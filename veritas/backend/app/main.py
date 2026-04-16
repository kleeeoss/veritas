import base64
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from veritas.ml.ocr_pipeline import extract_text_from_image

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("veritas-backend")


APP_VERSION = "1.0.0"
MODEL_SERVER_URL = os.getenv("MODEL_SERVER_URL", "http://veritas-model-server:8001/predict")
DB_PATH = Path(os.getenv("VERITAS_DB_PATH", "/app/reviews/veritas.db"))
ARTIFACT_DIR = Path(os.getenv("VERITAS_ARTIFACT_DIR", "/app/artifacts/reviews"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("MODEL_TIMEOUT_SECONDS", "30"))
JWT_SECRET = os.getenv("VERITAS_JWT_SECRET", "dev-secret-change-me")
JWT_ISSUER = os.getenv("VERITAS_JWT_ISSUER", "")
JWT_AUDIENCE = os.getenv("VERITAS_JWT_AUDIENCE", "")
AUDIT_SIGNING_KEY = os.getenv("VERITAS_AUDIT_SIGNING_KEY", "dev-audit-key-change-me")
VERIFICATION_REVIEW_LOWER = float(os.getenv("VERIFICATION_REVIEW_LOWER", "0.4"))
VERIFICATION_REVIEW_UPPER = float(os.getenv("VERIFICATION_REVIEW_UPPER", "0.6"))

ALLOWED_CONTENT_TYPES: Set[str] = {"image/jpeg", "image/png"}
ROLE_ADMIN = "admin"
ROLE_REVIEWER = "reviewer"
ROLE_AUDITOR = "auditor"
ROLE_VERIFIER = "verifier"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _b64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def decode_and_verify_jwt(token: str) -> Dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid JWT format.") from exc

    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid JWT encoding.") from exc

    if header.get("alg") != "HS256":
        raise HTTPException(status_code=401, detail="Unsupported JWT algorithm.")

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_sig = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual_sig = _b64url_decode(signature_b64)
    if not hmac.compare_digest(expected_sig, actual_sig):
        raise HTTPException(status_code=401, detail="JWT signature validation failed.")

    now = int(time.time())
    exp = payload.get("exp")
    nbf = payload.get("nbf")
    if exp is not None and now >= int(exp):
        raise HTTPException(status_code=401, detail="JWT expired.")
    if nbf is not None and now < int(nbf):
        raise HTTPException(status_code=401, detail="JWT not yet valid.")
    if JWT_ISSUER and payload.get("iss") != JWT_ISSUER:
        raise HTTPException(status_code=401, detail="JWT issuer mismatch.")
    if JWT_AUDIENCE:
        aud = payload.get("aud")
        if isinstance(aud, list):
            valid_aud = JWT_AUDIENCE in aud
        else:
            valid_aud = aud == JWT_AUDIENCE
        if not valid_aud:
            raise HTTPException(status_code=401, detail="JWT audience mismatch.")
    return payload


def require_roles(required_roles: Set[str]):
    def dependency(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer token.")
        token = authorization.split(" ", 1)[1].strip()
        claims = decode_and_verify_jwt(token)
        token_roles = claims.get("roles", [])
        if not isinstance(token_roles, list):
            raise HTTPException(status_code=401, detail="Invalid roles claim.")
        if required_roles.isdisjoint(set(token_roles)):
            raise HTTPException(status_code=403, detail="Insufficient role privileges.")
        return claims

    return dependency


def _detect_magic_type(data: bytes) -> Optional[str]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def validate_upload(file: UploadFile, payload: bytes) -> None:
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds maximum size of {MAX_UPLOAD_BYTES} bytes.")

    # Quick high-risk signature rejection first.
    banned_signatures = [b"MZ", b"\x7fELF", b"%PDF", b"PK\x03\x04"]
    if any(payload.startswith(sig) for sig in banned_signatures):
        raise HTTPException(status_code=400, detail="Potentially unsafe file signature detected.")

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported content type.")

    detected = _detect_magic_type(payload)
    if detected != file.content_type:
        raise HTTPException(status_code=415, detail="File signature does not match declared content type.")


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    artifact_path TEXT NOT NULL,
                    forgery_score REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    decision TEXT
                );

                CREATE TABLE IF NOT EXISTS idempotency_records (
                    idempotency_key TEXT PRIMARY KEY,
                    request_hash TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_time TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL,
                    signature TEXT NOT NULL
                );
                """
            )

    def save_review(self, review: Dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO reviews (id, filename, content_type, artifact_path, forgery_score, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    review["id"],
                    review["filename"],
                    review["content_type"],
                    review["artifact_path"],
                    review["forgery_score"],
                    review["created_at"],
                    review["updated_at"],
                ),
            )

    def list_pending_reviews(self) -> List[sqlite3.Row]:
        with self._conn() as conn:
            cur = conn.execute("SELECT * FROM reviews WHERE status = 'pending' ORDER BY created_at ASC")
            return cur.fetchall()

    def resolve_review(self, review_id: str, decision: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                """
                UPDATE reviews
                SET status = 'resolved', decision = ?, updated_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (decision, _utc_now(), review_id),
            )
            return cur.rowcount > 0

    def get_idempotent(self, key: str, request_hash: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT response_json, request_hash FROM idempotency_records WHERE idempotency_key = ?",
                (key,),
            )
            row = cur.fetchone()
            if not row:
                return None
            if row["request_hash"] != request_hash:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency key already used with different request payload.",
                )
            return json.loads(row["response_json"])

    def set_idempotent(self, key: str, request_hash: str, response: Dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO idempotency_records (idempotency_key, request_hash, response_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (key, request_hash, json.dumps(response, separators=(",", ":")), _utc_now()),
            )

    def append_audit_event(self, actor: str, event_type: str, payload: Dict[str, Any]) -> None:
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self._conn() as conn:
            cur = conn.execute("SELECT event_hash FROM audit_events ORDER BY id DESC LIMIT 1")
            latest = cur.fetchone()
            prev_hash = latest["event_hash"] if latest else ""
            event_time = _utc_now()
            raw = f"{prev_hash}|{event_type}|{actor}|{payload_json}|{event_time}".encode("utf-8")
            event_hash = hashlib.sha256(raw).hexdigest()
            signature = hmac.new(AUDIT_SIGNING_KEY.encode("utf-8"), event_hash.encode("utf-8"), hashlib.sha256).hexdigest()
            conn.execute(
                """
                INSERT INTO audit_events (event_time, actor, event_type, payload_json, prev_hash, event_hash, signature)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_time, actor, event_type, payload_json, prev_hash, event_hash, signature),
            )


class HealthCheck(BaseModel):
    status: str = "OK"
    version: str = APP_VERSION


class ReadinessCheck(BaseModel):
    status: str = "ready"
    database: str
    artifact_storage: str


class VerificationResponse(BaseModel):
    filename: str
    content_type: str
    message: str
    forgery_score: Optional[float] = None
    heatmap: Optional[str] = None
    ocr_text: Optional[str] = None
    needs_review: Optional[bool] = False
    risk_level: str
    reason_codes: List[str]


class ReviewItem(BaseModel):
    id: str
    filename: str
    image_data: str
    forgery_score: float
    created_at: str


class ReviewDecision(BaseModel):
    decision: str


ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
db = Database(DB_PATH)

app = FastAPI(title="Veritas Backend API", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def derive_risk(score: float, needs_review: bool) -> Dict[str, Any]:
    if score >= 0.8:
        return {"risk_level": "high", "reason_codes": ["ML_HIGH_FORGERY_SCORE"]}
    if score >= 0.6:
        return {"risk_level": "medium", "reason_codes": ["ML_SUSPICIOUS_SCORE"]}
    if needs_review:
        return {"risk_level": "needs-review", "reason_codes": ["ML_AMBIGUOUS_SCORE"]}
    return {"risk_level": "low", "reason_codes": ["ML_LOW_FORGERY_SCORE"]}


def save_review_artifact(review_id: str, payload: bytes, ext: str) -> str:
    review_dir = ARTIFACT_DIR / review_id[:2]
    review_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = review_dir / f"{review_id}.{ext}"
    artifact_path.write_bytes(payload)
    return str(artifact_path)


@app.get("/health", response_model=HealthCheck)
def get_health() -> HealthCheck:
    return HealthCheck(status="OK", version=APP_VERSION)


@app.get("/ready", response_model=ReadinessCheck)
def get_readiness() -> ReadinessCheck:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("SELECT 1")
        db_state = "ok"
    except Exception:
        db_state = "error"
    storage_state = "ok" if ARTIFACT_DIR.exists() and os.access(ARTIFACT_DIR, os.W_OK) else "error"
    if db_state != "ok" or storage_state != "ok":
        raise HTTPException(status_code=503, detail="Service dependencies unavailable.")
    return ReadinessCheck(status="ready", database=db_state, artifact_storage=storage_state)


@app.post("/api/v1/veritas/verify", response_model=VerificationResponse)
async def verify_document(
    file: UploadFile = File(...),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    claims: Dict[str, Any] = Depends(require_roles({ROLE_VERIFIER, ROLE_ADMIN, ROLE_AUDITOR, ROLE_REVIEWER})),
) -> VerificationResponse:
    image_bytes = await file.read()
    validate_upload(file, image_bytes)

    request_hash = hashlib.sha256(image_bytes).hexdigest()
    if idempotency_key:
        cached = db.get_idempotent(idempotency_key, request_hash)
        if cached:
            return VerificationResponse(**cached)

    ocr_result_text = extract_text_from_image(image_bytes)
    try:
        files = {"file": (file.filename, image_bytes, file.content_type)}
        response = requests.post(MODEL_SERVER_URL, files=files, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Model service unavailable: {exc}") from exc

    forgery_score = float(data.get("forgery_score", 0.0))
    needs_review_flag = VERIFICATION_REVIEW_LOWER <= forgery_score <= VERIFICATION_REVIEW_UPPER
    risk = derive_risk(forgery_score, needs_review_flag)

    if needs_review_flag:
        review_id = str(uuid.uuid4())
        ext = "png" if file.content_type == "image/png" else "jpg"
        artifact_path = save_review_artifact(review_id, image_bytes, ext)
        db.save_review(
            {
                "id": review_id,
                "filename": file.filename or f"document-{review_id}.{ext}",
                "content_type": file.content_type,
                "artifact_path": artifact_path,
                "forgery_score": forgery_score,
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
            }
        )
        db.append_audit_event(
            actor=claims.get("sub", "unknown"),
            event_type="review_created",
            payload={"review_id": review_id, "forgery_score": forgery_score},
        )

    payload = VerificationResponse(
        filename=file.filename or "uploaded-file",
        content_type=file.content_type or "application/octet-stream",
        message="File processed successfully.",
        forgery_score=forgery_score,
        heatmap=data.get("heatmap"),
        ocr_text=ocr_result_text,
        needs_review=needs_review_flag,
        risk_level=risk["risk_level"],
        reason_codes=risk["reason_codes"],
    )

    if idempotency_key:
        db.set_idempotent(idempotency_key, request_hash, payload.model_dump())
    db.append_audit_event(
        actor=claims.get("sub", "unknown"),
        event_type="verification_completed",
        payload={"filename": payload.filename, "risk_level": payload.risk_level, "score": forgery_score},
    )
    return payload


@app.get("/api/v1/admin/reviews", response_model=List[ReviewItem])
def get_reviews(claims: Dict[str, Any] = Depends(require_roles({ROLE_REVIEWER, ROLE_ADMIN, ROLE_AUDITOR}))) -> List[ReviewItem]:
    rows = db.list_pending_reviews()
    reviews: List[ReviewItem] = []
    for row in rows:
        artifact_bytes = Path(row["artifact_path"]).read_bytes()
        reviews.append(
            ReviewItem(
                id=row["id"],
                filename=row["filename"],
                image_data=base64.b64encode(artifact_bytes).decode("utf-8"),
                forgery_score=row["forgery_score"],
                created_at=row["created_at"],
            )
        )
    db.append_audit_event(
        actor=claims.get("sub", "unknown"),
        event_type="review_list_accessed",
        payload={"count": len(reviews)},
    )
    return reviews


@app.post("/api/v1/admin/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def process_review(
    review_id: str,
    decision: ReviewDecision,
    claims: Dict[str, Any] = Depends(require_roles({ROLE_REVIEWER, ROLE_ADMIN})),
) -> None:
    if decision.decision not in {"approve", "reject"}:
        raise HTTPException(status_code=422, detail="Decision must be 'approve' or 'reject'.")
    updated = db.resolve_review(review_id=review_id, decision=decision.decision)
    if not updated:
        raise HTTPException(status_code=404, detail="Review item not found.")
    db.append_audit_event(
        actor=claims.get("sub", "unknown"),
        event_type="review_resolved",
        payload={"review_id": review_id, "decision": decision.decision},
    )
    logger.info("Processed review for %s with decision: %s", review_id, decision.decision)
