# In veritas/ml/ocr_pipeline.py
import pytesseract
from PIL import Image
import io

def extract_text_from_image(image_bytes: bytes) -> str:
    """
    Takes image data as bytes, uses Tesseract to perform OCR,
    and returns the extracted text as a single string.
    """
    try:
        # Open the image from the in-memory bytes
        image = Image.open(io.BytesIO(image_bytes))

        # Use pytesseract to extract text
        text = pytesseract.image_to_string(image)

        return text if text else "No text found."
    except Exception as e:
        print(f"OCR Error: {e}")
        return "Error during OCR processing."