# Veritas SIH 2025

AI-powered document authenticity verification platform for forged/tampered certificate detection.

Veritas combines ML classification, OCR-based consistency checks, metadata/tamper heuristics, and rule-based validation to deliver explainable risk scoring, async verification workflows, and auditable manual review operations.

---

## Table of Contents

- [Overview](#overview)
- [What’s Implemented](#whats-implemented)
- [System Architecture](#system-architecture)
- [Repository Structure](#repository-structure)
- [Quick Start (Docker)](#quick-start-docker)
- [Local Development](#local-development)
- [Authentication and Roles](#authentication-and-roles)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Testing and Validation](#testing-and-validation)
- [Security and Hardening](#security-and-hardening)
- [Operations Notes](#operations-notes)
- [Troubleshooting](#troubleshooting)
- [Future Wave 4 Directions](#future-wave-4-directions)

---

## Overview

Veritas is designed for institutions that need trusted, explainable certificate verification. The platform accepts document images, computes a calibrated forgery risk score, provides detector-level evidence, and routes uncertain cases into a reviewer workflow.

Current implementation emphasizes:

- **Detection quality** through multi-engine scoring.
- **Operational resilience** through retries, circuit breaker, and readiness/metrics.
- **Auditability** through signed audit event chaining and review history tracking.
- **Scalability path** through async job APIs and persistent queue state.

---

## What’s Implemented

### Wave 1 foundation

- File validation (type, signature, size).
- JWT role-based authorization.
- OCR extraction and ML inference integration.
- Manual review queue with decision endpoints.

### Wave 2

- Async verification APIs:
  - `POST /api/v1/veritas/verify-async`
  - `GET /api/v1/veritas/jobs/{job_id}`
- Persisted jobs in SQLite with restart recovery.
- Model-call retries and circuit breaker.
- Request trace propagation (`X-Request-Id`).
- Enhanced readiness + operational metrics.
- Review lifecycle upgrades (`pending`, `in_review`, `escalated`, `resolved`).

### Wave 3

- Multi-engine detector aggregation:
  - ML classifier
  - OCR consistency heuristic
  - metadata/tamper heuristic
  - template/rule checks
  - optional external verifier connector
- Detector-level reason codes and model/version metadata in verification output.
- Model lifecycle APIs:
  - list model registry
  - activate model version
  - drift summary
- Model server metadata endpoint (`GET /metadata`).

---

## System Architecture

### Core services

1. **Backend API (FastAPI)**
   - Main orchestration layer
   - AuthN/AuthZ
   - Verification orchestration (sync + async)
   - Review workflow
   - Audit and metrics

2. **Model Server (FastAPI + PyTorch)**
   - ResNet-based binary forgery scoring
   - Heatmap generation
   - Model metadata exposure

3. **Frontend (React + Vite)**
   - Verification UI
   - Admin/reviewer queue UI
   - Async job polling and triage actions

### Data and artifacts

- **SQLite**: reviews, jobs, idempotency, audit events, model registry, drift outcomes.
- **Filesystem artifacts**: uploaded documents and review images.

---

## Repository Structure

```text
veritas-sih2025/
├── data/
│   ├── artifacts/
│   ├── reviews/
│   └── synthetic/
├── models/
│   └── veritas/
├── tools/
│   ├── data_validator.py
│   ├── pdf/
│   ├── qr/
│   └── signing/
├── veritas/
│   ├── backend/
│   │   ├── app/main.py
│   │   ├── tests/
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── frontend/nullpoint-ui/
│   ├── ml/
│   │   ├── model_server/
│   │   │   ├── server.py
│   │   │   ├── requirements.txt
│   │   │   └── Dockerfile
│   │   ├── ocr_pipeline.py
│   │   ├── train.py
│   │   └── eval.py
│   └── docs/
└── docker-compose.yml
```

---

## Quick Start (Docker)

### Prerequisites

- Docker
- Docker Compose
- Git LFS (recommended for model assets)

### 1) Clone

```bash
git clone https://github.com/kleeeoss/veritas-sih2025.git
cd veritas-sih2025
```

### 2) Start services

```bash
docker-compose up --build
```

### 3) Service endpoints

- Backend API: `http://localhost:8002`
- Model server (direct): `http://localhost:8008`

> Note: model server runs on container port `8001` and is exposed on host `8008` by compose.

---

## Local Development

### Backend

```bash
cd /home/runner/work/veritas-sih2025/veritas-sih2025/veritas/backend
python -m pip install -r requirements.txt
PYTHONPATH=/home/runner/work/veritas-sih2025/veritas-sih2025/veritas/backend:/home/runner/work/veritas-sih2025/veritas-sih2025 \
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd /home/runner/work/veritas-sih2025/veritas-sih2025/veritas/frontend/nullpoint-ui
npm ci
npm run dev
```

Frontend expects backend base URL from:

- `VITE_API_BASE_URL` (default: `http://localhost:8002`)
- `VITE_VERITAS_BEARER_TOKEN` (optional static bearer token for local testing)

---

## Authentication and Roles

Most v1 endpoints require a JWT bearer token with a `roles` claim.

Supported roles:

- `verifier`
- `reviewer`
- `auditor`
- `admin`

Access is enforced server-side per endpoint.

---

## API Reference

### Health / Ops

- `GET /health`
- `GET /ready`
- `GET /metrics` *(admin/auditor)*

### Verification

- `POST /api/v1/veritas/verify` *(sync)*
- `POST /api/v1/veritas/verify-async` *(returns `job_id`)*
- `GET /api/v1/veritas/jobs/{job_id}`

Verification response includes:

- calibrated `forgery_score`
- `risk_level`
- `reason_codes`
- `detectors[]` with detector version, score, confidence
- `model_version`
- `trace_id`

### Review workflow

- `GET /api/v1/admin/reviews`
- `POST /api/v1/admin/reviews/{review_id}/start`
- `POST /api/v1/admin/reviews/{review_id}/escalate`
- `GET /api/v1/admin/reviews/{review_id}/history`
- `POST /api/v1/admin/reviews/{review_id}` *(approve/reject)*

### Model lifecycle

- `GET /api/v1/models`
- `POST /api/v1/models/{model_version}/activate`
- `GET /api/v1/models/drift-summary`

### Model server (direct)

- `POST /predict`
- `GET /metadata`

---

## Configuration

Important backend environment variables:

| Variable | Purpose | Default |
|---|---|---|
| `MODEL_SERVER_URL` | ML prediction endpoint | `http://veritas-model-server:8001/predict` |
| `MODEL_METADATA_URL` | ML metadata endpoint | `http://veritas-model-server:8001/metadata` |
| `EXTERNAL_VERIFY_URL` | Optional external verifier | empty |
| `VERITAS_DB_PATH` | SQLite DB path | `/app/reviews/veritas.db` |
| `VERITAS_ARTIFACT_DIR` | Artifact root | `/app/artifacts/reviews` |
| `MAX_UPLOAD_BYTES` | Upload size limit | `10485760` |
| `MODEL_TIMEOUT_SECONDS` | Model call timeout | `30` |
| `MODEL_RETRIES` | Model call retries | `2` |
| `MODEL_CB_FAIL_THRESHOLD` | Circuit breaker fail threshold | `3` |
| `MODEL_CB_OPEN_SECONDS` | Breaker open interval | `20` |
| `ASYNC_QUEUE_MAX` | In-process queue max size | `1000` |
| `VERIFICATION_REVIEW_LOWER` | Review band lower threshold | `0.4` |
| `VERIFICATION_REVIEW_UPPER` | Review band upper threshold | `0.6` |
| `VERITAS_JWT_SECRET` | JWT signing secret | `dev-secret-change-me` |
| `VERITAS_JWT_ISSUER` | Optional JWT issuer validation | empty |
| `VERITAS_JWT_AUDIENCE` | Optional JWT audience validation | empty |
| `VERITAS_AUDIT_SIGNING_KEY` | Audit hash signature key | `dev-audit-key-change-me` |

---

## Testing and Validation

### Backend tests

```bash
cd /home/runner/work/veritas-sih2025/veritas-sih2025/veritas/backend
PYTHONPATH=/home/runner/work/veritas-sih2025/veritas-sih2025/veritas/backend:/home/runner/work/veritas-sih2025/veritas-sih2025 \
python -m unittest discover -s tests -v
```

### Frontend checks

```bash
cd /home/runner/work/veritas-sih2025/veritas-sih2025/veritas/frontend/nullpoint-ui
npm run lint
npm run build
```

---

## Security and Hardening

Current controls include:

- strict MIME + magic-byte file validation
- unsafe signature rejection for high-risk file types
- JWT validation (signature, expiry, issuer/audience when configured)
- role-based authorization per API surface
- idempotency key conflict detection
- signed, hash-chained audit events
- non-root users in backend/model Docker images

Production recommendations:

- rotate secrets and use secret manager/KMS
- move from SQLite to managed PostgreSQL
- move filesystem artifacts to object storage with retention policies
- put APIs behind gateway/WAF and enforce TLS + request quotas
- externalize async queue to Redis/Rabbit/Kafka for HA

---

## Operations Notes

- Async worker is currently process-local and suitable for single-instance or demo deployments.
- Readiness returns dependency status for DB, storage, model-service reachability, queue depth, and breaker state.
- Metrics endpoint provides operational counters plus drift snapshot to support monitoring dashboards.

---

## Troubleshooting

### Model service unavailable

- verify model container is running
- confirm `MODEL_SERVER_URL` and `MODEL_METADATA_URL`
- check breaker config (`MODEL_CB_FAIL_THRESHOLD`, `MODEL_CB_OPEN_SECONDS`)

### OCR issues

- ensure `tesseract-ocr` is installed in runtime
- test with higher-resolution, non-blurry input images

### Auth failures (401/403)

- verify bearer token signature/expiry
- ensure required roles exist in token `roles` claim

### Queue/job delays

- inspect `/metrics` queue depth
- validate artifact directory write permissions

---

## Future Wave 4 Directions

- External distributed queue + dedicated worker pool.
- Reviewer assignment/SLAs and notification channels.
- Feature store and model-quality monitoring beyond score drift.
- Stronger document-template profiling and issuer-specific policies.
- Full OpenAPI examples and generated SDKs.

---

## License / Ownership

Built for Smart India Hackathon 2025 context. Add explicit license metadata if public redistribution is intended.
