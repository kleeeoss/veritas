import os
import shutil
import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db, init_db
from .forensics_core import (
    aggregate_trust_score,
    analyze_ela,
    analyze_metadata,
    verify_signature_siamese,
)
from .models import ForensicReport, VerificationJob, VerificationStatus, utc_now


class UploadResponse(BaseModel):
    job_id: str
    original_filename: str
    saved_path: str
    storage_provider: str
    mock_s3_bucket: str
    mock_s3_key: str
    status: str
    uploaded_at: datetime


class VerificationRunResponse(BaseModel):
    job_id: str
    status: str
    trust_score: float
    passed: bool
    report_created_at: datetime


class VerificationStatusResponse(BaseModel):
    job_id: str
    original_filename: str
    status: str
    created_at: datetime
    updated_at: datetime


class ForensicReportResponse(BaseModel):
    job_id: str
    status: str
    trust_score: float | None
    summary: dict[str, Any] | None
    report_created_at: datetime


class VerificationJobListItem(BaseModel):
    job_id: str
    original_filename: str
    status: str
    created_at: datetime
    updated_at: datetime


class VerificationJobListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[VerificationJobListItem]


class ForensicReportListItem(BaseModel):
    job_id: str
    original_filename: str
    status: str
    trust_score: float | None
    report_created_at: datetime
    summary: dict[str, Any] | None


class ForensicReportListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ForensicReportListItem]


upload_dir = Path(os.getenv("UPLOAD_DIR", "./uploads"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    upload_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(title="Project Veritas Forensics API", version="0.1.0", lifespan=lifespan)


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

    now = utc_now()
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


@app.post("/api/verify/{job_id}/run", response_model=VerificationRunResponse)
def run_verification(
    job_id: str,
    db: Session = Depends(get_db),
) -> VerificationRunResponse:
    job = db.query(VerificationJob).filter(VerificationJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Verification job not found.")

    file_path = Path(job.stored_path)
    if not file_path.exists():
        job.status = VerificationStatus.failed.value
        job.updated_at = utc_now()
        db.commit()
        raise HTTPException(status_code=400, detail="Stored file is missing.")

    job.status = VerificationStatus.processing.value
    job.updated_at = utc_now()
    db.commit()

    ela_result = analyze_ela(str(file_path))
    metadata_result = analyze_metadata(str(file_path))
    signature_result = verify_signature_siamese(str(file_path))
    aggregation = aggregate_trust_score(ela_result, metadata_result, signature_result)

    summary = {
        "ela": ela_result,
        "metadata": metadata_result,
        "signature": signature_result,
        "aggregation": aggregation,
    }

    report = db.query(ForensicReport).filter(ForensicReport.job_id == job.id).first()
    if report is None:
        report = ForensicReport(
            job_id=job.id,
            integrity_score=aggregation["trust_score"],
            summary_json=json.dumps(summary),
            created_at=utc_now(),
        )
        db.add(report)
    else:
        report.integrity_score = aggregation["trust_score"]
        report.summary_json = json.dumps(summary)

    job.status = VerificationStatus.completed.value
    job.updated_at = utc_now()
    db.commit()
    db.refresh(report)

    return VerificationRunResponse(
        job_id=job.id,
        status=job.status,
        trust_score=aggregation["trust_score"],
        passed=aggregation["passed"],
        report_created_at=report.created_at,
    )


@app.get("/api/verify/jobs", response_model=VerificationJobListResponse)
def list_verification_jobs(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> VerificationJobListResponse:
    if status is not None:
        valid_statuses = {value.value for value in VerificationStatus}
        if status not in valid_statuses:
            raise HTTPException(status_code=400, detail="Invalid status filter.")

    query = db.query(VerificationJob)
    if status is not None:
        query = query.filter(VerificationJob.status == status)

    total = query.count()
    jobs = (
        query.order_by(VerificationJob.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return VerificationJobListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[
            VerificationJobListItem(
                job_id=job.id,
                original_filename=job.original_filename,
                status=job.status,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
            for job in jobs
        ],
    )


@app.get("/api/verify/{job_id}", response_model=VerificationStatusResponse)
def get_verification_status(
    job_id: str,
    db: Session = Depends(get_db),
) -> VerificationStatusResponse:
    job = db.query(VerificationJob).filter(VerificationJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Verification job not found.")

    return VerificationStatusResponse(
        job_id=job.id,
        original_filename=job.original_filename,
        status=job.status,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@app.get("/api/verify/{job_id}/report", response_model=ForensicReportResponse)
def get_forensic_report(
    job_id: str,
    db: Session = Depends(get_db),
) -> ForensicReportResponse:
    job = db.query(VerificationJob).filter(VerificationJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Verification job not found.")

    report = db.query(ForensicReport).filter(ForensicReport.job_id == job.id).first()
    if report is None:
        raise HTTPException(status_code=404, detail="Forensic report not found.")

    return ForensicReportResponse(
        job_id=job.id,
        status=job.status,
        trust_score=report.integrity_score,
        summary=json.loads(report.summary_json) if report.summary_json else None,
        report_created_at=report.created_at,
    )


@app.get("/api/reports", response_model=ForensicReportListResponse)
def list_forensic_reports(
    include_summary: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ForensicReportListResponse:
    total = db.query(ForensicReport).count()
    rows = (
        db.query(ForensicReport, VerificationJob)
        .join(VerificationJob, ForensicReport.job_id == VerificationJob.id)
        .order_by(ForensicReport.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items: list[ForensicReportListItem] = []
    for report, job in rows:
        summary: dict[str, Any] | None = None
        if include_summary and report.summary_json:
            summary = json.loads(report.summary_json)
        items.append(
            ForensicReportListItem(
                job_id=report.job_id,
                original_filename=job.original_filename,
                status=job.status,
                trust_score=report.integrity_score,
                report_created_at=report.created_at,
                summary=summary,
            )
        )

    return ForensicReportListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=items,
    )
