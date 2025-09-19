# projects/veritas/ml/ocr_pipeline.py

import re
import json
from PIL import Image
import pytesseract

# --- Placeholder Schema ---
# NOTE: This is a temporary structure. It MUST be updated once Garv commits
# the final 'meta/CERT_SCHEMA.json'.
CERTIFICATE_SCHEMA = {
    "student_name": None,
    "course_name": None,
    "completion_date": None,
    "issuing_authority": None
}

def extract_text_from_image(image_path: str) -> dict:
    """
    Processes an image of a certificate, extracts text using OCR,
    and parses it into a structured dictionary.

    Args:
        image_path: The full path to the certificate image file.

    Returns:
        A dictionary populated with extracted data, conforming to the schema.
        Returns a schema with None values if the image cannot be processed.
    """
    try:
        # Step 1: Open the image and perform OCR to get raw text
        img = Image.open(image_path)
        raw_text = pytesseract.image_to_string(img)

        # Step 2: Parse the raw text using regular expressions
        parsed_data = parse_raw_text(raw_text)
        return parsed_data

    except FileNotFoundError:
        print(f"❌ Error: Image file not found at {image_path}")
        return CERTIFICATE_SCHEMA
    except Exception as e:
        print(f"❌ An unexpected error occurred during OCR: {e}")
        return CERTIFICATE_SCHEMA

def parse_raw_text(text: str) -> dict:
    """
    Parses a block of raw text from OCR to find specific fields.
    """
    # NOTE: We're updating the schema to match the fields in the image.
    # We will need to confirm this structure with Garv.
    data = {
        "certificate_id": None,
        "completion_date": None,
        "student_name": None,      # Not present in this cert
        "course_name": None,       # Not present in this cert
        "issuing_authority": None  # Not present in this cert
    }

    # --- Updated Regex Patterns for 'genuine_0001.png' ---
    # Looks for "Certificate ID: 0001"
    id_pattern = re.compile(r"Certificate ID:\s*(\d+)", re.IGNORECASE)
    
    # Looks for "Date: 2025-09-11"
    date_pattern = re.compile(r"Date:\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)

    # --- Extraction Logic ---
    id_match = id_pattern.search(text)
    if id_match:
        data["certificate_id"] = id_match.group(1).strip()
    date_match = date_pattern.search(text)
    if date_match:
        data["completion_date"] = date_match.group(1).strip()

    return data


# --- Test Harness ---
# This block allows us to run this script directly for testing.
if __name__ == '__main__':
    # NOTE: Update this path to point to one of Sehaj's sample images.
    # Assuming the script is run from the project root.
# --- This is the correct line ---
    sample_image_path = "data/synthetic/veritas/genuine_0001.png"

    print(f"🔍 Processing image: {sample_image_path}")
    extracted_json = extract_text_from_image(sample_image_path)

    print("\n--- OCR Results ---")
    # Use json.dumps for a clean, JSON-formatted output
    print(json.dumps(extracted_json, indent=4))
    print("-------------------")