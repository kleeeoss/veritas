# Veritas Backend Production Profile (Wave 1)

## Deployment profile
- Target: containerized deployment on government cloud or controlled on-prem clusters.
- Data-at-rest: database and artifact storage paths must be on encrypted volumes.
- Data-in-transit: terminate TLS at ingress and enforce HTTPS between external clients and API.

## Baseline controls implemented
- Versioned API routes under `/api/v1/*`.
- JWT-based authentication with role checks (`admin`, `reviewer`, `auditor`, `verifier`).
- Upload safety checks: strict MIME + file signature validation + file size limits.
- Idempotency support via `Idempotency-Key` for verification requests.
- Relational persistence for review workflow via SQLite.
- Artifact storage abstraction using filesystem-backed object path.
- Tamper-evident audit event chain with HMAC signatures.
- Health and readiness probes (`/health`, `/ready`).
- Async verification orchestration (`/api/v1/veritas/verify-async` + job status endpoint).
- Multi-engine detector outputs with versioned reason codes for traceability.
- Review escalation and history endpoints for auditor workflows.
- Model registry + activation + drift-summary APIs for lifecycle governance.

## Runtime configuration
- `VERITAS_JWT_SECRET`: HS256 verification key.
- `VERITAS_JWT_ISSUER`: optional issuer check.
- `VERITAS_JWT_AUDIENCE`: optional audience check.
- `VERITAS_DB_PATH`: SQLite database path.
- `VERITAS_ARTIFACT_DIR`: artifact storage base path.
- `MAX_UPLOAD_BYTES`: upload size limit.
- `MODEL_SERVER_URL`: ML inference endpoint.
- `MODEL_TIMEOUT_SECONDS`: model call timeout.
- `VERITAS_AUDIT_SIGNING_KEY`: HMAC key for audit signatures.

## Immediate next steps
- Replace SQLite with managed PostgreSQL.
- Move artifact storage to object storage (S3-compatible or equivalent).
- Replace shared-secret JWT with OIDC issuer validation and JWKS.
- Add immutable external audit sink (WORM storage or append-only log service).
