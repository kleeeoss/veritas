# Project Veritas: Forgery Detection System

**Veritas** is an AI-powered document verification system designed to combat fraud by detecting forged and tampered certificates. By combining Optical Character Recognition (OCR) with a robust image-classification model, Veritas determines the authenticity of a document from an image. This project was developed for the **Smart India Hackathon (SIH) 2025**.

---

## Key Features

- **AI-Powered Forgery Detection**  
    Utilizes a pre-trained ResNet model to analyze certificate images and produce a forgery confidence score.
    
- **OCR Text Extraction**  
    Automatically extracts all text from an uploaded certificate image for review and for inclusion in digitally-signed certificates.
    
- **Digital Certificate Issuance**  
    Genuine documents can be digitally signed using an ECDSA key pair, producing a verifiable, tamper-proof JSON certificate.
    
- **QR Code Generation**  
    A QR code is issued for every signed certificate for quick verification.
    
- **Dockerized Services**  
    The entire stack (backend API and ML model server) is containerized for straightforward setup and deployment.
    

---

## Final Repository Structure

```text
veritas-sih2025/
├── data/
│   └── synthetic/
│       └── veritas/
├── models/
│   └── veritas/
├── tools/
│   ├── pdf/
│   ├── qr/
│   └── signing/
├── veritas/
│   ├── backend/
│   │   ├── app/
│   │   │   └── main.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── frontend/
│   └── ml/
│       ├── model_server/
│       │   ├── Dockerfile
│       │   ├── requirements.txt
│       │   └── server.py
│       ├── ocr_pipeline.py
│       └── train.py
└── docker-compose.yml
```

---

## How to Run the Demo

The project is fully containerized using Docker and Docker Compose.

### Prerequisites

- Docker
    
- Docker Compose
    
- Git LFS (for handling large model files)
    

### 1. Clone the Repository

Make sure Git LFS is installed so model files are pulled correctly.

```bash
# Install Git LFS (if you haven't already)
sudo apt-get install git-lfs
git lfs install

# Clone the repo
git clone https://github.com/thatguygarv/veritas-sih2025.git
cd veritas-sih2025
```

### 2. Run the Application Stack

Use `docker-compose.yml` to build and run all services:

```bash
docker-compose up --build
```

This will start at least two services:

- **veritas-backend** — FastAPI application (default: `http://localhost:8002`)
    
- **veritas-model-server** — ML model server (default: `http://localhost:8001`)
    

After the services are up you can interact with the API endpoints or connect the frontend application to them.

### API Notes (Current)

- Health: `GET /health`
- Readiness: `GET /ready`
- Metrics (admin/auditor): `GET /metrics`
- Verify (v1): `POST /api/v1/veritas/verify`
- Verify Async (v1): `POST /api/v1/veritas/verify-async`
- Job Status (v1): `GET /api/v1/veritas/jobs/{job_id}`
- Review Queue (v1): `GET /api/v1/admin/reviews`
- Start Review (v1): `POST /api/v1/admin/reviews/{review_id}/start`
- Escalate Review (v1): `POST /api/v1/admin/reviews/{review_id}/escalate`
- Review History (v1): `GET /api/v1/admin/reviews/{review_id}/history`
- Review Decision (v1): `POST /api/v1/admin/reviews/{review_id}`
- Models Registry (v1): `GET /api/v1/models`
- Activate Model (v1): `POST /api/v1/models/{model_version}/activate`
- Drift Summary (v1): `GET /api/v1/models/drift-summary`

Most v1 endpoints require a Bearer JWT with `roles` claim (for example: `verifier`, `reviewer`, `admin`, `auditor`).

The verification pipeline now combines multiple detector engines (ML + OCR consistency + metadata/tamper checks + template rules + optional external verifier), returning detector-level scores, reason codes, and calibrated risk level.

### 3. (Optional) Re-train the Model

To retrain the forgery detection model with new data:

1. Place your dataset in `data/synthetic/veritas/` and include a `labels.csv` mapping.
    
2. Run the training script (inside a virtual environment or appropriate Python environment):
    

```bash
python veritas/ml/train.py
```

The trained model will be saved to:  
`models/veritas/v0/model_v0.pt`

You will need to restart the Docker containers to load the newly trained model.

---

## Notes & Tips

- Ensure large model files are handled by Git LFS to avoid incomplete clones.
    
- When issuing ECDSA-signed JSON certificates, keep private keys secure and consider hardware-backed key storage for production.
    
- Add monitoring and health checks for both backend and model-server containers when deploying to production.
    

---
