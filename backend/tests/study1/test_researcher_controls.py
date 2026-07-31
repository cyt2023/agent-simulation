import pytest

from study1.services import Study1ServiceError


RESEARCHER = {"participant_id": "researcher", "role": "researcher"}


def test_session_never_auto_starts(memory_service):
    created = memory_service.create_session("manual-start")
    session_id = created["session"]["session_id"]
    snapshot = memory_service.repository.sessions[session_id]
    assert snapshot["status"] == "waiting"
    assert snapshot["phase"] == "SETUP"
    assert not any(event["event_type"] == "session_start" for event in memory_service.repository.events)


def test_start_pause_resume_extend_and_terminate_are_audited(memory_service):
    created = memory_service.create_session("controls")
    session_id = created["session"]["session_id"]
    started = memory_service.control(session_id, RESEARCHER, "start")
    assert started["session"]["status"] == "running"
    assert started["session"]["phase"] == "MATERIAL_READING"
    memory_service.control(session_id, RESEARCHER, "pause")
    memory_service.control(session_id, RESEARCHER, "resume")
    extended = memory_service.control(
        session_id, RESEARCHER, "extend", {"seconds": 300}
    )
    assert extended["session"]["remaining_seconds"] == 300
    terminated = memory_service.control(
        session_id, RESEARCHER, "terminate", {"reason": "test complete"}
    )
    assert terminated["session"]["status"] == "terminated"
    types = [event["event_type"] for event in memory_service.repository.events]
    for expected in (
        "session_start",
        "phase_transition",
        "session_pause",
        "session_resume",
        "session_extend",
        "session_terminate",
    ):
        assert expected in types


def test_invalid_controls_are_rejected(memory_service):
    session_id = memory_service.create_session("invalid")["session"]["session_id"]
    with pytest.raises(Study1ServiceError) as denied:
        memory_service.control(session_id, RESEARCHER, "resume")
    assert denied.value.status == 409
    with pytest.raises(Study1ServiceError) as bad_extension:
        memory_service.control(
            session_id, RESEARCHER, "extend", {"seconds": -1}
        )
    assert bad_extension.value.code == "INVALID_EXTENSION"


def test_incident_updates_dashboard_and_event_log(memory_service):
    session_id = memory_service.create_session("incident")["session"]["session_id"]
    incident = memory_service.add_incident(
        session_id,
        RESEARCHER,
        "participant_disconnect",
        "warning",
        "Participant briefly disconnected",
    )
    dashboard = memory_service.researcher_dashboard(session_id)
    assert incident["category"] == "participant_disconnect"
    assert dashboard["incident_count"] == 1
    assert memory_service.repository.events[-1]["event_type"] == "incident_created"
