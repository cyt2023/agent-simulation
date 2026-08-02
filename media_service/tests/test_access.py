import jwt
import pytest
import re

from media_service.app.access import AccessDenied, MediaAccessService
from media_service.app.config import Settings


@pytest.fixture
def access_service():
    return MediaAccessService(
        Settings(
            media_database_url="sqlite+pysqlite:///:memory:",
            media_database_schema="study1_media",
            a_to_b_service_token="a-secret",
            study1_internal_api_key="b-secret",
            a_base_url="http://backend:5000",
            livekit_url="ws://livekit:7880",
            livekit_api_key="devkey",
            livekit_api_secret="test-livekit-secret-at-least-32-bytes",
        )
    )


@pytest.mark.parametrize(
    ("phase", "role", "allowed"),
    [
        ("PROXY_MEETING", "principal", False),
        ("PROXY_MEETING", "teammate_1", True),
        ("PROXY_MEETING", "teammate_2", True),
        ("SYNC_MEETING", "principal", True),
        ("SYNC_MEETING", "teammate_1", True),
        ("SYNC_MEETING", "teammate_2", True),
        ("HANDOFF", "principal", True),
        ("HANDOFF", "teammate_1", True),
        ("HANDOFF", "teammate_2", True),
    ],
)
def test_access_matrix(access_service, phase, role, allowed):
    if not allowed:
        with pytest.raises(AccessDenied):
            access_service.issue_access("session-1", phase, 7, role, f"id-{role}")
        return

    result = access_service.issue_access(
        "session-1", phase, 7, role, f"id-{role}"
    )
    assert result.room_name == "study1-session-1-audio"
    assert result.captions_enabled is False
    assert result.token
    claims = jwt.decode(result.token, options={"verify_signature": False})
    expected_sources = [] if phase == "HANDOFF" else ["microphone"]
    assert claims["video"]["canPublishSources"] == expected_sources
    assert claims["video"]["canPublish"] is (phase != "HANDOFF")
    assert claims["video"]["canPublishData"] is False


def test_proxy_identity_cannot_join_sync_room(access_service):
    with pytest.raises(AccessDenied):
        access_service.issue_access(
            "session-1", "SYNC_MEETING", 7, "proxy", "proxy-session-1"
        )


def test_sync_recorder_token_is_subscribe_only(access_service):
    result = access_service.issue_recorder_access("session-1", 7)

    claims = jwt.decode(result.token, options={"verify_signature": False})
    assert claims["name"] == "recorder"
    assert claims["video"]["room"] == "study1-session-1-audio"
    assert claims["video"]["canSubscribe"] is True
    assert claims["video"]["canPublish"] is False


def test_recorder_identity_is_sanitized_and_bounded(access_service):
    result = access_service.issue_recorder_access(
        "unsafe session/../" + "x" * 200, 10
    )

    claims = jwt.decode(result.token, options={"verify_signature": False})
    identity = claims["sub"]
    assert re.fullmatch(r"recorder-[A-Za-z0-9_-]+", identity)
    assert len(identity) <= len("recorder-") + 96
