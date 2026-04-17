# Veritas
**Digital media integrity verification platform that closes the trust deficit with explainable forensic scoring.**

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?logo=sqlalchemy&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-Default-003B57?logo=sqlite&logoColor=white)
![PostgreSQL Ready](https://img.shields.io/badge/PostgreSQL-Production-4169E1?logo=postgresql&logoColor=white)
![Phase](https://img.shields.io/badge/Phase-5-success)

## Executive Summary
Digital-first ecosystems are struggling with a trust deficit: manipulated media, unverifiable artifacts, and weak provenance controls undermine operational confidence. Veritas addresses this by providing a structured verification workflow that ingests files, runs forensic analysis, and produces persistent trust reports with auditable status progression.

The platform’s value proposition is clear: teams can move from ad-hoc manual checks to a repeatable, API-driven trust pipeline. Veritas combines deterministic placeholder forensic engines (ELA, metadata analysis, and Siamese-signature checks) with weighted scoring and report history APIs, enabling downstream products to consume integrity intelligence consistently.

Today’s implementation is a clean FastAPI + SQLAlchemy backbone with Phase 5 capabilities, including job/report history listing and pagination. The architecture is production-aligned (PostgreSQL-ready, SQLite default) and structured for future integration with external trust layers such as blockchain notarization or national digital-authentication APIs.

## Core Features
- File upload intake for verification jobs (`POST /api/verify/upload`).
- Multi-engine forensic pipeline:
  - Error Level Analysis (ELA) scoring.
  - File metadata consistency scoring.
  - Siamese-signature verification scoring.
- Weighted trust-score aggregation (`aggregate_trust_score`) with pass/fail outcome.
- Persistent verification/report models:
  - `VerificationJob`
  - `ForensicReport`
- Status and single-report retrieval APIs:
  - `GET /api/verify/{job_id}`
  - `GET /api/verify/{job_id}/report`
- Phase 5 history APIs:
  - `GET /api/verify/jobs` (status filter + pagination)
  - `GET /api/reports` (pagination + optional summary expansion)

## System Architecture
```mermaid
graph TD
    A[Edge / Client App] --> B[Frontend Layer (Web / Next.js Client)]
    B --> C[FastAPI Backend<br/>/api/verify/*]
    C --> D[(SQL Database<br/>SQLite default / PostgreSQL prod)]
    C --> E[Forensics Core<br/>ELA + Metadata + Siamese]
    C -. optional integration .-> F[External Trust Layers<br/>Blockchain / NAD API]
    E --> C
    D --> C
    C --> B
    B --> A
```

**Microservice/layer summary**
- **Edge/Client:** End-user or operator interface initiating verification requests.
- **Frontend Layer:** Presentation/UI and API orchestration layer (not bundled in this repository snapshot).
- **FastAPI Backend:** Core orchestration for upload, verification runs, status/report retrieval, and history listing.
- **Forensics Core:** Modular analysis functions and trust-score aggregation logic.
- **Database Layer:** SQL persistence for jobs and forensic reports.
- **External Trust Layers (optional):** Reserved integration path for notarization/identity-verification systems.

## Tech Stack Snapshot
### Backend
- Python 3.11+
- FastAPI
- SQLAlchemy 2.x
- Uvicorn
- python-multipart

### Frontend
- Planned integration target: Next.js/React client
- **Current repository state:** frontend implementation is not present in this clone

### AI/ML Core
- ELA analysis module (deterministic placeholder implementation)
- Metadata analysis module (deterministic placeholder implementation)
- Siamese-signature verification module (deterministic placeholder implementation)
- Weighted trust-score aggregation engine

### Infrastructure
- SQLite (default local runtime)
- PostgreSQL-compatible configuration via `DATABASE_URL`
- Local filesystem upload storage (`UPLOAD_DIR`)

## Getting Started (Local Deployment)
### 1) Prerequisites
- **Git** 2.30+
- **Python** 3.11+ (3.12 tested)
- **pip** (latest recommended)
- **Node.js** 20+ and **npm** 10+ (for companion frontend, when available)
- **Docker Desktop / Docker Engine** 24+ (optional, for containerized local services)

### 2) Clone Repository
```bash
git clone https://github.com/kleeeoss/veritas.git
cd veritas
```

### 3) Backend Environment Setup
```bash
cd /home/runner/work/veritas/veritas/backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4) Environment Variables (`.env` template)
Create `/home/runner/work/veritas/veritas/backend/.env`:
```bash
DATABASE_URL=sqlite:///./veritas_phase1.db
UPLOAD_DIR=./uploads
```

Load variables in your shell:
```bash
set -a
source /home/runner/work/veritas/veritas/backend/.env
set +a
```

> For PostgreSQL, set `DATABASE_URL` to e.g.:
> `postgresql+psycopg://<user>:<password>@localhost:5432/veritas`

### 5) Start FastAPI Backend
```bash
cd /home/runner/work/veritas/veritas/backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Health check:
```bash
curl http://localhost:8000/health
```

### 6) Start Next.js Frontend (Companion App)
This repository currently does **not** include a frontend directory.  
If you have the companion Next.js client, start it with:
```bash
cd /path/to/frontend
npm install
npm run dev
```
Configure frontend API base URL to `http://localhost:8000`.

## Usage Flow
1. Upload a media/file artifact to create a verification job.
2. Receive `job_id` and storage metadata from the upload response.
3. Trigger the forensic run for that `job_id`.
4. Read real-time job status via the status endpoint.
5. Fetch the generated forensic report for detailed scoring output.
6. Query job/report history endpoints for monitoring, dashboards, and auditing.

## API Overview
| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Service health probe |
| POST | `/api/verify/upload` | Upload file and create verification job |
| POST | `/api/verify/{job_id}/run` | Execute forensic pipeline and persist report |
| GET | `/api/verify/{job_id}` | Get verification job status |
| GET | `/api/verify/{job_id}/report` | Get forensic report for a job |
| GET | `/api/verify/jobs` | List verification jobs (`status`, `limit`, `offset`) |
| GET | `/api/reports` | List forensic reports (`include_summary`, `limit`, `offset`) |

## License & Disclaimer
This project is intended for open-source distribution under the MIT model; add a `LICENSE` file before production or external redistribution if your organization has not yet finalized licensing.

**Disclaimer:** Veritas currently uses deterministic placeholder forensic engines for pipeline scaffolding. It is not a substitute for legally certified forensic examination, national digital-forensics standards, or judicial evidentiary procedures without additional validation, model hardening, and governance controls.
