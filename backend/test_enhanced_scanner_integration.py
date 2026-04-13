"""
Integration checks for scanner API, SSE compatibility and hand-tracking websocket.

These tests are opt-in and run only when a backend server is already running.
Set `INSIGHTGRAPH_URL` (default: http://localhost:8000).
"""

from __future__ import annotations

import os
import time
import json

import httpx
import pytest

BASE_URL = os.getenv("INSIGHTGRAPH_URL", "http://localhost:8000")


def _server_available() -> bool:
    try:
        resp = httpx.get(f"{BASE_URL}/api/health", timeout=2.0)
        return resp.status_code in (200, 503)
    except Exception:
        return False


def _skip_if_offline() -> None:
    if not _server_available():
        pytest.skip("InsightGraph server not running for integration test")


def test_scan_status_endpoint_contract():
    _skip_if_offline()
    resp = httpx.get(f"{BASE_URL}/api/scan/status", timeout=10.0)
    assert resp.status_code == 200
    payload = resp.json()
    assert "status" in payload
    assert "scanned_files" in payload
    assert "total_files" in payload


def test_scan_start_and_cancel_contract():
    _skip_if_offline()
    start = httpx.post(
        f"{BASE_URL}/api/scan",
        json={"mode": "local", "paths": ["./backend"]},
        timeout=20.0,
    )
    assert start.status_code == 202
    cancel = httpx.post(f"{BASE_URL}/api/scan/cancel", timeout=10.0)
    assert cancel.status_code == 200
    assert "cancelled" in cancel.json()


def test_sse_event_stream_reachable():
    _skip_if_offline()
    with httpx.stream("GET", f"{BASE_URL}/api/events", timeout=10.0) as resp:
        assert resp.status_code == 200
        deadline = time.time() + 3
        lines = []
        for line in resp.iter_lines():
            if line:
                lines.append(line)
            if time.time() > deadline:
                break
    # stream may be idle, but endpoint should be readable and non-crashing
    assert isinstance(lines, list)


def test_hand_tracking_websocket_reachable():
    _skip_if_offline()
    websockets = pytest.importorskip("websockets")
    ws_url = BASE_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws/hand-tracking"

    async def _run():
        async with websockets.connect(ws_url, open_timeout=5, close_timeout=5) as ws:
            await ws.send(json.dumps({"type": "frame", "image_base64": "", "client_ts": int(time.time() * 1000)}))
            _ = await ws.recv()

    import asyncio

    asyncio.run(_run())
