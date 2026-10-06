from __future__ import annotations

import os
import time
from urllib.parse import quote
import requests


def get_vendor_risk(
    vendor_name: str,
    timeout_seconds: float = 3.0,
    retries: int = 2,
    backoff_factor: float = 0.3,
) -> dict:
    """Low-level API client with retries, timeout handling, and graceful error reporting."""
    base_url = os.getenv("VENDOR_RISK_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
    url = f"{base_url}/vendor-risk/{quote(vendor_name.strip(), safe='')}"

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, timeout=timeout_seconds)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return {
                    "error": "not_found",
                    "vendor_name": vendor_name,
                    "detail": f"Vendor '{vendor_name}' not found in vendor risk database",
                }
            elif response.status_code == 503:
                # Upstream outage - retry if attempts remain
                if attempt < retries:
                    time.sleep(backoff_factor * (2**attempt))
                    continue
                return {
                    "error": "unavailable",
                    "vendor_name": vendor_name,
                    "detail": response.json().get("detail", "Vendor-risk service unavailable"),
                }
            else:
                response.raise_for_status()
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(backoff_factor * (2**attempt))
                continue
            return {
                "error": "unavailable",
                "vendor_name": vendor_name,
                "detail": f"Connection/timeout error: {exc}",
            }
        except requests.RequestException as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(backoff_factor * (2**attempt))
                continue
            return {
                "error": "unavailable",
                "vendor_name": vendor_name,
                "detail": str(exc),
            }

    return {
        "error": "unavailable",
        "vendor_name": vendor_name,
        "detail": str(last_error) if last_error else "Request failed",
    }
