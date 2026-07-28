from types import SimpleNamespace

import pytest

from media_service.app.config import Settings
from media_service.app.livekit_runtime import LiveKitRoomRuntime


@pytest.mark.asyncio
async def test_livekit_participant_events_are_forwarded_with_authoritative_role():
    seen = []

    async def consume(session_id, participant_id, role, state, metadata):
        seen.append((session_id, participant_id, role, state, metadata))

    settings = Settings(
        media_database_url="sqlite+pysqlite:///:memory:",
        media_database_schema="study1_media",
        a_to_b_service_token="a-secret",
        study1_internal_api_key="b-secret",
        livekit_api_key="devkey",
        livekit_api_secret="test-livekit-secret-at-least-32-bytes",
    )
    runtime = LiveKitRoomRuntime(settings, connection_consumer=consume)

    await runtime._emit_connection(
        "session-1",
        "study1-session-1-sync-v10",
        SimpleNamespace(identity="participant-1", name="teammate_1"),
        "connected",
    )

    assert seen == [
        (
            "session-1",
            "participant-1",
            "teammate_1",
            "connected",
            {"room_name": "study1-session-1-sync-v10"},
        )
    ]
