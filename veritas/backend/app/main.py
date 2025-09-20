import requests
import logging
import tempfile
from pathlib import Path
from typing import Optional

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
    "http://localhost:5173",  # The URL of your React frontend
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

# --- Pydantic Models ---
class HealthCheck(BaseModel):
    status: str = "OK"

class VerificationResponse(BaseModel):
    filename: str
    content_type: str
    message: str
    forgery_score: Optional[float] = None
    heatmap: Optional[str] = None
    ocr_data: Optional[dict] = None

class CertificateResponse(BaseModel):
    status: str
    message: str

# --- API Endpoints ---
@app.get("/health", response_model=HealthCheck, status_code=status.HTTP_200_OK)
def get_health():
    """Provides a simple health check of the API."""
    logging.info("Health check endpoint was called.")
    return HealthCheck(status="OK")

@app.post("/veritas/verify", response_model=VerificationResponse, status_code=status.HTTP_200_OK)
async def verify_document(file: UploadFile = File(...)):
    """
    Receives an uploaded image, sends it to the ML model server for analysis,
    and returns the forgery score and a heatmap.
    """
    logging.info(f"Received file for verification: {file.filename}")

    # --- Input Validation ---
    if file.content_type not in ["image/jpeg", "image/png"]:
        logging.warning(f"Invalid file type uploaded: {file.content_type}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Please upload a JPEG or PNG image."
        )

    # Use a temporary file to handle the upload
    try:
        with tempfile.NamedTemporaryFile(delete=True, suffix=Path(file.filename).suffix) as temp_file:
            # Write the uploaded file content to the temporary file
            temp_file.write(await file.read())
            temp_file.seek(0) # Go back to the start of the file

            logging.info(f"Sending {file.filename} to model server for prediction.")
            
            # Prepare file for sending
            files = {"file": (file.filename, temp_file, file.content_type)}
            
            # Call the model server
            response = requests.post(MODEL_SERVER_URL, files=files, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            forgery_score = data.get("forgery_score")
            heatmap = data.get("heatmap") # Extract heatmap from response
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
        ocr_data={"status": "pending"} # Mock OCR data for now
    )

@app.post("/veritas/issue-certificate", response_model=CertificateResponse, status_code=status.HTTP_201_CREATED)
async def issue_certificate(payload: dict):
    """
    Placeholder endpoint for issuing a digital certificate.
    Accepts a JSON payload and returns a mock success message.
    """
    logging.info(f"Placeholder for /issue-certificate was called with payload: {payload}")
    return CertificateResponse(
        status="success",
        message="Certificate endpoint is ready for implementation."
    )