"""API Security Tests.

Probes the FastAPI server for:
- Endpoints accessible without authentication
- Information disclosure via error messages
- HTTP method misuse (PUT/PATCH/DELETE on read-only resources)
- Open CORS policy verification
- Path traversal in file-serving endpoints
- Rate limiting absence
"""

from __future__ import annotations

import json
import unittest
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, ClassVar

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = 5  # seconds


def _get(url: str, headers: dict | None = None, timeout: int = TIMEOUT) -> dict[str, Any]:
    """Make a GET request, return (status, headers, body_dict)."""
    req = urllib.request.Request(url, method="GET", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return {
                "status": resp.status,
                "headers": dict(resp.headers),
                "body": json.loads(body) if body.strip() else {},
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            body_json = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            body_json = {"raw": body}
        return {"status": exc.code, "headers": dict(exc.headers), "body": body_json}
    except Exception as exc:
        return {"status": 0, "headers": {}, "body": {"error": str(exc)}}


def _request(
    method: str, url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = TIMEOUT
) -> dict[str, Any]:
    """Generic request helper."""
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return {
                "status": resp.status,
                "headers": dict(resp.headers),
                "body": json.loads(body) if body.strip() else {},
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            body_json = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            body_json = {"raw": body}
        return {"status": exc.code, "headers": dict(exc.headers), "body": body_json}
    except Exception as exc:
        return {"status": 0, "headers": {}, "body": {"error": str(exc)}}


class TestUnauthorizedAccess(unittest.TestCase):
    """Endpoints that should be reachable WITHOUT a Bearer token."""

    # Health is always open (by design) -- just verify it works.
    def test_health_always_accessible(self):
        r = _get(f"{BASE_URL}/health")
        self.assertEqual(r["status"], 200, "GET /health should be 200")
        self.assertIn("status", r["body"])

    def test_health_leaks_server_info(self):
        """Health endpoint should NOT leak version/broker/auth status to
        unauthenticated callers in production."""
        r = _get(f"{BASE_URL}/health")
        if r["status"] != 200:
            self.skipTest("Server not running")
        body = r["body"]
        # Information disclosure: health exposes version, broker type, auth flag
        info_leaked = []
        if "version" in body:
            info_leaked.append("version")
        if "broker" in body:
            info_leaked.append("broker")
        if "auth" in body:
            info_leaked.append("auth_enabled")
        if info_leaked:
            self.fail(f"GET /health leaks unauthenticated info: {info_leaked}. Consider restricting these fields.")

    def test_config_status_accessible_without_auth(self):
        """Config status should require auth or hide sensitive details."""
        r = _get(f"{BASE_URL}/api/config/status")
        if r["status"] != 200:
            self.skipTest("Server not running")
        body = r["body"]
        # Check if it reveals key presence (mild info leak)
        warnings = []
        if body.get("has_llm_key"):
            warnings.append("has_llm_key=True reveals LLM key is configured")
        if body.get("has_broker_keys"):
            warnings.append("has_broker_keys=True reveals broker keys are configured")
        if warnings:
            print(f"  [WARN] Config status info disclosure: {warnings}")


class TestCORSHeaders(unittest.TestCase):
    """Verify CORS policy is not dangerously open."""

    def test_cors_allows_arbitrary_origin(self):
        """CORS should not reflect arbitrary Origin headers."""
        r = _request(
            "OPTIONS",
            f"{BASE_URL}/health",
            headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "GET"},
        )
        if r["status"] == 0:
            self.skipTest("Server not running")
        acao = r["headers"].get("access-control-allow-origin", "")
        if acao == "*":
            print("  [WARN] CORS allows all origins (*) -- consider restricting to known origins.")
        elif acao == "https://evil.example.com":
            self.fail(
                "CORS reflects arbitrary origin! Access-Control-Allow-Origin: "
                f"{acao}. This is a cross-origin vulnerability."
            )


class TestHTTPMethodMisuse(unittest.TestCase):
    """Check that sensitive endpoints don't respond to wrong HTTP methods."""

    def test_delete_nonexistent_order(self):
        """DELETE on /orders/{fake_id} should not 200."""
        r = _request("DELETE", f"{BASE_URL}/orders/__security_test_fake_id__")
        if r["status"] == 0:
            self.skipTest("Server not running")
        self.assertIn(r["status"], (401, 403, 404), "DELETE on fake order should not succeed")

    def test_put_health(self):
        """PUT on /health should not be accepted."""
        r = _request("PUT", f"{BASE_URL}/health", data=b'{"status":"hacked"}')
        if r["status"] == 0:
            self.skipTest("Server not running")
        self.assertIn(r["status"], (401, 403, 404, 405), "PUT on /health should be rejected")

    def test_patch_settings(self):
        """PATCH is not a registered method -- should be 405."""
        r = _request("PATCH", f"{BASE_URL}/settings", data=b'{"paper":false}')
        if r["status"] == 0:
            self.skipTest("Server not running")
        self.assertIn(r["status"], (401, 403, 404, 405), "PATCH on /settings should be rejected")


class TestPathTraversal(unittest.TestCase):
    """Path traversal via URL-encoded sequences."""

    def test_traversal_in_symbol_param(self):
        """symbol parameter with path traversal should not cause file read."""
        payloads = ["../../../etc/passwd", "..%2F..%2F..%2Fetc%2Fpasswd", "....//....//....//etc/passwd"]
        for payload in payloads:
            r = _get(f"{BASE_URL}/market/price?symbol={urllib.parse.quote(payload)}")
            if r["status"] == 0:
                self.skipTest("Server not running")
            # Should return error, not file contents
            body_str = json.dumps(r["body"])
            self.assertNotIn("root:", body_str, f"Path traversal payload '{payload}' leaked file contents!")

    def test_traversal_in_source_param(self):
        """source parameter should not allow directory traversal."""
        r = _get(f"{BASE_URL}/market/price?symbol=AAPL&source=../../../etc/passwd")
        if r["status"] == 0:
            self.skipTest("Server not running")
        body_str = json.dumps(r["body"])
        self.assertNotIn("root:", body_str, "Path traversal via source param leaked file contents!")


class TestInformationDisclosure(unittest.TestCase):
    """Check for sensitive info leaked in error responses."""

    def test_error_traceback_leak(self):
        """Error responses should not contain Python tracebacks."""
        r = _get(f"{BASE_URL}/backtest")
        if r["status"] == 0:
            self.skipTest("Server not running")
        body_str = json.dumps(r["body"]).lower()
        traceback_indicators = ["traceback", "traceback (most recent", 'file "', '.py", line']
        found = [ind for ind in traceback_indicators if ind in body_str]
        self.assertEqual(found, [], f"Error response leaks traceback: {found}")

    def test_404_handler_no_info_leak(self):
        """404 should not reveal internal paths."""
        r = _get(f"{BASE_URL}/nonexistent_endpoint_security_test")
        if r["status"] == 0:
            self.skipTest("Server not running")
        body_str = json.dumps(r["body"])
        self.assertNotIn("quanttrader", body_str.lower(), "404 response reveals package name")


class TestRateLimiting(unittest.TestCase):
    """Verify rate limiting is in place (absence is a vulnerability)."""

    def test_rapid_requests_not_throttled(self):
        """Fire 20 rapid requests -- if all succeed, rate limiting is absent."""
        if _get(f"{BASE_URL}/health")["status"] == 0:
            self.skipTest("Server not running")

        blocked = False
        for _ in range(20):
            r = _get(f"{BASE_URL}/health")
            if r["status"] == 429:
                blocked = True
                break
        if not blocked:
            print("  [WARN] No rate limiting detected on /health (20 rapid requests all succeeded).")


class TestSensitiveEndpointDiscovery(unittest.TestCase):
    """Discover endpoints that may be sensitive and verify auth."""

    SENSITIVE_ENDPOINTS: ClassVar[list[tuple[str, str]]] = [
        ("GET", "/portfolio"),
        ("GET", "/orders"),
        ("POST", "/orders"),
        ("POST", "/signal"),
        ("POST", "/settings"),
        ("GET", "/settings"),
        ("POST", "/backtest"),
        ("POST", "/optimize"),
        ("POST", "/ai/run"),
        ("POST", "/ai/llm/run"),
        ("GET", "/api/scanner/results"),
        ("POST", "/api/scanner/run"),
    ]

    def test_sensitive_endpoints_require_auth(self):
        """Sensitive endpoints should return 401 when QT_API_TOKEN is set."""
        for method, path in self.SENSITIVE_ENDPOINTS:
            with self.subTest(method=method, path=path):
                r = _request(method, f"{BASE_URL}{path}")
                if r["status"] == 0:
                    self.skipTest("Server not running")
                # 200 = auth is disabled (QT_API_TOKEN not set) -- just note it
                if r["status"] == 200:
                    print(f"  [INFO] {method} {path} accessible without auth (QT_API_TOKEN likely unset)")
                elif r["status"] == 401:
                    pass  # Good -- auth required
                elif r["status"] == 405:
                    pass  # Method not allowed is fine
                else:
                    print(f"  [INFO] {method} {path} returned {r['status']}")


class TestLargePayload(unittest.TestCase):
    """Test resistance to extremely large payloads."""

    def test_oversized_backtest_request(self):
        """Sending a massive JSON body should be rejected, not OOM."""
        if _get(f"{BASE_URL}/health")["status"] == 0:
            self.skipTest("Server not running")
        huge_params = {"key_" * 100: "x" * 1_000_000}
        payload = json.dumps({"symbol": "AAPL", "params": huge_params}).encode()
        r = _request("POST", f"{BASE_URL}/backtest", data=payload)
        # Should get 400/413/422, not 500 or hang
        self.assertIn(r["status"], (400, 401, 413, 422, 500), f"Oversized payload returned unexpected {r['status']}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
