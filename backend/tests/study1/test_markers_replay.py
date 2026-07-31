import pytest

from study1.models import Study1Role
from study1.services import Study1ServiceError


RESEARCHER = {"participant_id": "researcher", "role": "researcher"}


def _participant(participant_id="p-1", role=Study1Role.PRINCIPAL.value):
    return {"participant_id": participant_id, "role": role}


def _session_id(memory_service):
    return memory_service.create_session("markers")["session"]["session_id"]


def test_researcher_private_marker_is_not_returned_to_participants(memory_service):
    session_id = _session_id(memory_service)
    marker = memory_service.create_marker(
        session_id,
        RESEARCHER,
        {
            "type": "technical",
            "start_ms": 30_000,
            "end_ms": 35_000,
            "reason": "ASR dropped briefly.",
            "participant_visible": False,
        },
    )

    participant_markers = memory_service.list_markers(
        session_id, _participant("principal-1")
    )
    researcher_markers = memory_service.list_markers(session_id, RESEARCHER)

    assert participant_markers == []
    assert researcher_markers[0]["marker_id"] == marker["marker_id"]


def test_participant_marker_requires_registered_type(memory_service):
    session_id = _session_id(memory_service)

    with pytest.raises(Study1ServiceError) as error:
        memory_service.create_marker(
            session_id,
            _participant("t1", Study1Role.TEAMMATE_1.value),
            {
                "type": "technical",
                "start_ms": 10_000,
                "end_ms": 11_000,
                "reason": "This should be researcher-only.",
            },
        )

    assert error.value.code == "INVALID_MARKER_TYPE"


def test_replay_merges_overlapping_context_windows(memory_service):
    session_id = _session_id(memory_service)
    first = memory_service.create_marker(
        session_id,
        _participant("t1", Study1Role.TEAMMATE_1.value),
        {
            "type": "key_decision",
            "start_ms": 30_000,
            "end_ms": 30_000,
            "reason": "Team started converging.",
            "segment_ids": ["u-1"],
            "recording_ids": ["rec-1"],
        },
    )
    second = memory_service.create_marker(
        session_id,
        _participant("t2", Study1Role.TEAMMATE_2.value),
        {
            "type": "unexpected",
            "start_ms": 35_000,
            "end_ms": 35_000,
            "reason": "New evidence changed the rationale.",
            "segment_ids": ["u-2"],
            "recording_ids": ["rec-1"],
        },
    )

    replay = memory_service.generate_replay_plan(
        session_id,
        RESEARCHER,
        {
            "marker_ids": [first["marker_id"], second["marker_id"]],
            "context_seconds": 10,
        },
    )

    assert replay["version"] == "1"
    assert [
        (item["start_second"], item["end_second"]) for item in replay["items"]
    ] == [(20, 45)]
    assert replay["items"][0]["marker_ids"] == [first["marker_id"], second["marker_id"]]


def test_marker_routes_filter_private_researcher_markers(
    study1_client, token_manager, memory_service
):
    result = memory_service.create_session("marker-routes")
    session_id = result["session"]["session_id"]
    principal = next(invite for invite in result["invites"] if invite["role"] == "principal")
    researcher_token = token_manager.issue_researcher()
    principal_token = token_manager.issue_participant(
        session_id,
        principal["participant_id"],
        "principal",
    )

    created = study1_client.post(
        f"/api/study1/sessions/{session_id}/markers",
        headers={"Authorization": f"Bearer {researcher_token}"},
        json={
            "type": "technical",
            "start_ms": 1_000,
            "end_ms": 2_000,
            "reason": "Network handoff check.",
            "participant_visible": False,
        },
    )
    participant_list = study1_client.get(
        f"/api/study1/sessions/{session_id}/markers",
        headers={"Authorization": f"Bearer {principal_token}"},
    )
    researcher_list = study1_client.get(
        f"/api/study1/sessions/{session_id}/markers",
        headers={"Authorization": f"Bearer {researcher_token}"},
    )

    assert created.status_code == 201
    assert participant_list.get_json()["markers"] == []
    assert researcher_list.get_json()["markers"][0]["type"] == "technical"
