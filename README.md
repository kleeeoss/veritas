# Project Veritas (Rebuild)

Phase 1, Phase 2, Phase 3, Phase 4, and Phase 5 scaffold completed:

- Clean-slate repository reset
- FastAPI backend initialized
- SQLAlchemy models added:
  - `VerificationJob`
  - `ForensicReport`
- Upload endpoint added:
  - `POST /api/verify/upload` (multipart file upload, local save, mock S3 metadata)
- Forensics pipeline module added with placeholder engines:
  - `analyze_ela(image_path)`
  - `analyze_metadata(file_path)`
  - `verify_signature_siamese(image_path)`
- Trust-score aggregation and report persistence added:
  - `aggregate_trust_score(...)`
  - `POST /api/verify/{job_id}/run`
- Phase 4 read APIs added:
  - `GET /api/verify/{job_id}` (job status)
  - `GET /api/verify/{job_id}/report` (forensic report)
- Phase 5 listing APIs added:
  - `GET /api/verify/jobs` (job history with pagination/filtering)
  - `GET /api/reports` (forensic report history with pagination)

## Run locally

```bash
cd backend
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Set `DATABASE_URL` to your PostgreSQL connection string for production.  
Phase 1 defaults to a local SQLite file for quick startup.
