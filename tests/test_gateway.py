"""
Tests for clawtracerx.gateway — pure helper functions.
"""
from __future__ import annotations

from clawtracerx.gateway import _base64url_encode, _build_device_auth_payload


class TestBase64urlEncode:
    def test_url_safe_no_padding(self):
        result = _base64url_encode(b"\xff\xfe\xfd")
        assert "+" not in result
        assert "/" not in result
        assert "=" not in result

    def test_empty_bytes(self):
        result = _base64url_encode(b"")
        assert result == ""

    def test_known_value(self):
        # base64url("hello") = "aGVsbG8"
        assert _base64url_encode(b"hello") == "aGVsbG8"


class TestBuildDeviceAuthPayload:
    def test_v1_format_without_nonce(self):
        payload = _build_device_auth_payload(
            device_id="dev-123",
            client_id="gateway-client",
            client_mode="backend",
            role="operator",
            scopes=["operator.admin"],
            signed_at_ms=1700000000000,
            token="mytoken",
            nonce=None,
        )
        assert payload.startswith("v1|")
        parts = payload.split("|")
        assert parts[0] == "v1"
        assert parts[1] == "dev-123"
        assert parts[5] == "operator.admin"
        assert len(parts) == 8

    def test_v2_format_with_nonce(self):
        payload = _build_device_auth_payload(
            device_id="dev-456",
            client_id="gateway-client",
            client_mode="backend",
            role="operator",
            scopes=["operator.admin"],
            signed_at_ms=1700000000000,
            token="mytoken",
            nonce="abc123nonce",
        )
        assert payload.startswith("v2|")
        parts = payload.split("|")
        assert parts[-1] == "abc123nonce"
        assert len(parts) == 9
