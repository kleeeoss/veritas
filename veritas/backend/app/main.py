# In veritas/backend/app/main.py
import requests
import logging
import json
import uuid
import base64
from pathlib import Path
from typing import Optional, List

# --- Tool Imports ---
from tools.signing.sign_helper import sign_data
from tools.qr.qr_generator import create_qr_code
from veritas.ml.ocr_pipeline import extract_text_from_image

from fastapi import FastAPI, status, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
app = FastAPI(title="Veritas Backend API", version="0.1.0")

# --- CORS Configuration ---
origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
app.add_middleware(
    CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

# --- Constants & Paths ---
MODEL_SERVER_URL = "http://veritas-model-server:8001/predict"
REVIEW_FILE_PATH = Path("/app/reviews/reviews.json")  # Path inside the container


# --- Pydantic Models ---
class HealthCheck(BaseModel): status: str = "OK"


class VerificationResponse(BaseModel):
    filename: str
    content_type: str
    message: str
    forgery_score: Optional[float] = None
    heatmap: Optional[str] = None
    ocr_text: Optional[str] = None
    needs_review: Optional[bool] = False


# --- NEW: Models for Admin Review ---
class ReviewItem(BaseModel):
    id: str
    filename: str
    image_data: str  # base64 encoded image
    forgery_score: float


class ReviewDecision(BaseModel):
    decision: str  # "approve" or "reject"


# --- API Endpoints ---
@app.get("/health", response_model=HealthCheck)
def get_health(): return HealthCheck(status="OK")


@app.post("/veritas/verify", response_model=VerificationResponse)
async def verify_document(file: UploadFile = File(...)):
    image_bytes = await file.read()
    ocr_result_text = extract_text_from_image(image_bytes)

    try:
        files = {"file": (file.filename, image_bytes, file.content_type)}
        response = requests.post(MODEL_SERVER_URL, files=files, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Model service unavailable: {e}")

    forgery_score = data.get("forgery_score")
    needs_review_flag = 0.4 <= forgery_score <= 0.6

    # --- NEW: Logic to save document for review ---
    if needs_review_flag:
        logging.info(f"Flagging {file.filename} for manual review.")
        review_id = str(uuid.uuid4())
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')

        new_review = ReviewItem(
            id=review_id,
            filename=file.filename,
            image_data=image_base64,
            forgery_score=forgery_score
        )

        reviews = []
        if REVIEW_FILE_PATH.exists():
            with open(REVIEW_FILE_PATH, "r") as f:
                reviews = json.load(f)

        reviews.append(new_review.dict())
        with open(REVIEW_FILE_PATH, "w") as f:
            json.dump(reviews, f, indent=2)

    return VerificationResponse(
        filename=file.filename,
        content_type=file.content_type,
        message="File processed successfully.",
        forgery_score=forgery_score,
        heatmap=data.get("heatmap"),
        ocr_text=ocr_result_text,
        needs_review=needs_review_flag
    )


# --- NEW: Admin Review Endpoints ---

@app.get("/admin/reviews", response_model=List[ReviewItem])
def get_reviews():
    """Returns the list of all documents currently needing manual review."""
    if not REVIEW_FILE_PATH.exists():
        return []
    with open(REVIEW_FILE_PATH, "r") as f:
        return json.load(f)


@app.post("/admin/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def process_review(review_id: str, decision: ReviewDecision):
    """Processes a decision for a reviewed document (removes it from the list)."""
    if not REVIEW_FILE_PATH.exists():
        raise HTTPException(status_code=404, detail="Review file not found.")

    with open(REVIEW_FILE_PATH, "r") as f:
        reviews = json.load(f)

    # Filter out the item that has been reviewed
    updated_reviews = [item for item in reviews if item['id'] != review_id]

    if len(updated_reviews) == len(reviews):
        raise HTTPException(status_code=404, detail="Review item not found.")

    with open(REVIEW_FILE_PATH, "w") as f:
        json.dump(updated_reviews, f, indent=2)

    logging.info(f"Processed review for {review_id} with decision: {decision.decision}")
    return