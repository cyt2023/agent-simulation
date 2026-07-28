from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from media_service.app.config import Settings
from media_service.app.db import Database
from media_service.app.repository import MediaRepository


@pytest.fixture
def command_payload():
    return {
        "command_id": str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
        "phase_version": 5,
        "command": "START_PROXY_MEETING",
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "authorized_context": {
                "authorization_submission_id": str(uuid.uuid4()),
                "proxy_config_submission_id": str(uuid.uuid4()),
                "materials": [],
                "proxy_config": {"stance": "neutral"},
            }
        },
    }


@pytest.fixture
def repository():
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
    database = Database(settings)
    database.create_all()
    return MediaRepository(database)
