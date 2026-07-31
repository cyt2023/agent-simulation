import pytest


def test_summary_qa_records_private_researcher_error_fields():
    from study1.summary_service import InMemorySummaryQaStore, SummaryQaService

    service = SummaryQaService(store=InMemorySummaryQaStore())
    entry = service.record(
        session_id="session-1",
        summary_artifact_id="summary-1",
        researcher_id="researcher",
        ratings={
            "omission_error": True,
            "misattribution_error": False,
            "hallucination_error": False,
            "decision_status_error": True,
            "action_item_error": False,
            "note": "Missed a stated disagreement.",
        },
    )

    assert entry.private is True
    assert service.list_for_session("session-1")[0].ratings["omission_error"] is True


def test_summary_qa_rejects_missing_note_when_error_is_flagged():
    from study1.summary_service import InMemorySummaryQaStore, SummaryPolicyError, SummaryQaService

    service = SummaryQaService(store=InMemorySummaryQaStore())

    with pytest.raises(SummaryPolicyError) as error:
        service.record(
            session_id="session-1",
            summary_artifact_id="summary-1",
            researcher_id="researcher",
            ratings={"hallucination_error": True, "note": ""},
        )

    assert error.value.code == "SUMMARY_QA_NOTE_REQUIRED"


def test_summary_qa_route_persists_private_artifact(study1_client, token_manager, memory_service):
    result = memory_service.create_session("summary-qa")
    session_id = result["session"]["session_id"]
    memory_service.repository.add_artifact_for_testing(
        {
            "artifact_id": "summary-1",
            "session_id": session_id,
            "type": "summary",
            "version": "1",
            "content": "Neutral summary",
        }
    )
    headers = {"Authorization": "Bearer " + token_manager.issue_researcher()}

    response = study1_client.post(
        f"/api/study1/sessions/{session_id}/summary-qa",
        headers=headers,
        json={
            "summary_artifact_id": "summary-1",
            "ratings": {
                "omission_error": True,
                "misattribution_error": False,
                "hallucination_error": False,
                "decision_status_error": False,
                "action_item_error": False,
                "note": "Missing disagreement.",
            },
        },
    )

    assert response.status_code == 201
    artifacts = memory_service.repository.export_data(session_id)["artifacts"]
    assert artifacts[-1]["type"] == "summary_qa"
    assert artifacts[-1]["metadata"]["private_researcher_qa"] is True
