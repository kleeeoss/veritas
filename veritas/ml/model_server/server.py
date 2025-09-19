import random
from fastapi import FastAPI
from pydantic import BaseModel

class Prediction(BaseModel):
    """Defines the data shape for the model's prediction response."""
    filename: str = "stub_file.png"
    forgery_score: float

# Initialize the FastAPI application
app = FastAPI(title="Veritas Model Server")

@app.post("/predict", response_model=Prediction)
def predict():
    """
    A placeholder endpoint that simulates the ML model.
    It returns a random forgery score.
    """
    # Generate a random score between 0.0 and 1.0
    score = random.uniform(0.0, 1.0)
    # Return the score in the defined Pydantic model shape
    return Prediction(forgery_score=round(score, 4))
