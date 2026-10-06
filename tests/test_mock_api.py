from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from mock_api.app import app


class MockApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health(self):
        r = self.client.get('/health')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'ok')

    def test_known_vendor(self):
        r = self.client.get('/vendor-risk/BrandBoard')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['security_review_status'], 'not_completed')

    def test_forced_outage(self):
        r = self.client.get('/vendor-risk/NimbusAI')
        self.assertEqual(r.status_code, 503)

    def test_vendor_client_graceful_failure(self):
        from unittest.mock import patch
        from src.vendor_client import get_vendor_risk

        # Test graceful failure when API returns 503
        with patch('requests.get') as mock_get:
            mock_resp = unittest.mock.MagicMock()
            mock_resp.status_code = 503
            mock_resp.json.return_value = {"detail": "Upstream vendor assessment provider is temporarily unavailable."}
            mock_get.return_value = mock_resp

            result = get_vendor_risk("NimbusAI", retries=0)
            self.assertEqual(result.get("error"), "unavailable")
            self.assertIn("temporarily unavailable", result.get("detail", ""))

        # Test graceful failure on timeout
        import requests
        with patch('requests.get', side_effect=requests.Timeout("Connection timed out")):
            result = get_vendor_risk("SlowVendor", retries=0)
            self.assertEqual(result.get("error"), "unavailable")
            self.assertIn("Connection/timeout error", result.get("detail", ""))

    def test_vendor_client_not_found(self):
        from unittest.mock import patch
        from src.vendor_client import get_vendor_risk

        with patch('requests.get') as mock_get:
            mock_resp = unittest.mock.MagicMock()
            mock_resp.status_code = 404
            mock_get.return_value = mock_resp

            result = get_vendor_risk("UnknownVendor", retries=0)
            self.assertEqual(result.get("error"), "not_found")


if __name__ == '__main__':
    unittest.main()
