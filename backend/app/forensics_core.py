import hashlib
from pathlib import Path
from typing import Any


def _seed(path: str) -> int:
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _mock_result(path: str, minimum_score: int = 55) -> dict[str, Any]:
    seed = _seed(path)
    confidence = minimum_score + (seed % (101 - minimum_score))
    passed = confidence >= 70

    x = 20 + (seed % 200)
    y = 20 + ((seed >> 3) % 200)
    width = 60 + ((seed >> 5) % 180)
    height = 30 + ((seed >> 7) % 120)

    return {
        "passed": passed,
        "confidence_score": float(confidence),
        "bounding_boxes": [[x, y, width, height]],
    }


def analyze_ela(image_path: str) -> dict[str, Any]:
    _ = Path(image_path)
    return _mock_result(image_path, minimum_score=50)


def analyze_metadata(file_path: str) -> dict[str, Any]:
    _ = Path(file_path)
    return _mock_result(file_path, minimum_score=60)


def verify_signature_siamese(image_path: str) -> dict[str, Any]:
    _ = Path(image_path)
    return _mock_result(image_path, minimum_score=45)


def aggregate_trust_score(
    ela_result: dict[str, Any],
    metadata_result: dict[str, Any],
    signature_result: dict[str, Any],
) -> dict[str, Any]:
    weights = {
        "ela": 0.4,
        "metadata": 0.2,
        "signature": 0.4,
    }

    ela_score = float(ela_result.get("confidence_score", 0.0))
    metadata_score = float(metadata_result.get("confidence_score", 0.0))
    signature_score = float(signature_result.get("confidence_score", 0.0))

    weighted_score = (
        ela_score * weights["ela"]
        + metadata_score * weights["metadata"]
        + signature_score * weights["signature"]
    )

    normalized_score = round(max(0.0, min(100.0, weighted_score)), 2)
    passed = normalized_score >= 70.0

    return {
        "trust_score": normalized_score,
        "passed": passed,
    }
