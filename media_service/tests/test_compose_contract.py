from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from media_service.app.config import Settings


def test_compose_wires_livekit_media_and_a_b_boundary():
    root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert {"postgres", "backend", "frontend", "livekit", "media-service"} <= set(services)
    media = services["media-service"]
    assert "study1_media" in media["environment"]["MEDIA_DATABASE_URL"]
    assert media["environment"]["MEDIA_DATABASE_SCHEMA"] == "study1_media"
    assert media["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert media["depends_on"]["livekit"]["condition"] == "service_healthy"

    backend = services["backend"]["environment"]
    assert backend["MEDIA_GATEWAY_MODE"] == "http"
    assert backend["MEDIA_SERVICE_URL"] == "http://media-service:8000"

    livekit_ports = " ".join(str(port) for port in services["livekit"]["ports"])
    assert "7880" in livekit_ports
    assert "7881" in livekit_ports
    assert "50000-50100" in livekit_ports
    assert services["livekit"]["healthcheck"]["test"] == [
        "CMD",
        "/livekit-server",
        "--version",
    ]


def test_example_environment_names_every_media_secret_without_real_values():
    root = Path(__file__).resolve().parents[2]
    content = (root / ".env.example").read_text(encoding="utf-8")
    for name in (
        "A_TO_B_SERVICE_TOKEN",
        "MEDIA_DATABASE_PASSWORD",
        "LIVEKIT_API_KEY",
        "LIVEKIT_API_SECRET",
    ):
        assert f"{name}=" in content


def test_production_settings_reject_placeholder_media_secrets():
    with pytest.raises(ValidationError, match="placeholder"):
        Settings(
            media_database_url="postgresql+psycopg://media:secret@postgres/study1",
            media_database_schema="study1_media",
            a_to_b_service_token="change-me-for-local-development",
            study1_internal_api_key="change-me-for-local-development",
            livekit_api_key="devkey",
            livekit_api_secret="change-me-for-local-development",
        )


def test_compose_has_no_default_for_media_access_secrets():
    root = Path(__file__).resolve().parents[2]
    content = (root / "docker-compose.yml").read_text(encoding="utf-8")
    for name in (
        "A_TO_B_SERVICE_TOKEN",
        "STUDY1_INTERNAL_API_KEY",
        "LIVEKIT_API_KEY",
        "LIVEKIT_API_SECRET",
        "MEDIA_DATABASE_PASSWORD",
    ):
        assert f"${{{name}:-" not in content
