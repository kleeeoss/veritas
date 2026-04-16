import base64
import hashlib
import hmac
import importlib
import json
import os
import tempfile
import time
import unittest
from io import BytesIO
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from PIL import Image


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def create_jwt(secret: str, roles: list[str], sub: str = "test-user") -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": sub,
        "roles": roles,
        "iat": int(time.time()) - 1,
        "exp": int(time.time()) + 1800,
    }
    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url(sig)}"


def make_test_jpeg_bytes() -> bytes:
    buffer = BytesIO()
    image = Image.new("RGB", (800, 600), color=(200, 200, 200))
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


class TestApiSecurity(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["VERITAS_DB_PATH"] = os.path.join(self.tmpdir.name, "veritas.db")
        os.environ["VERITAS_ARTIFACT_DIR"] = os.path.join(self.tmpdir.name, "artifacts")
        os.environ["VERITAS_JWT_SECRET"] = "test-secret"
        os.environ["VERITAS_AUDIT_SIGNING_KEY"] = "test-audit-key"
        os.environ["MODEL_SERVER_URL"] = "http://example.invalid/predict"

        import app.main as main_module

        self.main = importlib.reload(main_module)
        self.client = TestClient(self.main.app)
        self.verifier_token = create_jwt("test-secret", ["verifier"])
        self.reviewer_token = create_jwt("test-secret", ["reviewer"])
        self.admin_token = create_jwt("test-secret", ["admin"])

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_health_endpoint_public(self) -> None:
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "OK")

    def test_verify_requires_bearer_token(self) -> None:
        res = self.client.post(
            "/api/v1/veritas/verify",
            files={"file": ("demo.jpg", b"\xff\xd8\xff\x00\x11", "image/jpeg")},
        )
        self.assertEqual(res.status_code, 401)

    def test_admin_reviews_requires_role(self) -> None:
        verifier_headers = {"Authorization": f"Bearer {self.verifier_token}"}
        res = self.client.get("/api/v1/admin/reviews", headers=verifier_headers)
        self.assertEqual(res.status_code, 403)

    def test_verify_rejects_content_type_signature_mismatch(self) -> None:
        headers = {"Authorization": f"Bearer {self.verifier_token}"}
        res = self.client.post(
            "/api/v1/veritas/verify",
            headers=headers,
            files={"file": ("demo.png", b"\xff\xd8\xff\x00\x11", "image/png")},
        )
        self.assertEqual(res.status_code, 415)

    def test_verify_idempotency_returns_same_response(self) -> None:
        headers = {
            "Authorization": f"Bearer {self.verifier_token}",
            "Idempotency-Key": "idem-key-1",
        }
        fake_model = {"forgery_score": 0.51, "heatmap": "abc==", "model_version": "v1"}

        with patch("app.main.extract_text_from_image", return_value="ocr-text"), patch(
            "app.main.call_model_service",
            new=AsyncMock(return_value=fake_model),
        ) as mocked_model:

            body = {"file": ("doc.jpg", make_test_jpeg_bytes(), "image/jpeg")}
            first = self.client.post("/api/v1/veritas/verify", headers=headers, files=body)
            second = self.client.post("/api/v1/veritas/verify", headers=headers, files=body)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(mocked_model.await_count, 1)
        self.assertIn("detectors", first.json())
        self.assertIn("risk_level", first.json())

    def test_reviewer_can_access_reviews(self) -> None:
        headers = {"Authorization": f"Bearer {self.reviewer_token}"}
        res = self.client.get("/api/v1/admin/reviews", headers=headers)
        self.assertEqual(res.status_code, 200)

    def test_async_job_completes(self) -> None:
        headers = {"Authorization": f"Bearer {self.verifier_token}", "Idempotency-Key": "job-1"}
        fake_model = {"forgery_score": 0.2, "heatmap": "abc==", "model_version": "v1"}
        body = {"file": ("doc.jpg", make_test_jpeg_bytes(), "image/jpeg")}
        with patch("app.main.extract_text_from_image", return_value="Certificate issued on 21/01/2026 for name"), patch(
            "app.main.call_model_service",
            new=AsyncMock(return_value=fake_model),
        ):
            queued = self.client.post("/api/v1/veritas/verify-async", headers=headers, files=body)
            self.assertEqual(queued.status_code, 202)
            job_id = queued.json()["job_id"]
            import asyncio

            asyncio.run(self.main.process_queued_job(job_id))
            for _ in range(10):
                status_res = self.client.get(
                    f"/api/v1/veritas/jobs/{job_id}", headers={"Authorization": f"Bearer {self.verifier_token}"}
                )
                self.assertEqual(status_res.status_code, 200)
                if status_res.json()["status"] == "completed":
                    self.assertIn("result", status_res.json())
                    return
                time.sleep(0.1)
            self.fail("Async job did not complete in time")

    def test_review_escalation_and_history(self) -> None:
        verifier_headers = {"Authorization": f"Bearer {self.verifier_token}"}
        reviewer_headers = {"Authorization": f"Bearer {self.reviewer_token}"}
        fake_model = {"forgery_score": 0.5, "heatmap": "abc==", "model_version": "v1"}
        body = {"file": ("doc.jpg", make_test_jpeg_bytes(), "image/jpeg")}
        with patch("app.main.extract_text_from_image", return_value="random text"), patch(
            "app.main.call_model_service",
            new=AsyncMock(return_value=fake_model),
        ):
            verify = self.client.post("/api/v1/veritas/verify", headers=verifier_headers, files=body)
            self.assertEqual(verify.status_code, 200)

        reviews = self.client.get("/api/v1/admin/reviews", headers=reviewer_headers).json()
        self.assertGreaterEqual(len(reviews), 1)
        review_id = reviews[0]["id"]

        esc = self.client.post(
            f"/api/v1/admin/reviews/{review_id}/escalate",
            headers={**reviewer_headers, "Content-Type": "application/json"},
            json={"reason": "Needs auditor decision"},
        )
        self.assertEqual(esc.status_code, 204)

        history = self.client.get(f"/api/v1/admin/reviews/{review_id}/history", headers=reviewer_headers)
        self.assertEqual(history.status_code, 200)
        actions = [item["action"] for item in history.json()]
        self.assertIn("escalated", actions)

    def test_models_endpoint_admin_only(self) -> None:
        forbidden = self.client.get("/api/v1/models", headers={"Authorization": f"Bearer {self.verifier_token}"})
        self.assertEqual(forbidden.status_code, 403)
        allowed = self.client.get("/api/v1/models", headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(allowed.status_code, 200)


if __name__ == "__main__":
    unittest.main()
