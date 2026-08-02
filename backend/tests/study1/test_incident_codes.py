import pytest

from study1.services import Study1ServiceError


RESEARCHER = {"participant_id": "researcher", "role": "researcher"}


def test_unknown_incident_code_is_rejected(memory_service):
    session_id = memory_service.create_session("incident-code")["session"]["session_id"]

    with pytest.raises(Study1ServiceError) as error:
        memory_service.add_incident(
            session_id,
            RESEARCHER,
            "free_text_failure",
            "warning",
            "This category is not in the coded catalog.",
        )

    assert error.value.code == "INVALID_INCIDENT_CODE"


def test_coded_incident_is_recorded_with_catalog_metadata(memory_service):
    session_id = memory_service.create_session("incident-code")["session"]["session_id"]

    incident = memory_service.add_incident(
        session_id,
        RESEARCHER,
        "participant_disconnect",
        "warning",
        "Teammate 1 briefly disconnected.",
    )

    assert incident["category"] == "participant_disconnect"
    assert incident["metadata"]["incident_label"] == "Participant disconnect"
