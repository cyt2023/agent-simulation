from fastapi.testclient import TestClient

from media_service.app.config import Settings
from media_service.app.health import HealthService
from media_service.app.main import create_app


def test_health_reports_service_and_schema():
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
    response = TestClient(create_app(settings)).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {
        "service": "study1-media",
        "status": "ok",
        "schema": "study1_media",
        "schema_version": "study1-media-v2",
    }


def test_asr_health_is_unknown_without_probe(repository):
    snapshot = HealthService(repository).snapshot()

    assert snapshot["asr"]["status"] == "unknown"


def test_failed_probe_is_never_reported_ready(repository):
    service = HealthService(repository)
    service.record_failure("asr", "ASR_PROVIDER_ERROR")

    assert service.snapshot()["asr"]["status"] == "failed"
    assert service.snapshot()["asr"]["last_error_code"] == "ASR_PROVIDER_ERROR"
