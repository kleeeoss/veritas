# In veritas/backend/app/main.py
import requests
import logging
import tempfile
from pathlib import Path
from typing import Optional

# --- Tool Imports ---
from tools.signing.sign_helper import sign_data
from tools.qr.qr_generator import create_qr_code

# --- NEW: Import our OCR function ---
from veritas.ml.ocr_pipeline import extract_text_from_image

from fastapi import FastAPI, status, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Veritas Backend API",
    description="API for Veritas document forgery detection.",
    version="0.1.0"
)

# --- CORS Configuration ---
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Constants ---
MODEL_SERVER_URL = "http://veritas-model-server:8001/predict"


# --- Pydantic Models (with ocr_data type updated) ---
class HealthCheck(BaseModel):
    status: str = "OK"


class VerificationResponse(BaseModel):
    filename: str
    content_type: str
    message: str
    forgery_score: Optional[float] = None
    heatmap: Optional[str] = None
    ocr_text: Optional[str] = None  # UPDATED: Changed from 'ocr_data' to 'ocr_text' for simplicity


# Models for Day 2 Certificate Issuance
class DocumentData(BaseModel):
    filename: str
    ocr_text: str
    timestamp: str


class FullCertificateResponse(BaseModel):
    original_data: DocumentData
    signature: str
    qr_code_image: str


# --- API Endpoints ---
@app.get("/health", response_model=HealthCheck, status_code=status.HTTP_200_OK)
def get_health():
    return HealthCheck(status="OK")


@app.post("/veritas/verify", response_model=VerificationResponse, status_code=status.HTTP_200_OK)
async def verify_document(file: UploadFile = File(...)):
    logging.info(f"Received file for verification: {file.filename}")

    if file.content_type not in ["image/jpeg", "image/png"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Please upload a JPEG or PNG image."
        )

    # Read the image content once
    image_bytes = await file.read()

    try:
        # --- NEW: Perform OCR on the image bytes ---
        ocr_result_text = extract_text_from_image(image_bytes)
        logging.info(f"OCR result for {file.filename}: {ocr_result_text[:100]}...")

        # Send to model server for prediction
        logging.info(f"Sending {file.filename} to model server for prediction.")
        files = {"file": (file.filename, image_bytes, file.content_type)}
        response = requests.post(MODEL_SERVER_URL, files=files, timeout=30)
        response.raise_for_status()

        data = response.json()
        forgery_score = data.get("forgery_score")
        heatmap = data.get("heatmap")
        logging.info(f"Received forgery score: {forgery_score} for {file.filename}")

    except requests.exceptions.RequestException as e:
        logging.error(f"Model service call failed: {e}")
        raise HTTPException(status_code=503, detail=f"Model service unavailable: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")

    return VerificationResponse(
        filename=file.filename,
        content_type=file.content_type,
        message="File processed successfully.",
        forgery_score=forgery_score,
        heatmap=heatmap,
        # --- NEW: Add the actual OCR result to the response ---
        ocr_text=ocr_result_text
    )


@app.post("/veritas/issue-certificate", response_model=FullCertificateResponse, status_code=status.HTTP_201_CREATED)
async def issue_certificate(document: DocumentData):
    logging.info(f"Issuing certificate for {document.filename}")

    document_payload = document.dict()
    signature = sign_data(document_payload)

    qr_data = {"data": document_payload, "signature": signature}
    qr_code_base64 = create_qr_code(qr_data)

    return FullCertificateResponse(
        original_data=document,
        signature=signature,
        qr_code_image=qr_code_base64
    )