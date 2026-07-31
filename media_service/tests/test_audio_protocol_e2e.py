from __future__ import annotations

from fastapi.testclient import TestClient

from media_service.app.config import Settings
from media_service.app.main import create_app


def _client():
    settings = Settings(
        media_database_url="sqlite+pysqlite:///:memory:",
        media_database_schema="study1_media",
        a_to_b_service_token="a-secret",
        study1_internal_api_key="b-secret",
        a_base_url="http://backend:5000",
        livekit_url="ws://livekit:7880",
        livekit_api_key="devkey",
        livekit_api_secret="test-livekit-secret-at-least-32-bytes",
    )
    return TestClient(create_app(settings))


def test_internal_rtc_metric_batch_updates_truthful_media_status():
    client = _client()
    headers = {"Authorization": "Bearer a-secret"}

    response = client.post(
        "/internal/rtc-metrics",
        headers=headers,
        json={
            "session_id": "session-1",
            "phase_version": 3,
            "participant_id": "principal-1",
            "role": "principal",
            "samples": [
                {
                    "rtt_ms": 28,
                    "jitter_ms": 4,
                    "packet_loss": 0,
                    "bitrate_kbps": 52,
                    "connection_state": "connected",
                }
            ],
        },
    )

    assert response.status_code == 202
    status = client.get(
        "/internal/sessions/session-1/status", headers=headers
    ).json()
    assert status["rtc"]["status"] == "healthy"
    assert status["components"]["asr"]["status"] == "unknown"
    assert status["asr"]["status"] == "unknown"
