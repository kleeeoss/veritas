import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image

from veritas.ml.ocr_pipeline import extract_text_from_image

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("veritas-backend")

APP_VERSION = "2.0.0"
MODEL_SERVER_URL = os.getenv("MODEL_SERVER_URL", "http://veritas-model-server:8001/predict")
MODEL_METADATA_URL = os.getenv("MODEL_METADATA_URL", "http://veritas-model-server:8001/metadata")
EXTERNAL_VERIFY_URL = os.getenv("EXTERNAL_VERIFY_URL", "")
DB_PATH = Path(os.getenv("VERITAS_DB_PATH", "/app/reviews/veritas.db"))
ARTIFACT_DIR = Path(os.getenv("VERITAS_ARTIFACT_DIR", "/app/artifacts/reviews"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("MODEL_TIMEOUT_SECONDS", "30"))
MODEL_RETRIES = int(os.getenv("MODEL_RETRIES", "2"))
CIRCUIT_BREAKER_FAIL_THRESHOLD = int(os.getenv("MODEL_CB_FAIL_THRESHOLD", "3"))
CIRCUIT_BREAKER_OPEN_SECONDS = int(os.getenv("MODEL_CB_OPEN_SECONDS", "20"))
JWT_SECRET = os.getenv("VERITAS_JWT_SECRET", "dev-secret-change-me")
JWT_ISSUER = os.getenv("VERITAS_JWT_ISSUER", "")
JWT_AUDIENCE = os.getenv("VERITAS_JWT_AUDIENCE", "")
AUDIT_SIGNING_KEY = os.getenv("VERITAS_AUDIT_SIGNING_KEY", "dev-audit-key-change-me")
VERIFICATION_REVIEW_LOWER = float(os.getenv("VERIFICATION_REVIEW_LOWER", "0.4"))
VERIFICATION_REVIEW_UPPER = float(os.getenv("VERIFICATION_REVIEW_UPPER", "0.6"))
ASYNC_QUEUE_MAX = int(os.getenv("ASYNC_QUEUE_MAX", "1000"))

ALLOWED_CONTENT_TYPES: Set[str] = {"image/jpeg", "image/png"}
ROLE_ADMIN = "admin"
ROLE_REVIEWER = "reviewer"
ROLE_AUDITOR = "auditor"
ROLE_VERIFIER = "verifier"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


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
        claims = decode_and_verify_jwt(authorization.split(" ", 1)[1].strip())
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
    if len(data) >= 4 and data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def validate_upload(file: UploadFile, payload: bytes) -> None:
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds maximum size of {MAX_UPLOAD_BYTES} bytes.")

    banned_signatures = [b"MZ", b"\x7fELF", b"%PDF", b"#!", b"<!DOCTYPE html", b"<html", b"<?php"]
    if any(payload.startswith(sig) for sig in banned_signatures):
        raise HTTPException(status_code=400, detail="Potentially unsafe file signature detected.")

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported content type.")
    if _detect_magic_type(payload) != file.content_type:
        raise HTTPException(status_code=415, detail="File signature does not match declared content type.")


class HealthCheck(BaseModel):
    status: str = "OK"
    version: str = APP_VERSION


class ReadinessCheck(BaseModel):
    status: str = "ready"
    database: str
    artifact_storage: str
    model_service: str
    queue_depth: int
    circuit_breaker_open: bool


class DetectorScore(BaseModel):
    detector: str
    version: str
    forgery_score: float
    confidence: float
    reason_codes: List[str]


class VerificationResponse(BaseModel):
    filename: str
    content_type: str
    message: str
    forgery_score: float
    heatmap: Optional[str] = None
    ocr_text: Optional[str] = None
    needs_review: bool = False
    risk_level: str
    reason_codes: List[str]
    detectors: List[DetectorScore]
    model_version: str
    trace_id: str


class VerificationJobResponse(BaseModel):
    job_id: str
    status: str
    trace_id: str


class VerificationJobStatus(BaseModel):
    job_id: str
    status: str
    error: Optional[str] = None
    result: Optional[VerificationResponse] = None
    created_at: str
    updated_at: str


class ReviewItem(BaseModel):
    id: str
    filename: str
    image_data: str
    forgery_score: float
    created_at: str
    status: str
    risk_level: str
    escalation_reason: Optional[str] = None


class ReviewDecision(BaseModel):
    decision: str
    notes: Optional[str] = None


class ReviewEscalation(BaseModel):
    reason: str


class ReviewHistoryItem(BaseModel):
    action: str
    actor: str
    notes: Optional[str]
    created_at: str


class ModelRecord(BaseModel):
    model_version: str
    source: str
    status: str
    metadata: Dict[str, Any]
    created_at: str


class DriftSummary(BaseModel):
    sample_count: int
    avg_score: float
    high_risk_ratio: float
    by_model: Dict[str, Dict[str, float]]


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
                    risk_level TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    escalation_reason TEXT,
                    decision TEXT,
                    decision_notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS review_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    notes TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS idempotency_records (
                    idempotency_key TEXT PRIMARY KEY,
                    request_hash TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS verification_jobs (
                    job_id TEXT PRIMARY KEY,
                    idempotency_key TEXT,
                    request_hash TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    artifact_path TEXT NOT NULL,
                    submitted_by TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    retries INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
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

                CREATE TABLE IF NOT EXISTS model_registry (
                    model_version TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS verification_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    score REAL NOT NULL,
                    risk_level TEXT NOT NULL
                );
                """
            )

    def append_audit_event(self, actor: str, event_type: str, payload: Dict[str, Any]) -> None:
        payload_json = _json(payload)
        with self._conn() as conn:
            cur = conn.execute("SELECT event_hash FROM audit_events ORDER BY id DESC LIMIT 1")
            last = cur.fetchone()
            prev_hash = last["event_hash"] if last else ""
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

    def list_pending_reviews(self) -> List[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM reviews WHERE status IN ('pending','escalated','in_review') ORDER BY created_at ASC"
            ).fetchall()

    def create_review(self, review: Dict[str, Any], actor: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO reviews (id, filename, content_type, artifact_path, forgery_score, risk_level, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    review["id"],
                    review["filename"],
                    review["content_type"],
                    review["artifact_path"],
                    review["forgery_score"],
                    review["risk_level"],
                    review["created_at"],
                    review["updated_at"],
                ),
            )
            conn.execute(
                "INSERT INTO review_history (review_id, action, actor, notes, created_at) VALUES (?, 'created', ?, ?, ?)",
                (review["id"], actor, "auto-created from verification pipeline", _utc_now()),
            )

    def resolve_review(self, review_id: str, decision: str, notes: Optional[str], actor: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                """
                UPDATE reviews
                SET status='resolved', decision=?, decision_notes=?, escalation_reason=NULL, updated_at=?
                WHERE id=? AND status IN ('pending','escalated','in_review')
                """,
                (decision, notes, _utc_now(), review_id),
            )
            if cur.rowcount:
                conn.execute(
                    "INSERT INTO review_history (review_id, action, actor, notes, created_at) VALUES (?, 'resolved', ?, ?, ?)",
                    (review_id, actor, f"{decision}: {notes or ''}".strip(), _utc_now()),
                )
            return cur.rowcount > 0

    def escalate_review(self, review_id: str, reason: str, actor: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                """
                UPDATE reviews
                SET status='escalated', escalation_reason=?, updated_at=?
                WHERE id=? AND status IN ('pending','in_review')
                """,
                (reason, _utc_now(), review_id),
            )
            if cur.rowcount:
                conn.execute(
                    "INSERT INTO review_history (review_id, action, actor, notes, created_at) VALUES (?, 'escalated', ?, ?, ?)",
                    (review_id, actor, reason, _utc_now()),
                )
            return cur.rowcount > 0

    def start_review(self, review_id: str, actor: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE reviews SET status='in_review', updated_at=? WHERE id=? AND status IN ('pending','escalated')",
                (_utc_now(), review_id),
            )
            if cur.rowcount:
                conn.execute(
                    "INSERT INTO review_history (review_id, action, actor, notes, created_at) VALUES (?, 'in_review', ?, ?, ?)",
                    (review_id, actor, "reviewer started triage", _utc_now()),
                )
            return cur.rowcount > 0

    def get_review_history(self, review_id: str) -> List[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute(
                "SELECT action, actor, notes, created_at FROM review_history WHERE review_id=? ORDER BY id ASC",
                (review_id,),
            ).fetchall()

    def get_idempotent(self, key: str, request_hash: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT request_hash, response_json FROM idempotency_records WHERE idempotency_key=?",
                (key,),
            ).fetchone()
            if not row:
                return None
            if row["request_hash"] != request_hash:
                raise HTTPException(status_code=409, detail="Idempotency key reused with different payload.")
            return json.loads(row["response_json"])

    def set_idempotent(self, key: str, request_hash: str, response: Dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO idempotency_records (idempotency_key, request_hash, response_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (key, request_hash, _json(response), _utc_now()),
            )

    def create_job(
        self,
        job_id: str,
        idempotency_key: Optional[str],
        request_hash: str,
        filename: str,
        content_type: str,
        artifact_path: str,
        submitted_by: str,
        trace_id: str,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO verification_jobs (
                    job_id, idempotency_key, request_hash, filename, content_type, artifact_path,
                    submitted_by, trace_id, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)
                """,
                (
                    job_id,
                    idempotency_key,
                    request_hash,
                    filename,
                    content_type,
                    artifact_path,
                    submitted_by,
                    trace_id,
                    _utc_now(),
                    _utc_now(),
                ),
            )

    def find_job_by_idempotency(self, key: str, request_hash: str) -> Optional[sqlite3.Row]:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM verification_jobs
                WHERE idempotency_key=? ORDER BY created_at DESC LIMIT 1
                """,
                (key,),
            ).fetchone()
            if not row:
                return None
            if row["request_hash"] != request_hash:
                raise HTTPException(status_code=409, detail="Idempotency key reused with different payload.")
            return row

    def update_job_status(self, job_id: str, status_value: str, error: Optional[str] = None) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE verification_jobs SET status=?, error=?, updated_at=? WHERE job_id=?",
                (status_value, error, _utc_now(), job_id),
            )

    def mark_job_running(self, job_id: str) -> None:
        self.update_job_status(job_id, "running")

    def mark_job_failed(self, job_id: str, error: str) -> None:
        self.update_job_status(job_id, "failed", error)

    def mark_job_completed(self, job_id: str, result: Dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE verification_jobs SET status='completed', result_json=?, updated_at=? WHERE job_id=?",
                (_json(result), _utc_now(), job_id),
            )

    def get_job(self, job_id: str) -> Optional[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute("SELECT * FROM verification_jobs WHERE job_id=?", (job_id,)).fetchone()

    def list_recoverable_jobs(self) -> List[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT job_id FROM verification_jobs WHERE status IN ('queued','running') ORDER BY created_at ASC"
            ).fetchall()
            return [row["job_id"] for row in rows]

    def upsert_model(self, model_version: str, source: str, status_value: str, metadata: Dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO model_registry (model_version, source, status, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(model_version) DO UPDATE SET
                    source=excluded.source,
                    status=excluded.status,
                    metadata_json=excluded.metadata_json
                """,
                (model_version, source, status_value, _json(metadata), _utc_now()),
            )

    def activate_model(self, model_version: str) -> bool:
        with self._conn() as conn:
            exists = conn.execute("SELECT 1 FROM model_registry WHERE model_version=?", (model_version,)).fetchone()
            if not exists:
                return False
            conn.execute("UPDATE model_registry SET status='inactive' WHERE status='active'")
            conn.execute("UPDATE model_registry SET status='active' WHERE model_version=?", (model_version,))
            return True

    def get_active_model(self) -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT model_version FROM model_registry WHERE status='active' LIMIT 1").fetchone()
            return row["model_version"] if row else "unknown"

    def list_models(self) -> List[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute("SELECT * FROM model_registry ORDER BY created_at DESC").fetchall()

    def add_outcome(self, model_version: str, score: float, risk_level: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO verification_outcomes (created_at, model_version, score, risk_level) VALUES (?, ?, ?, ?)",
                (_utc_now(), model_version, score, risk_level),
            )

    def get_drift_summary(self) -> Dict[str, Any]:
        with self._conn() as conn:
            rows = conn.execute("SELECT model_version, score, risk_level FROM verification_outcomes").fetchall()
        if not rows:
            return {"sample_count": 0, "avg_score": 0.0, "high_risk_ratio": 0.0, "by_model": {}}
        total = len(rows)
        avg_score = sum(float(r["score"]) for r in rows) / total
        high = sum(1 for r in rows if r["risk_level"] == "high")
        by_model: Dict[str, Dict[str, float]] = {}
        for row in rows:
            m = row["model_version"]
            by_model.setdefault(m, {"count": 0, "avg_score": 0.0})
            by_model[m]["count"] += 1
            by_model[m]["avg_score"] += float(row["score"])
        for m, v in by_model.items():
            v["avg_score"] = v["avg_score"] / v["count"]
        return {"sample_count": total, "avg_score": avg_score, "high_risk_ratio": high / total, "by_model": by_model}


ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
db = Database(DB_PATH)
metrics: Dict[str, int] = {
    "verify_sync_total": 0,
    "verify_async_total": 0,
    "jobs_completed": 0,
    "jobs_failed": 0,
    "reviews_escalated": 0,
    "model_calls_failed": 0,
}


class CircuitBreaker:
    def __init__(self):
        self.failures = 0
        self.open_until = 0.0

    def is_open(self) -> bool:
        return time.time() < self.open_until

    def success(self) -> None:
        self.failures = 0
        self.open_until = 0.0

    def fail(self) -> None:
        self.failures += 1
        if self.failures >= CIRCUIT_BREAKER_FAIL_THRESHOLD:
            self.open_until = time.time() + CIRCUIT_BREAKER_OPEN_SECONDS


circuit_breaker = CircuitBreaker()
job_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=ASYNC_QUEUE_MAX)
worker_task: Optional[asyncio.Task] = None

app = FastAPI(title="Veritas Backend API", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = trace_id
    return response


def save_artifact(prefix: str, payload: bytes, ext: str) -> str:
    item_id = str(uuid.uuid4())
    d = ARTIFACT_DIR / prefix / item_id[:2]
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{item_id}.{ext}"
    p.write_bytes(payload)
    return str(p)


def calc_ocr_consistency_score(text: str) -> Tuple[float, List[str]]:
    lower = text.lower() if text else ""
    keywords = ["certificate", "issued", "name", "date"]
    hits = sum(1 for word in keywords if word in lower)
    if len(lower) < 20:
        return 0.75, ["OCR_TEXT_TOO_SHORT"]
    if hits <= 1:
        return 0.65, ["OCR_MISSING_CERTIFICATE_KEYWORDS"]
    if hits >= 3:
        return 0.2, ["OCR_STRUCTURE_CONSISTENT"]
    return 0.45, ["OCR_PARTIAL_STRUCTURE"]


def calc_metadata_tamper_score(image_bytes: bytes) -> Tuple[float, List[str]]:
    try:
        im = Image.open(io_from_bytes(image_bytes))
        w, h = im.size
        score = 0.15
        reasons: List[str] = []
        if w < 500 or h < 300:
            score += 0.35
            reasons.append("LOW_RESOLUTION_DOCUMENT")
        ratio = w / h if h else 0
        if ratio < 1.0 or ratio > 2.2:
            score += 0.25
            reasons.append("UNUSUAL_ASPECT_RATIO")
        exif = im.getexif()
        if exif and 305 in exif:
            reasons.append("EDITING_SOFTWARE_METADATA_PRESENT")
            score += 0.15
        if not reasons:
            reasons = ["METADATA_APPEARS_NORMAL"]
        return min(score, 1.0), reasons
    except Exception:
        return 0.6, ["METADATA_PARSE_ERROR"]


def io_from_bytes(data: bytes):
    from io import BytesIO

    return BytesIO(data)


def calc_template_rule_score(text: str) -> Tuple[float, List[str]]:
    lower = text.lower() if text else ""
    reasons: List[str] = []
    score = 0.2
    if not re.search(r"\b\d{2}[-/]\d{2}[-/]\d{4}\b", text or ""):
        score += 0.25
        reasons.append("MISSING_DATE_PATTERN")
    if "certificate" not in lower:
        score += 0.3
        reasons.append("MISSING_CERTIFICATE_TITLE")
    if "issued" not in lower:
        score += 0.2
        reasons.append("MISSING_ISSUANCE_TERM")
    if not reasons:
        reasons = ["TEMPLATE_RULES_PASS"]
    return min(score, 1.0), reasons


def call_external_verifier(request_hash: str) -> Tuple[float, List[str]]:
    if not EXTERNAL_VERIFY_URL:
        return 0.5, ["EXTERNAL_VERIFIER_NOT_CONFIGURED"]
    try:
        r = requests.post(EXTERNAL_VERIFY_URL, json={"request_hash": request_hash}, timeout=5)
        r.raise_for_status()
        payload = r.json()
        verified = bool(payload.get("verified"))
        if verified:
            return 0.1, ["EXTERNAL_VERIFIER_CONFIRMED"]
        return 0.8, ["EXTERNAL_VERIFIER_REJECTED"]
    except Exception:
        return 0.55, ["EXTERNAL_VERIFIER_UNAVAILABLE"]


async def call_model_service(image_bytes: bytes, filename: str, content_type: str) -> Dict[str, Any]:
    if circuit_breaker.is_open():
        raise HTTPException(status_code=503, detail="Model service circuit breaker is open.")
    err = None
    for attempt in range(MODEL_RETRIES + 1):
        try:
            files = {"file": (filename, image_bytes, content_type)}
            response = requests.post(MODEL_SERVER_URL, files=files, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            circuit_breaker.success()
            return response.json()
        except Exception as exc:
            err = exc
            metrics["model_calls_failed"] += 1
            circuit_breaker.fail()
            if attempt < MODEL_RETRIES:
                await asyncio.sleep(min(1.5 * (attempt + 1), 4.0))
    raise HTTPException(status_code=503, detail=f"Model service unavailable after retries: {err}")


def compose_risk(detectors: List[DetectorScore]) -> Tuple[float, str, List[str]]:
    weights = {
        "ml_classifier": 0.50,
        "ocr_consistency": 0.20,
        "metadata_tamper": 0.15,
        "template_rules": 0.10,
        "external_verifier": 0.05,
    }
    total = 0.0
    reasons: List[str] = []
    for d in detectors:
        total += weights.get(d.detector, 0.0) * d.forgery_score
        reasons.extend(d.reason_codes)
    if total >= 0.8:
        risk = "high"
    elif total >= 0.6:
        risk = "medium"
    elif total >= 0.4:
        risk = "needs-review"
    else:
        risk = "low"
    return total, risk, sorted(set(reasons))


async def fetch_model_metadata() -> Dict[str, Any]:
    try:
        res = requests.get(MODEL_METADATA_URL, timeout=5)
        res.raise_for_status()
        return res.json()
    except Exception:
        return {"model_version": "unknown", "status": "unavailable"}


async def run_verification_pipeline(
    image_bytes: bytes,
    filename: str,
    content_type: str,
    actor: str,
    trace_id: str,
) -> VerificationResponse:
    model_data = await call_model_service(image_bytes, filename, content_type)
    ocr_text = extract_text_from_image(image_bytes)
    request_hash = hashlib.sha256(image_bytes).hexdigest()

    ml_score = float(model_data.get("forgery_score", 0.0))
    ocr_score, ocr_reasons = calc_ocr_consistency_score(ocr_text or "")
    metadata_score, metadata_reasons = calc_metadata_tamper_score(image_bytes)
    template_score, template_reasons = calc_template_rule_score(ocr_text or "")
    external_score, external_reasons = call_external_verifier(request_hash)

    detectors = [
        DetectorScore(
            detector="ml_classifier",
            version=f"resnet18:{model_data.get('model_version', db.get_active_model())}",
            forgery_score=ml_score,
            confidence=0.92,
            reason_codes=["ML_BASELINE_SCORE"],
        ),
        DetectorScore(
            detector="ocr_consistency",
            version="ocr-ruleset:v1",
            forgery_score=ocr_score,
            confidence=0.76,
            reason_codes=ocr_reasons,
        ),
        DetectorScore(
            detector="metadata_tamper",
            version="metadata-heuristics:v1",
            forgery_score=metadata_score,
            confidence=0.68,
            reason_codes=metadata_reasons,
        ),
        DetectorScore(
            detector="template_rules",
            version="template-rules:v1",
            forgery_score=template_score,
            confidence=0.71,
            reason_codes=template_reasons,
        ),
        DetectorScore(
            detector="external_verifier",
            version="ext-connector:v1",
            forgery_score=external_score,
            confidence=0.50,
            reason_codes=external_reasons,
        ),
    ]
    combined_score, risk_level, reason_codes = compose_risk(detectors)
    needs_review = VERIFICATION_REVIEW_LOWER <= combined_score <= VERIFICATION_REVIEW_UPPER or risk_level == "needs-review"

    model_version = str(model_data.get("model_version") or db.get_active_model())
    response = VerificationResponse(
        filename=filename or "uploaded-file",
        content_type=content_type or "application/octet-stream",
        message="File processed successfully.",
        forgery_score=combined_score,
        heatmap=model_data.get("heatmap"),
        ocr_text=ocr_text,
        needs_review=needs_review,
        risk_level=risk_level,
        reason_codes=reason_codes,
        detectors=detectors,
        model_version=model_version,
        trace_id=trace_id,
    )

    db.add_outcome(model_version=model_version, score=combined_score, risk_level=risk_level)
    db.append_audit_event(
        actor=actor,
        event_type="verification_completed",
        payload={"filename": response.filename, "score": combined_score, "risk_level": risk_level, "trace_id": trace_id},
    )

    if needs_review:
        ext = "png" if content_type == "image/png" else "jpg"
        review_id = str(uuid.uuid4())
        artifact_path = save_artifact("reviews", image_bytes, ext)
        db.create_review(
            {
                "id": review_id,
                "filename": response.filename,
                "content_type": content_type,
                "artifact_path": artifact_path,
                "forgery_score": combined_score,
                "risk_level": risk_level,
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
            },
            actor=actor,
        )
        db.append_audit_event(
            actor=actor,
            event_type="review_created",
            payload={"review_id": review_id, "score": combined_score, "trace_id": trace_id},
        )
    return response


async def process_queued_job(job_id: str) -> None:
    row = db.get_job(job_id)
    if not row:
        return
    db.mark_job_running(job_id)
    try:
        image_bytes = Path(row["artifact_path"]).read_bytes()
        result = await run_verification_pipeline(
            image_bytes=image_bytes,
            filename=row["filename"],
            content_type=row["content_type"],
            actor=row["submitted_by"],
            trace_id=row["trace_id"],
        )
        db.mark_job_completed(job_id, result.model_dump())
        metrics["jobs_completed"] += 1
    except Exception as exc:
        db.mark_job_failed(job_id, str(exc))
        metrics["jobs_failed"] += 1


async def job_worker() -> None:
    while True:
        job_id = await job_queue.get()
        try:
            await process_queued_job(job_id)
        finally:
            job_queue.task_done()


@app.on_event("startup")
async def on_startup() -> None:
    global worker_task
    metadata = await fetch_model_metadata()
    model_version = str(metadata.get("model_version", "unknown"))
    db.upsert_model(model_version=model_version, source="model-server", status_value="active", metadata=metadata)

    for job_id in db.list_recoverable_jobs():
        await job_queue.put(job_id)
    if worker_task is None:
        worker_task = asyncio.create_task(job_worker())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global worker_task
    if worker_task:
        worker_task.cancel()
        worker_task = None


@app.get("/health", response_model=HealthCheck)
def get_health() -> HealthCheck:
    return HealthCheck(status="OK", version=APP_VERSION)


@app.get("/ready", response_model=ReadinessCheck)
async def get_readiness() -> ReadinessCheck:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("SELECT 1")
        db_state = "ok"
    except Exception as exc:
        logger.exception("Readiness check failed for database: %s", exc)
        db_state = "error"

    storage_state = "ok" if ARTIFACT_DIR.exists() and os.access(ARTIFACT_DIR, os.W_OK) else "error"
    model_meta = await fetch_model_metadata()
    model_state = "ok" if model_meta.get("status") != "unavailable" else "error"
    if db_state != "ok" or storage_state != "ok":
        raise HTTPException(status_code=503, detail="Service dependencies unavailable.")
    return ReadinessCheck(
        status="ready",
        database=db_state,
        artifact_storage=storage_state,
        model_service=model_state,
        queue_depth=job_queue.qsize(),
        circuit_breaker_open=circuit_breaker.is_open(),
    )


@app.get("/metrics")
def get_metrics(claims: Dict[str, Any] = Depends(require_roles({ROLE_ADMIN, ROLE_AUDITOR}))) -> Dict[str, Any]:
    pending_reviews = len(db.list_pending_reviews())
    drift = db.get_drift_summary()
    return {
        "counters": metrics,
        "queue_depth": job_queue.qsize(),
        "pending_reviews": pending_reviews,
        "drift": drift,
        "timestamp": _utc_now(),
        "requested_by": claims.get("sub", "unknown"),
    }


@app.post("/api/v1/veritas/verify", response_model=VerificationResponse)
async def verify_document(
    request: Request,
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

    metrics["verify_sync_total"] += 1
    payload = await run_verification_pipeline(
        image_bytes=image_bytes,
        filename=file.filename or "uploaded-file",
        content_type=file.content_type or "application/octet-stream",
        actor=claims.get("sub", "unknown"),
        trace_id=request.state.trace_id,
    )
    if idempotency_key:
        db.set_idempotent(idempotency_key, request_hash, payload.model_dump())
    return payload


@app.post("/api/v1/veritas/verify-async", response_model=VerificationJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def verify_document_async(
    request: Request,
    file: UploadFile = File(...),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    claims: Dict[str, Any] = Depends(require_roles({ROLE_VERIFIER, ROLE_ADMIN, ROLE_AUDITOR, ROLE_REVIEWER})),
) -> VerificationJobResponse:
    image_bytes = await file.read()
    validate_upload(file, image_bytes)
    request_hash = hashlib.sha256(image_bytes).hexdigest()
    if idempotency_key:
        existing = db.find_job_by_idempotency(idempotency_key, request_hash)
        if existing:
            return VerificationJobResponse(job_id=existing["job_id"], status=existing["status"], trace_id=existing["trace_id"])

    artifact_ext = "png" if file.content_type == "image/png" else "jpg"
    artifact_path = save_artifact("jobs", image_bytes, artifact_ext)
    job_id = str(uuid.uuid4())
    db.create_job(
        job_id=job_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        filename=file.filename or f"upload-{job_id}.{artifact_ext}",
        content_type=file.content_type or "application/octet-stream",
        artifact_path=artifact_path,
        submitted_by=claims.get("sub", "unknown"),
        trace_id=request.state.trace_id,
    )
    await job_queue.put(job_id)
    metrics["verify_async_total"] += 1
    db.append_audit_event(
        actor=claims.get("sub", "unknown"),
        event_type="verification_job_queued",
        payload={"job_id": job_id, "trace_id": request.state.trace_id},
    )
    return VerificationJobResponse(job_id=job_id, status="queued", trace_id=request.state.trace_id)


@app.get("/api/v1/veritas/jobs/{job_id}", response_model=VerificationJobStatus)
def get_job_status(
    job_id: str,
    claims: Dict[str, Any] = Depends(require_roles({ROLE_VERIFIER, ROLE_ADMIN, ROLE_AUDITOR, ROLE_REVIEWER})),
) -> VerificationJobStatus:
    row = db.get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found.")
    if claims.get("sub", "unknown") != row["submitted_by"] and ROLE_ADMIN not in claims.get("roles", []):
        if ROLE_AUDITOR not in claims.get("roles", []):
            raise HTTPException(status_code=403, detail="Not allowed to view this job.")
    result = VerificationResponse(**json.loads(row["result_json"])) if row["result_json"] else None
    return VerificationJobStatus(
        job_id=row["job_id"],
        status=row["status"],
        error=row["error"],
        result=result,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@app.get("/api/v1/admin/reviews", response_model=List[ReviewItem])
def get_reviews(
    claims: Dict[str, Any] = Depends(require_roles({ROLE_REVIEWER, ROLE_ADMIN, ROLE_AUDITOR})),
) -> List[ReviewItem]:
    rows = db.list_pending_reviews()
    out: List[ReviewItem] = []
    for row in rows:
        image_data = base64.b64encode(Path(row["artifact_path"]).read_bytes()).decode("utf-8")
        out.append(
            ReviewItem(
                id=row["id"],
                filename=row["filename"],
                image_data=image_data,
                forgery_score=float(row["forgery_score"]),
                created_at=row["created_at"],
                status=row["status"],
                risk_level=row["risk_level"],
                escalation_reason=row["escalation_reason"],
            )
        )
    db.append_audit_event(
        actor=claims.get("sub", "unknown"),
        event_type="review_list_accessed",
        payload={"count": len(out)},
    )
    return out


@app.post("/api/v1/admin/reviews/{review_id}/start", status_code=status.HTTP_204_NO_CONTENT)
def start_review(review_id: str, claims: Dict[str, Any] = Depends(require_roles({ROLE_REVIEWER, ROLE_ADMIN}))) -> None:
    if not db.start_review(review_id, claims.get("sub", "unknown")):
        raise HTTPException(status_code=404, detail="Review item not found.")


@app.post("/api/v1/admin/reviews/{review_id}/escalate", status_code=status.HTTP_204_NO_CONTENT)
def escalate_review(
    review_id: str,
    escalation: ReviewEscalation,
    claims: Dict[str, Any] = Depends(require_roles({ROLE_REVIEWER, ROLE_ADMIN})),
) -> None:
    if not escalation.reason.strip():
        raise HTTPException(status_code=422, detail="Escalation reason is required.")
    if not db.escalate_review(review_id, escalation.reason.strip(), claims.get("sub", "unknown")):
        raise HTTPException(status_code=404, detail="Review item not found.")
    metrics["reviews_escalated"] += 1
    db.append_audit_event(
        actor=claims.get("sub", "unknown"),
        event_type="review_escalated",
        payload={"review_id": review_id, "reason": escalation.reason.strip()},
    )


@app.get("/api/v1/admin/reviews/{review_id}/history", response_model=List[ReviewHistoryItem])
def review_history(
    review_id: str,
    claims: Dict[str, Any] = Depends(require_roles({ROLE_REVIEWER, ROLE_ADMIN, ROLE_AUDITOR})),
) -> List[ReviewHistoryItem]:
    rows = db.get_review_history(review_id)
    if not rows:
        return []
    db.append_audit_event(
        actor=claims.get("sub", "unknown"),
        event_type="review_history_accessed",
        payload={"review_id": review_id},
    )
    return [ReviewHistoryItem(action=r["action"], actor=r["actor"], notes=r["notes"], created_at=r["created_at"]) for r in rows]


@app.post("/api/v1/admin/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def process_review(
    review_id: str,
    decision: ReviewDecision,
    claims: Dict[str, Any] = Depends(require_roles({ROLE_REVIEWER, ROLE_ADMIN})),
) -> None:
    if decision.decision not in {"approve", "reject"}:
        raise HTTPException(status_code=422, detail="Decision must be 'approve' or 'reject'.")
    if not db.resolve_review(review_id, decision.decision, decision.notes, claims.get("sub", "unknown")):
        raise HTTPException(status_code=404, detail="Review item not found.")
    db.append_audit_event(
        actor=claims.get("sub", "unknown"),
        event_type="review_resolved",
        payload={"review_id": review_id, "decision": decision.decision},
    )


@app.get("/api/v1/models", response_model=List[ModelRecord])
def list_models(claims: Dict[str, Any] = Depends(require_roles({ROLE_ADMIN, ROLE_AUDITOR}))) -> List[ModelRecord]:
    rows = db.list_models()
    return [
        ModelRecord(
            model_version=row["model_version"],
            source=row["source"],
            status=row["status"],
            metadata=json.loads(row["metadata_json"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]


@app.post("/api/v1/models/{model_version}/activate", status_code=status.HTTP_204_NO_CONTENT)
def activate_model(model_version: str, claims: Dict[str, Any] = Depends(require_roles({ROLE_ADMIN}))) -> None:
    if not db.activate_model(model_version):
        raise HTTPException(status_code=404, detail="Model version not found.")
    db.append_audit_event(
        actor=claims.get("sub", "unknown"),
        event_type="model_activated",
        payload={"model_version": model_version},
    )


@app.get("/api/v1/models/drift-summary", response_model=DriftSummary)
def drift_summary(claims: Dict[str, Any] = Depends(require_roles({ROLE_ADMIN, ROLE_AUDITOR}))) -> DriftSummary:
    summary = db.get_drift_summary()
    return DriftSummary(**summary)
