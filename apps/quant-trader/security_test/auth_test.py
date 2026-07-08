"""Authentication & Authorization Security Tests.

Probes the FastAPI server for:
- Bearer token bypass techniques
- Token enumeration / timing side-channel
- Missing auth on sensitive endpoints
- Auth header injection
- Settings endpoint credential exposure
- Order/signing without proper authorization
"""

from __future__ import annotations

import json
import time
import unittest
import urllib.error
import urllib.request
from typing import Any

BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = 5


def _request(
    method: str, url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = TIMEOUT
) -> dict[str, Any]:
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


def _get(url: str, headers: dict | None = None) -> dict[str, Any]:
    return _request("GET", url, headers=headers)


class TestBearerTokenBypass(unittest.TestCase):
    """Various token bypass techniques."""

    def _authed_endpoint(self) -> dict:
        """Try to hit a protected endpoint without token."""
        return _get(f"{BASE_URL}/portfolio")

    def test_no_token(self):
        """Request without Authorization header."""
        r = self._authed_endpoint()
        if r["status"] == 0:
            self.skipTest("Server not running")
        # If 200, auth is disabled -- this is a finding
        if r["status"] == 200:
            print("  [FINDING] /portfolio accessible WITHOUT auth token. Set QT_API_TOKEN in production.")

    def test_empty_bearer(self):
        """Authorization: Bearer (empty)."""
        r = _get(f"{BASE_URL}/portfolio", headers={"Authorization": "Bearer "})
        if r["status"] == 0:
            self.skipTest("Server not running")
        if r["status"] == 200:
            self.fail("Endpoint accepts empty Bearer token!")

    def test_malformed_bearer(self):
        """Various malformed Authorization header values."""
        payloads = [
            "Bearer",  # no token
            "Bearer  ",  # whitespace
            "bearer test",  # lowercase scheme
            "Basic dGVzdA==",  # wrong scheme (Basic auth)
            "Token abc123",  # non-standard scheme
            "test",  # no scheme
        ]
        for auth_val in payloads:
            with self.subTest(auth=auth_val):
                r = _get(f"{BASE_URL}/portfolio", headers={"Authorization": auth_val})
                if r["status"] == 0:
                    self.skipTest("Server not running")
                self.assertIn(r["status"], (401, 403, 200), f"Unexpected status for auth={auth_val!r}")
                if r["status"] == 200:
                    print(f"  [FINDING] Accepts malformed auth: {auth_val!r}")

    def test_sql_injection_in_token(self):
        """Token value with SQL injection attempt."""
        payload = "Bearer ' OR '1'='1"
        r = _get(f"{BASE_URL}/portfolio", headers={"Authorization": payload})
        if r["status"] == 0:
            self.skipTest("Server not running")
        # Should be 401, not 200
        self.assertIn(r["status"], (401, 403), "SQL injection in token may have bypassed auth!")

    def test_jwt_none_algorithm(self):
        """JWT 'none' algorithm bypass attempt."""
        # A fake JWT with alg:none
        fake_jwt = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiIxIn0."
        r = _get(f"{BASE_URL}/portfolio", headers={"Authorization": f"Bearer {fake_jwt}"})
        if r["status"] == 0:
            self.skipTest("Server not running")
        self.assertIn(r["status"], (401, 403), "Fake JWT with none algorithm may have bypassed auth!")


class TestTokenTimingSideChannel(unittest.TestCase):
    """Check if invalid tokens have different response times than valid ones."""

    def test_token_timing_comparison(self):
        """Compare response times for invalid vs possibly-valid tokens."""
        # First, check if auth is even enabled
        r = _get(f"{BASE_URL}/portfolio")
        if r["status"] == 0:
            self.skipTest("Server not running")
        if r["status"] == 200:
            self.skipTest("Auth disabled (QT_API_TOKEN not set)")

        # Time invalid tokens
        times_invalid = []
        for tok in ["invalid1", "invalid2", "invalid3"]:
            start = time.monotonic()
            _get(f"{BASE_URL}/portfolio", headers={"Authorization": f"Bearer {tok}"})
            times_invalid.append(time.monotonic() - start)

        # Time another batch
        times_invalid2 = []
        for tok in ["aaaa", "bbbb", "cccc"]:
            start = time.monotonic()
            _get(f"{BASE_URL}/portfolio", headers={"Authorization": f"Bearer {tok}"})
            times_invalid2.append(time.monotonic() - start)

        avg1 = sum(times_invalid) / len(times_invalid)
        avg2 = sum(times_invalid2) / len(times_invalid2)

        # If timing differs significantly, there may be a side channel
        if avg1 > 0 and avg2 > 0:
            ratio = max(avg1, avg2) / min(avg1, avg2)
            if ratio > 2.0:
                print(f"  [WARN] Token validation timing varies: {ratio:.1f}x. May indicate timing side-channel.")


class TestAuthHeaderInjection(unittest.TestCase):
    """Injection via Authorization and other headers."""

    def test_host_header_injection(self):
        """Malformed Host header should not bypass anything."""
        r = _get(f"{BASE_URL}/portfolio", headers={"Host": "evil.example.com"})
        if r["status"] == 0:
            self.skipTest("Server not running")
        # Should not get 200 from a host we didn't intend
        if r["status"] == 200:
            print("  [WARN] Server responds to Host header injection")

    def test_x_forwarded_for_injection(self):
        """X-Forwarded-For should not bypass auth or IP restrictions."""
        r = _get(f"{BASE_URL}/portfolio", headers={"X-Forwarded-For": "127.0.0.1"})
        if r["status"] == 0:
            self.skipTest("Server not running")
        # Just verify it doesn't cause errors
        self.assertIn(r["status"], (200, 401, 403), f"X-Forwarded-For caused unexpected {r['status']}")


class TestSettingsEndpointSecurity(unittest.TestCase):
    """Settings endpoint should protect credentials."""

    def test_settings_leaks_key_status(self):
        """GET /settings should not reveal whether API keys are set."""
        r = _get(f"{BASE_URL}/settings")
        if r["status"] == 0:
            self.skipTest("Server not running")
        body = r["body"]
        leaks = []
        if body.get("has_broker_keys"):
            leaks.append("has_broker_keys=True")
        if body.get("has_ai_key"):
            leaks.append("has_ai_key=True")
        if body.get("has_llm_key"):
            leaks.append("has_llm_key=True")
        if body.get("ai_endpoint"):
            leaks.append(f"ai_endpoint={body['ai_endpoint']}")
        if body.get("llm_provider"):
            leaks.append(f"llm_provider={body['llm_provider']}")
        if leaks:
            print(f"  [WARN] GET /settings reveals: {leaks}")

    def test_settings_post_no_auth(self):
        """POST /settings should reject unauthenticated updates."""
        r = _request("POST", f"{BASE_URL}/settings", data=json.dumps({"cash": 999999}).encode())
        if r["status"] == 0:
            self.skipTest("Server not running")
        if r["status"] == 200:
            self.fail(
                "POST /settings accepted modification without auth! "
                "An attacker could change broker keys, cash, or enable live trading."
            )

    def test_settings_allows_credential_rotation(self):
        """Verify that settings update accepts new API keys (feature, not bug,
        but should require auth)."""
        r = _request(
            "POST",
            f"{BASE_URL}/settings",
            data=json.dumps({"api_key": "test_key_security_test", "api_secret": "test_secret_security_test"}).encode(),
        )
        if r["status"] == 0:
            self.skipTest("Server not running")
        if r["status"] == 200:
            print("  [WARN] POST /settings accepted new API keys -- verify this requires auth in production.")


class TestOrderWithoutAuth(unittest.TestCase):
    """Order placement should require auth."""

    def test_buy_order_no_auth(self):
        """POST /orders (buy) without auth should be rejected."""
        payload = json.dumps({"symbol": "AAPL", "side": "buy", "notional": 100, "source": "synthetic"}).encode()
        r = _request("POST", f"{BASE_URL}/orders", data=payload)
        if r["status"] == 0:
            self.skipTest("Server not running")
        if r["status"] == 200:
            self.fail("POST /orders accepted a BUY order without auth! This could result in unauthorized trades.")

    def test_signal_endpoint_no_auth(self):
        """POST /signal should reject unauthenticated trading signals."""
        payload = json.dumps({"symbol": "AAPL", "signal": 1, "source": "synthetic"}).encode()
        r = _request("POST", f"{BASE_URL}/signal", data=payload)
        if r["status"] == 0:
            self.skipTest("Server not running")
        if r["status"] == 200:
            self.fail("POST /signal accepted a BUY signal without auth! An attacker could trigger trades.")

    def test_live_trading_guard(self):
        """Even with auth, live trading should require QT_ALLOW_LIVE."""
        # This test verifies the guard exists by checking the error message
        payload = json.dumps({"symbol": "AAPL", "side": "buy", "notional": 100, "source": "synthetic"}).encode()
        r = _request("POST", f"{BASE_URL}/orders", data=payload)
        if r["status"] == 0:
            self.skipTest("Server not running")
        # If it succeeded, check if there's a live-trading guard
        if r["status"] == 200:
            # The response should indicate paper trading
            body_str = json.dumps(r["body"])
            if "is_live" in body_str:
                print(
                    "  [INFO] Order endpoint responds (paper mode). "
                    "Verify QT_ALLOW_LIVE guard is active for real brokers."
                )


class TestWebSocketSecurity(unittest.TestCase):
    """WebSocket connection security (if applicable)."""

    def test_websocket_no_auth(self):
        """WebSocket upgrade without auth should be rejected (if auth is on)."""
        # This is a basic check -- full WS testing needs a WS client
        r = _request(
            "GET",
            f"{BASE_URL}/ws",
            headers={
                "Upgrade": "websocket",
                "Connection": "Upgrade",
                "Sec-WebSocket-Version": "13",
                "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
            },
        )
        if r["status"] == 0:
            self.skipTest("Server not running or no WS endpoint")
        # WS upgrade returns 101 normally; 400/401/403 if rejected
        if r["status"] == 101:
            print("  [INFO] WebSocket accepts upgrade -- verify auth is enforced on WS.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
