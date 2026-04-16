# Veritas Wave 2 + Wave 3 Delivery Notes

## Implemented in this iteration

### Wave 2: Async orchestration + observability + review workflow
- Added async verification orchestration:
  - `POST /api/v1/veritas/verify-async`
  - `GET /api/v1/veritas/jobs/{job_id}`
  - In-process queue worker with persisted jobs in SQLite for restart recovery.
- Added model call resilience:
  - Retry policy with bounded backoff.
  - Circuit breaker with configurable open interval.
- Added operational observability:
  - Request ID propagation via `X-Request-Id`.
  - `/metrics` endpoint with queue/counter/drift snapshots.
  - Readiness expanded with model service state and circuit breaker status.
- Upgraded reviewer workflow:
  - Review statuses: `pending`, `in_review`, `escalated`, `resolved`.
  - Escalation endpoint and history tracking.

### Wave 3: Multi-engine forensics + model lifecycle
- Added detector aggregation pipeline:
  - ML classifier score from model server.
  - OCR consistency heuristic.
  - Metadata/tamper heuristic.
  - Template/rule check.
  - Optional external verification connector.
- Verification response now includes:
  - detector-level scores + versions.
  - calibrated aggregate risk and reason codes.
  - model version + trace id.
- Added model lifecycle APIs:
  - `GET /api/v1/models`
  - `POST /api/v1/models/{model_version}/activate`
  - `GET /api/v1/models/drift-summary`
- Added model metadata endpoint in model server (`GET /metadata`).

## Configuration knobs
- `MODEL_RETRIES`
- `MODEL_CB_FAIL_THRESHOLD`
- `MODEL_CB_OPEN_SECONDS`
- `MODEL_METADATA_URL`
- `EXTERNAL_VERIFY_URL`
- `ASYNC_QUEUE_MAX`

## Operational caveats
- Async queue worker is process-local; for HA production use an external broker and dedicated worker deployment.
- SQLite is used for baseline portability; production should migrate to managed PostgreSQL.
- Artifact storage is filesystem-backed; production should use object storage with immutable lifecycle policies.
