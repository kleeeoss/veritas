import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db, init_db
from .models import ForensicReport, VerificationJob, VerificationStatus


class UploadResponse(BaseModel):
    job_id: str
    original_filename: str
    saved_path: str
    storage_provider: str
    mock_s3_bucket: str
    mock_s3_key: str
    status: str
    uploaded_at: datetime


app = FastAPI(title="Project Veritas Forensics API", version="0.1.0")
upload_dir = Path(os.getenv("UPLOAD_DIR", "./uploads"))


@app.on_event("startup")
def on_startup() -> None:
    upload_dir.mkdir(parents=True, exist_ok=True)
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/verify/upload", response_model=UploadResponse)
async def upload_for_verification(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")

    extension = Path(file.filename).suffix
    stored_name = f"{uuid4()}{extension}"
    stored_path = upload_dir / stored_name

    with stored_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    now = datetime.now(timezone.utc)
    mock_s3_key = f"temp-uploads/{stored_name}"
    job = VerificationJob(
        original_filename=file.filename,
        stored_path=str(stored_path.resolve()),
        storage_provider="local",
        s3_key=mock_s3_key,
        status=VerificationStatus.uploaded.value,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.flush()

    report = ForensicReport(job_id=job.id, integrity_score=None, summary_json=None, created_at=now)
    db.add(report)
    db.commit()

    return UploadResponse(
        job_id=job.id,
        original_filename=job.original_filename,
        saved_path=job.stored_path,
        storage_provider=job.storage_provider,
        mock_s3_bucket="veritas-temp-mock-bucket",
        mock_s3_key=mock_s3_key,
        status=job.status,
        uploaded_at=now,
    )
