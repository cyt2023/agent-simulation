from __future__ import annotations

import pytest

from study1.instruments import (
    InstrumentValidationError,
    instrument_for,
    load_instrument_catalog,
    validate_ordered_responses,
)


RESEARCHER = {"participant_id": "researcher", "role": "researcher"}


def _task(task_definition_id: str = "formal-instrument-task") -> dict:
    return {
        "task_definition_id": task_definition_id,
        "task_version": "1.0",
        "title": "Formal instrument task",
        "candidate_ids": ["candidate-a", "candidate-b", "candidate-c"],
        "facts": [
            {
                "fact_id": "shared-a",
                "candidate_id": "candidate-a",
                "text": "Shared evidence supports Candidate A.",
                "valence": "positive",
                "information_type": "shared",
                "visible_to_roles": ["principal", "teammate_1", "teammate_2"],
            }
        ],
    }


def _formal_session_in(memory_service, phase: str):
    task = memory_service.create_task_definition(RESEARCHER, _task())
    memory_service.validate_task_definition(
        task["task_definition_id"], RESEARCHER, task["task_version"]
    )
    created = memory_service.create_session(
        "Formal instruments",
        task_definition_id=task["task_definition_id"],
    )
    session_id = created["session"]["session_id"]
    identities = {}
    for invite in created["invites"]:
        identity = memory_service.exchange_invite(invite["token"])["identity"]
        identities[identity["role"]] = identity
    snapshot = memory_service.repository.sessions[session_id]
    snapshot["status"] = "running"
    snapshot["phase"] = phase
    snapshot["completion"] = {}
    return session_id, identities


def test_formal_instrument_rejects_wrong_order():
    catalog = load_instrument_catalog()
    instrument = catalog["instruments"][0]
    responses = [
        {"item_id": "confidence", "response": 4},
        {"item_id": "candidate_id", "response": "a"},
        {"item_id": "rationale", "response": "Reason"},
    ]
    with pytest.raises(InstrumentValidationError) as error:
        validate_ordered_responses(instrument, responses)
    assert error.value.code == "INVALID_INSTRUMENT_ORDER"


def test_catalog_contains_only_ordered_versioned_english_items():
    catalog = load_instrument_catalog()
    assert catalog["catalog_version"] == "study1-instruments-v2"
    assert len(catalog["checksum"]) == 64
    for instrument in catalog["instruments"]:
        assert instrument["instrument_version"] == "2.0"
        assert [item["item_id"] for item in instrument["items"]]


def test_catalog_contains_principal_delegation_and_comprehension_instruments():
    catalog = load_instrument_catalog()

    delegation = instrument_for(catalog, "DELEGATION_EXPECTATION", "principal")
    comprehension = instrument_for(catalog, "COMPREHENSION_MEASUREMENT", "principal")

    assert delegation["instrument_definition_id"] == "delegation-expectation-v2"
    assert [item["item_id"] for item in delegation["items"]] == [
        "expected_information_shared",
        "expected_recommendation",
        "expected_tentative_agreement",
        "confidence",
    ]
    assert comprehension["instrument_definition_id"] == "comprehension-measurement-v2"
    assert [item["item_id"] for item in comprehension["items"]] == [
        "conclusion",
        "reasons",
        "member_positions",
        "disagreements",
        "decision_status",
        "proxy_commitments",
        "acceptance_intention",
        "confidence",
    ]
    assert instrument_for(catalog, "DELEGATION_EXPECTATION", "teammate_1") is None
    assert instrument_for(catalog, "COMPREHENSION_MEASUREMENT", "teammate_2") is None


def test_delegation_expectation_instrument_response_drives_review_gate(memory_service):
    session_id, identities = _formal_session_in(memory_service, "DELEGATION_EXPECTATION")
    instrument = memory_service.get_current_instrument(session_id, identities["principal"])

    memory_service.submit_instrument_response(
        session_id,
        identities["principal"],
        instrument["instrument_definition_id"],
        instrument["instrument_version"],
        [
            {"item_id": "expected_information_shared", "response": "I expect X to share the principal's authorized priorities."},
            {"item_id": "expected_recommendation", "response": "I expect X to keep the recommendation tentative."},
            {"item_id": "expected_tentative_agreement", "response": "X may acknowledge a tentative preference only."},
            {"item_id": "confidence", "response": 5},
        ],
    )
    memory_service.repository.add_artifact_for_testing(
        {
            "artifact_id": "summary-1",
            "session_id": session_id,
            "type": "summary",
            "version": "1",
            "content": "Neutral delegated discussion summary.",
        }
    )
    memory_service.repository.sessions[session_id]["completion"] = {}

    dto = memory_service.session_dto(
        memory_service.repository.get_session(session_id), "principal"
    )

    assert dto["ready_to_advance"] is True
    assert dto["missing_prerequisites"] == []


def test_comprehension_instrument_response_drives_handoff_gate(memory_service):
    session_id, identities = _formal_session_in(
        memory_service, "COMPREHENSION_MEASUREMENT"
    )
    instrument = memory_service.get_current_instrument(session_id, identities["principal"])

    memory_service.submit_instrument_response(
        session_id,
        identities["principal"],
        instrument["instrument_definition_id"],
        instrument["instrument_version"],
        [
            {"item_id": "conclusion", "response": "The delegated discussion reached a tentative preference."},
            {"item_id": "reasons", "response": "The participants cited the shared task evidence."},
            {"item_id": "member_positions", "response": "T1 supported A, T2 was cautious, and X stayed neutral."},
            {"item_id": "disagreements", "response": "No final commitment was made."},
            {"item_id": "decision_status", "response": "tentative_consensus"},
            {"item_id": "proxy_commitments", "response": "X made no binding commitment."},
            {"item_id": "acceptance_intention", "response": "I will revisit the tentative preference in the synchronous meeting."},
            {"item_id": "confidence", "response": 6},
        ],
    )
    memory_service.repository.sessions[session_id]["completion"] = {}

    dto = memory_service.session_dto(
        memory_service.repository.get_session(session_id), "principal"
    )

    assert dto["ready_to_advance"] is True
    assert dto["missing_prerequisites"] == []
