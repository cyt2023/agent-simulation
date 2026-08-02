from __future__ import annotations

from fastapi.testclient import TestClient

from media_service.app.config import Settings
from media_service.app.main import create_app


class FakeRuntime:
    async def start_proxy(self, session_id, phase_version, config):
        return None


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
        study1_release_id="study1-release-v1",
        study1_release_checksum="abc123",
    )
    return TestClient(create_app(settings, runtime_coordinator=FakeRuntime()))


def _command(release_id="study1-release-v1", checksum="abc123"):
    return {
        "command_id": "command-1",
        "session_id": "session-1",
        "phase_version": 5,
        "command": "START_PROXY_MEETING",
        "issued_at": "2026-07-31T00:00:00Z",
        "payload": {
            "release": {
                "release_id": release_id,
                "checksum": checksum,
            },
            "authorized_context": {
                "authorization_submission_id": "auth-1",
                "proxy_config_submission_id": "proxy-1",
                "materials": [],
                "proxy_config": {"stance": "neutral"},
            },
        },
    }


def test_media_service_rejects_release_checksum_drift():
    response = _client().post(
        "/internal/commands",
        headers={"Authorization": "Bearer a-secret"},
        json=_command(checksum="different"),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "RELEASE_CHECKSUM_MISMATCH"


def test_media_service_accepts_matching_release_identity():
    response = _client().post(
        "/internal/commands",
        headers={"Authorization": "Bearer a-secret"},
        json=_command(),
    )

    assert response.status_code == 202
    assert response.json()["accepted"] is True
