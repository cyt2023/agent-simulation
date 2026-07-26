from datetime import timedelta

import pytest

import study1.services as services_module
from study1.services import ActionNotAllowedInPhase, Study1ServiceError, utc_now


RESEARCHER = {"participant_id": "researcher", "role": "researcher"}


def _setup(memory_service):
    result = memory_service.create_session("review-study", minimum_review_seconds=10)
    identities = {
        invite["role"]: {
            "session_id": invite["session_id"],
            "participant_id": invite["participant_id"],
            "role": invite["role"],
        }
        for invite in result["invites"]
    }
    return result["session"]["session_id"], identities


def test_summary_is_unavailable_before_review(memory_service):
    session_id, identities = _setup(memory_service)
    with pytest.raises(ActionNotAllowedInPhase) as error:
        memory_service.get_review(session_id, identities["principal"])
    assert error.value.status == 409
    assert error.value.required_phase == "REVIEW"


def test_teammates_can_never_access_principal_review(memory_service):
    session_id, identities = _setup(memory_service)
    snapshot = memory_service.repository.sessions[session_id]
    snapshot["phase"] = "REVIEW"
    snapshot["completion"]["delegation_expectation:principal"] = True
    with pytest.raises(Study1ServiceError) as denied:
        memory_service.get_review(session_id, identities["teammate_1"])
    assert denied.value.code == "REVIEW_ACCESS_FORBIDDEN"
    assert denied.value.status == 403


def test_force_advance_does_not_bypass_delegation_expectation_gate(memory_service):
    session_id, identities = _setup(memory_service)
    snapshot = memory_service.repository.sessions[session_id]
    snapshot["phase"] = "REVIEW"
    with pytest.raises(Study1ServiceError) as denied:
        memory_service.get_review(session_id, identities["principal"])
    assert denied.value.code == "DELEGATION_EXPECTATION_REQUIRED"


def test_review_returns_summary_with_collapsed_transcript_and_logs_reading(
    memory_service, monkeypatch
):
    session_id, identities = _setup(memory_service)
    snapshot = memory_service.repository.sessions[session_id]
    snapshot["phase"] = "REVIEW"
    snapshot["completion"]["delegation_expectation:principal"] = True
    memory_service.repository.add_artifact_for_testing(
        {
            "artifact_id": "summary-1",
            "session_id": session_id,
            "type": "summary",
            "version": "1",
            "content": "Neutral summary",
        }
    )
    memory_service.repository.add_artifact_for_testing(
        {
            "artifact_id": "transcript-1",
            "session_id": session_id,
            "type": "transcript",
            "version": "1",
            "content": "Segment one\nSegment two",
        }
    )
    review = memory_service.get_review(session_id, identities["principal"])
    assert review["summary"]["content"] == "Neutral summary"
    assert review["transcript"]["content"].startswith("Segment")
    opened = services_module.utc_now()
    snapshot["review_opened_at"] = (
        opened - timedelta(seconds=11)
    ).isoformat().replace("+00:00", "Z")
    event = memory_service.log_review_ui_event(
        session_id,
        identities["principal"],
        "scroll_depth",
        {"max_depth": 5, "visible_segments": ["segment-1"]},
    )
    assert event["payload"]["max_depth"] == 1.0
    assert snapshot["completion"]["review_reading_recorded:principal"] is True
    assert snapshot["completion"]["minimum_review_time_met:principal"] is True


def test_cannot_enter_handoff_without_comprehension_submission(memory_service):
    session_id, _ = _setup(memory_service)
    snapshot = memory_service.repository.sessions[session_id]
    snapshot["phase"] = "COMPREHENSION_MEASUREMENT"
    with pytest.raises(Study1ServiceError) as denied:
        memory_service.advance(session_id, RESEARCHER, "HANDOFF")
    assert denied.value.code == "PREREQUISITES_NOT_MET"
