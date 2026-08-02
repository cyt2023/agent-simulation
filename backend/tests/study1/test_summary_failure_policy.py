import pytest


def test_retry_same_config_rejects_configuration_drift():
    from study1.summary_service import SummaryPolicyError, build_summary_failure_action

    with pytest.raises(SummaryPolicyError) as error:
        build_summary_failure_action(
            action="retry_same_config",
            reason="Provider recovered",
            frozen_config_checksum="abc",
            approved_config_checksum="changed",
            source_transcript_checksum="transcript",
            source_summary_version="1",
        )

    assert error.value.code == "SUMMARY_CONFIG_DRIFT"


def test_retry_same_config_builds_regenerate_summary_command_payload():
    from study1.summary_service import build_summary_failure_action

    action = build_summary_failure_action(
        action="retry_same_config",
        reason="Provider recovered",
        frozen_config_checksum="abc",
        approved_config_checksum="abc",
        source_transcript_checksum="transcript",
        source_summary_version="1",
    )

    assert action["media_command"] == "REGENERATE_SUMMARY"
    assert action["payload"]["reason"] == "Provider recovered"


def test_transcript_only_action_requires_reason():
    from study1.summary_service import SummaryPolicyError, build_summary_failure_action

    with pytest.raises(SummaryPolicyError) as error:
        build_summary_failure_action(action="transcript_only", reason="")

    assert error.value.code == "SUMMARY_ACTION_REASON_REQUIRED"


def test_summary_action_route_issues_retry_command(study1_client, token_manager, memory_service):
    result = memory_service.create_session("summary-action")
    session_id = result["session"]["session_id"]
    memory_service.repository.sessions[session_id]["phase"] = "REVIEW"
    headers = {"Authorization": "Bearer " + token_manager.issue_researcher()}

    response = study1_client.post(
        f"/api/study1/sessions/{session_id}/summary-actions",
        headers=headers,
        json={
            "action": "retry_same_config",
            "reason": "Provider recovered",
            "frozen_config_checksum": "abc",
            "approved_config_checksum": "abc",
            "source_transcript_checksum": "transcript",
            "source_summary_version": "1",
        },
    )

    assert response.status_code == 202
    assert memory_service.media_gateway.commands[-1]["command"] == "REGENERATE_SUMMARY"
