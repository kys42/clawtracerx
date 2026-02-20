"""
ocmon gateway — WebSocket RPC client for OpenClaw gateway.

Protocol (v3):
  1. Client opens WS to ws://host:port
  2. Server sends connect.challenge event (with nonce)
  3. Client sends "connect" req with minProtocol/maxProtocol=3, client info,
     device identity (Ed25519 signed), and auth token
  4. Server responds with hello-ok or error
  5. Client sends RPC requests, server sends responses + events
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

import websocket
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
    Encoding,
    PublicFormat,
)

OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"
DEVICE_IDENTITY_FILE = Path.home() / ".openclaw" / "identity" / "device.json"

PROTOCOL_VERSION = 3
CLIENT_ID = "gateway-client"
CLIENT_MODE = "backend"
ROLE = "operator"
SCOPES = ["operator.admin"]


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def load_gateway_config() -> dict:
    """Read host, port, token from ~/.openclaw/openclaw.json."""
    with open(OPENCLAW_CONFIG) as f:
        cfg = json.load(f)
    gw = cfg.get("gateway", {})
    auth = gw.get("auth", {})
    return {
        "host": "localhost",
        "port": gw.get("port", 18789),
        "token": auth.get("token", ""),
    }


def _load_device_identity() -> dict:
    """Load Ed25519 device identity from ~/.openclaw/identity/device.json."""
    with open(DEVICE_IDENTITY_FILE) as f:
        data = json.load(f)
    return {
        "deviceId": data["deviceId"],
        "publicKeyPem": data["publicKeyPem"],
        "privateKeyPem": data["privateKeyPem"],
    }


def _get_public_key_raw(public_key_pem: str) -> bytes:
    """Extract raw 32-byte Ed25519 public key from PEM (strip SPKI header)."""
    key = load_pem_public_key(public_key_pem.encode())
    raw = key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return raw


def _sign_payload(private_key_pem: str, payload: str) -> str:
    """Sign payload with Ed25519 private key, return base64url signature."""
    key = load_pem_private_key(private_key_pem.encode(), password=None)
    signature = key.sign(payload.encode("utf-8"))
    return _base64url_encode(signature)


def _build_device_auth_payload(
    device_id: str,
    client_id: str,
    client_mode: str,
    role: str,
    scopes: list[str],
    signed_at_ms: int,
    token: str,
    nonce: str | None = None,
) -> str:
    """Build the device auth payload string (v2 format with nonce)."""
    version = "v2" if nonce else "v1"
    parts = [
        version,
        device_id,
        client_id,
        client_mode,
        role,
        ",".join(scopes),
        str(signed_at_ms),
        token or "",
    ]
    if version == "v2":
        parts.append(nonce or "")
    return "|".join(parts)


def _connect() -> websocket.WebSocket:
    """Open WS connection and authenticate via protocol v3 with device identity."""
    cfg = load_gateway_config()
    identity = _load_device_identity()
    url = f"ws://{cfg['host']}:{cfg['port']}"

    ws = websocket.WebSocket()
    ws.settimeout(10)
    ws.connect(url)

    # 1. Receive connect.challenge event
    raw = ws.recv()
    challenge = json.loads(raw)
    if challenge.get("type") != "event" or challenge.get("event") != "connect.challenge":
        raise RuntimeError(f"Expected connect.challenge, got: {raw[:200]}")

    nonce = None
    payload = challenge.get("payload", {})
    if isinstance(payload, dict):
        nonce = payload.get("nonce")

    # 2. Build device auth
    signed_at_ms = int(time.time() * 1000)
    auth_payload = _build_device_auth_payload(
        device_id=identity["deviceId"],
        client_id=CLIENT_ID,
        client_mode=CLIENT_MODE,
        role=ROLE,
        scopes=SCOPES,
        signed_at_ms=signed_at_ms,
        token=cfg["token"],
        nonce=nonce,
    )
    signature = _sign_payload(identity["privateKeyPem"], auth_payload)
    public_key_raw = _get_public_key_raw(identity["publicKeyPem"])

    # 3. Send connect RPC
    connect_id = str(uuid4())
    connect_msg = {
        "type": "req",
        "id": connect_id,
        "method": "connect",
        "params": {
            "minProtocol": PROTOCOL_VERSION,
            "maxProtocol": PROTOCOL_VERSION,
            "client": {
                "id": CLIENT_ID,
                "version": "1.0.0",
                "platform": "darwin",
                "mode": CLIENT_MODE,
            },
            "role": ROLE,
            "scopes": SCOPES,
            "caps": [],
            "auth": {"token": cfg["token"]},
            "device": {
                "id": identity["deviceId"],
                "publicKey": _base64url_encode(public_key_raw),
                "signature": signature,
                "signedAt": signed_at_ms,
                "nonce": nonce,
            },
        },
    }
    ws.send(json.dumps(connect_msg))

    # 4. Receive auth response
    raw = ws.recv()
    resp = json.loads(raw)
    if resp.get("type") == "res" and resp.get("id") == connect_id:
        if not resp.get("ok", False):
            raise RuntimeError(f"Auth failed: {resp.get('error', {})}")
    else:
        raise RuntimeError(f"Unexpected connect response: {raw[:200]}")

    return ws


def rpc_call(method: str, params: dict, timeout: int = 30) -> dict:
    """Send an RPC request and return the response. New connection per call."""
    ws = _connect()
    try:
        ws.settimeout(timeout)
        req_id = str(uuid4())
        msg = {
            "type": "req",
            "id": req_id,
            "method": method,
            "params": params,
        }
        ws.send(json.dumps(msg))

        # Read responses until we get one matching our req id
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = ws.recv()
            resp = json.loads(raw)
            if resp.get("type") == "res" and resp.get("id") == req_id:
                if not resp.get("ok", False):
                    raise RuntimeError(f"RPC error ({method}): {resp.get('error', {})}")
                return resp.get("payload", {})
            # Skip events (heartbeat, state updates, etc.)
        raise TimeoutError(f"RPC timeout for {method}")
    finally:
        ws.close()


def send_agent_message(
    message: str,
    session_key: str,
    agent_id: str = "main",
    model: str = None,
    thinking: str = None,
    deliver: bool = False,
    extra_system_prompt: str = None,
    timeout: int = 120,
) -> dict:
    """Send a message via the agent RPC. deliver=False prevents channel delivery."""
    params = {
        "message": message,
        "sessionKey": session_key,
        "agentId": agent_id,
        "deliver": deliver,
        "timeout": timeout,
        "idempotencyKey": str(uuid4()),
    }
    if model:
        params["model"] = model
    if thinking:
        params["thinking"] = thinking
    if extra_system_prompt:
        params["extraSystemPrompt"] = extra_system_prompt
    return rpc_call("agent", params, timeout=timeout + 10)


def list_gateway_sessions(agent_id: str = None, limit: int = 30) -> list:
    """List sessions via sessions.list RPC."""
    params = {"limit": limit}
    if agent_id:
        params["agentId"] = agent_id
    result = rpc_call("sessions.list", params)
    return result.get("sessions", result) if isinstance(result, dict) else result


def patch_session(session_key: str, **kwargs) -> dict:
    """Patch session settings via sessions.patch RPC."""
    params = {"sessionKey": session_key}
    params.update(kwargs)
    return rpc_call("sessions.patch", params)


def reset_session(session_key: str) -> dict:
    """Reset session transcript via sessions.reset RPC."""
    return rpc_call("sessions.reset", {"sessionKey": session_key})


def list_models() -> list:
    """List available models via models.list RPC."""
    result = rpc_call("models.list", {})
    return result.get("models", result) if isinstance(result, dict) else result


def list_agents() -> list:
    """List agents via agents.list RPC."""
    result = rpc_call("agents.list", {})
    return result.get("agents", result) if isinstance(result, dict) else result
