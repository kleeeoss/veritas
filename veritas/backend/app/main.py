import shutil
import requests
import logging # <-- Import logging module
from pathlib import Path
from typing import Optional


from fastapi import FastAPI, status, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

app = FastAPI(
    title="Veritas Backend API",
    description="API for Veritas document forgery detection.",
    version="0.1.0"
)
# --- CORS Configuration ---
origins = [
    "http://localhost:5173", # The URL of your React frontend
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# --- Pydantic Models (Corrected for Python 3.9) ---
class HealthCheck(BaseModel):
    status: str = "OK"

class VerificationResponse(BaseModel):
    filename: str
    content_type: str
    message: str
    ocr_data: Optional[dict] = None
    forgery_score: Optional[float] = None

MODEL_SERVER_URL = "http://veritas-model-server:8001/predict"

@app.get("/health", response_model=HealthCheck, status_code=status.HTTP_200_OK)
def get_health():
    logging.info("Health check endpoint was called.")
    return HealthCheck(status="OK")

@app.post("/veritas/verify", response_model=VerificationResponse, status_code=status.HTTP_201_CREATED)
async def verify_document(file: UploadFile = File(...)):
    logging.info(f"Received file for verification: {file.filename}")

    # --- Hardening: Input Validation ---
    if file.content_type not in ["image/jpeg", "image/png"]:
        logging.warning(f"Invalid file type uploaded: {file.content_type}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Please upload a JPEG or PNG image."
        )

    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
    file_path = upload_dir / file.filename

    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    forgery_score = None
    try:
        logging.info(f"Sending {file.filename} to model server for prediction.")
        with open(file_path, "rb") as f:
            files = {"file": (file.filename, f, file.content_type)}
            response = requests.post(MODEL_SERVER_URL, files=files)
            response.raise_for_status()
            
            data = response.json()
            forgery_score = data.get("forgery_score")
            logging.info(f"Received forgery score: {forgery_score} for {file.filename}")

    except requests.exceptions.RequestException as e:
        logging.error(f"Model service call failed: {e}")
        raise HTTPException(status_code=503, detail=f"Model service unavailable: {e}")

    return VerificationResponse(
        filename=file.filename,
        content_type=file.content_type,
        message="File processed successfully.",
        ocr_data={"status": "pending"},
        forgery_score=forgery_score
    )

