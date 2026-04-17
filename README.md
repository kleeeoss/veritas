# Project Veritas (Rebuild)

Phase 1 scaffold completed:

- Clean-slate repository reset
- FastAPI backend initialized
- SQLAlchemy models added:
  - `VerificationJob`
  - `ForensicReport`
- Upload endpoint added:
  - `POST /api/verify/upload` (multipart file upload, local save, mock S3 metadata)

## Run locally

```bash
cd backend
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Set `DATABASE_URL` to your PostgreSQL connection string for production.  
Phase 1 defaults to a local SQLite file for quick startup.
