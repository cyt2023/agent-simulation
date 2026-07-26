import hashlib
import uuid
from datetime import datetime, timezone

from study1.media_gateway import MockMediaGateway
from study1.services import Study1Service


RESEARCHER = {"participant_id": "researcher", "role": "researcher"}


def _iso_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def test_mock_gateway_command_is_idempotent(memory_service):
    session_id = memory_service.create_session("media")["session"]["session_id"]
    snapshot = memory_service.repository.sessions[session_id]
    snapshot["phase"] = "PROXY_MEETING"
    snapshot["phase_version"] = 5
    command_id = str(uuid.uuid4())
    first = memory_service.issue_media_command(
        session_id, RESEARCHER, "START_PROXY_MEETING", command_id=command_id
    )
    second = memory_service.issue_media_command(
        session_id, RESEARCHER, "START_PROXY_MEETING", command_id=command_id
    )
    assert first["command"]["phase_version"] == 5
    assert first["gateway"]["mode"] == "mock"
    assert second["duplicate"] is True
    assert len(memory_service.media_gateway.commands) == 1
    assert (
        len(
            [
                event
                for event in memory_service.repository.events
                if event["event_type"] == "media_command"
            ]
        )
        == 1
    )


def test_duplicate_media_event_is_not_processed_twice(memory_service):
    session_id = memory_service.create_session("media")["session"]["session_id"]
    snapshot = memory_service.repository.sessions[session_id]
    snapshot["phase"] = "PROXY_MEETING"
    snapshot["phase_version"] = 3
    envelope = {
        "event_id": str(uuid.uuid4()),
        "session_id": session_id,
        "phase_version": 3,
        "event_type": "MEETING_ENDED",
        "occurred_at": _iso_now(),
        "payload": {},
    }
    first = memory_service.receive_media_event(envelope)
    second = memory_service.receive_media_event(envelope)
    assert first["processed"] is True
    assert second["duplicate"] is True
    assert snapshot["completion"]["proxy_meeting_ended"] is True
    assert (
        len(
            [
                event
                for event in memory_service.repository.events
                if event["event_type"] == "media_event"
            ]
        )
        == 1
    )


def test_artifact_is_idempotent_and_summary_sets_readiness_only(memory_service):
    session_id = memory_service.create_session("artifact")["session"]["session_id"]
    content = "Neutral summary"
    artifact = {
        "artifact_id": str(uuid.uuid4()),
        "type": "summary",
        "version": "1",
        "content": content,
        "checksum": hashlib.sha256(content.encode()).hexdigest(),
        "created_at": _iso_now(),
        "generator_version": "mock-1",
        "metadata": {},
    }
    first = memory_service.create_artifact(session_id, artifact)
    second = memory_service.create_artifact(session_id, artifact)
    snapshot = memory_service.repository.sessions[session_id]
    assert first["created"] is True
    assert second["duplicate"] is True
    assert snapshot["completion"]["summary_artifact_ready"] is True
    assert snapshot["phase"] == "SETUP"
    assert len(memory_service.repository.artifacts) == 1


def test_internal_artifact_endpoint_requires_shared_secret(memory_service, study1_client):
    session_id = memory_service.create_session("artifact-api")["session"]["session_id"]
    content = "Summary from B"
    payload = {
        "artifact_id": str(uuid.uuid4()),
        "type": "summary",
        "version": "1",
        "content": content,
        "checksum": hashlib.sha256(content.encode()).hexdigest(),
        "generator_version": "mock-b",
    }
    denied = study1_client.post(
        f"/api/internal/study1/sessions/{session_id}/artifacts", json=payload
    )
    assert denied.status_code == 401
    accepted = study1_client.post(
        f"/api/internal/study1/sessions/{session_id}/artifacts",
        headers={"X-Study1-Internal-Key": "internal-test-key"},
        json=payload,
    )
    assert accepted.status_code == 201
    assert accepted.get_json()["artifact"]["type"] == "summary"
