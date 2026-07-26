import pytest

from study1.models import Study1Phase
from study1.services import ActionNotAllowedInPhase, Study1ServiceError


RESEARCHER = {"participant_id": "researcher", "role": "researcher"}


def _created(memory_service):
    return memory_service.create_session(
        "study-one",
        materials_by_role={
            "principal": [{"title": "P only", "content": "principal secret"}],
            "teammate_1": [{"title": "T1 only", "content": "teammate one secret"}],
            "teammate_2": [{"title": "T2 only", "content": "teammate two secret"}],
        },
    )


def _identity(result, role):
    invite = next(item for item in result["invites"] if item["role"] == role)
    return {
        "session_id": invite["session_id"],
        "participant_id": invite["participant_id"],
        "role": role,
    }


def test_materials_are_filtered_only_by_authenticated_role(memory_service):
    result = _created(memory_service)
    session_id = result["session"]["session_id"]
    principal = memory_service.get_materials(session_id, "principal")
    teammate = memory_service.get_materials(session_id, "teammate_1")
    assert [item["content"] for item in principal] == ["principal secret"]
    assert [item["content"] for item in teammate] == ["teammate one secret"]
    assert "teammate one secret" not in str(principal)
    assert "principal secret" not in str(teammate)


def test_material_api_never_accepts_a_requested_role(memory_service, study1_client):
    result = _created(memory_service)
    tokens = {}
    for invite in result["invites"][:2]:
        exchanged = study1_client.post(
            f"/api/study1/invites/{invite['token']}/exchange"
        ).get_json()
        tokens[invite["role"]] = exchanged["token"]
    session_id = result["session"]["session_id"]
    principal_response = study1_client.get(
        f"/api/study1/sessions/{session_id}/me/materials?role=teammate_1",
        headers={"Authorization": f"Bearer {tokens['principal']}"},
    )
    teammate_response = study1_client.get(
        f"/api/study1/sessions/{session_id}/me/materials?role=principal",
        headers={"Authorization": f"Bearer {tokens['teammate_1']}"},
    )
    assert principal_response.get_json()["materials"][0]["content"] == "principal secret"
    assert teammate_response.get_json()["materials"][0]["content"] == "teammate one secret"


def test_wrong_phase_submission_returns_protocol_409_details(
    memory_service, study1_client
):
    result = _created(memory_service)
    invite = next(item for item in result["invites"] if item["role"] == "principal")
    exchange = study1_client.post(
        f"/api/study1/invites/{invite['token']}/exchange"
    ).get_json()
    response = study1_client.post(
        f"/api/study1/sessions/{invite['session_id']}/submissions/pre_vote",
        headers={"Authorization": f"Bearer {exchange['token']}"},
        json={"payload": {"choice": "A"}},
    )
    assert response.status_code == 409
    assert response.get_json()["error"] == "ACTION_NOT_ALLOWED_IN_PHASE"
    assert response.get_json()["current_phase"] == "SETUP"
    assert response.get_json()["required_phase"] == "PRE_VOTE"


def test_submission_locks_original_and_researcher_revision_preserves_it(
    memory_service,
):
    result = _created(memory_service)
    session_id = result["session"]["session_id"]
    principal = _identity(result, "principal")
    memory_service.advance(session_id, RESEARCHER, "MATERIAL_READING")
    original = memory_service.submit(
        session_id, principal, "material_ack", "ack-v1", {"ack": True}
    )
    with pytest.raises(Study1ServiceError) as locked:
        memory_service.submit(
            session_id, principal, "material_ack", "ack-v1", {"ack": False}
        )
    assert locked.value.code == "SUBMISSION_LOCKED"
    revision = memory_service.revise_submission(
        session_id,
        original["submission_id"],
        "researcher",
        "Corrected data-entry error",
        {"ack": False},
        "ack-v2",
    )
    assert revision["previous_submission_id"] == original["submission_id"]
    assert original["payload"] == {"ack": True}
    assert len(memory_service.repository.submissions) == 2


def test_advance_checks_prerequisites_and_force_requires_reason(memory_service):
    result = _created(memory_service)
    session_id = result["session"]["session_id"]
    memory_service.advance(session_id, RESEARCHER, "MATERIAL_READING")
    with pytest.raises(Study1ServiceError) as missing:
        memory_service.advance(session_id, RESEARCHER, "PRE_VOTE")
    assert missing.value.code == "PREREQUISITES_NOT_MET"
    with pytest.raises(Study1ServiceError) as no_reason:
        memory_service.advance(
            session_id, RESEARCHER, "PRE_VOTE", override=True, reason=""
        )
    assert no_reason.value.code == "OVERRIDE_REASON_REQUIRED"
    result = memory_service.advance(
        session_id,
        RESEARCHER,
        "PRE_VOTE",
        override=True,
        reason="Protocol exception",
    )
    assert result["session"]["phase"] == Study1Phase.PRE_VOTE.value
    assert [event["event_type"] for event in result["events"]] == [
        "override",
        "phase_transition",
    ]
