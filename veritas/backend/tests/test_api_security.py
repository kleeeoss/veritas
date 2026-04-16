import base64
import hashlib
import hmac
import importlib
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


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
        fake_payload = {"forgery_score": 0.51, "heatmap": "abc=="}

        with patch("app.main.extract_text_from_image", return_value="ocr-text"), patch(
            "app.main.requests.post"
        ) as mocked_post:
            mocked_post.return_value.raise_for_status.return_value = None
            mocked_post.return_value.json.return_value = fake_payload

            body = {"file": ("doc.jpg", b"\xff\xd8\xff\x00\x11", "image/jpeg")}
            first = self.client.post("/api/v1/veritas/verify", headers=headers, files=body)
            second = self.client.post("/api/v1/veritas/verify", headers=headers, files=body)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(mocked_post.call_count, 1)

    def test_reviewer_can_access_reviews(self) -> None:
        headers = {"Authorization": f"Bearer {self.reviewer_token}"}
        res = self.client.get("/api/v1/admin/reviews", headers=headers)
        self.assertEqual(res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
