from __future__ import annotations

import json
import zipfile


RESEARCHER = {"participant_id": "researcher", "role": "researcher"}


def _task(task_definition_id: str = "formal-export-task") -> dict:
    return {
        "task_definition_id": task_definition_id,
        "task_version": "1.0",
        "title": "Formal export task",
        "candidate_ids": ["a", "b", "c"],
        "facts": [
            {
                "fact_id": "shared-a",
                "candidate_id": "a",
                "text": "Shared evidence for A.",
                "valence": "positive",
                "information_type": "shared",
                "visible_to_roles": ["principal", "teammate_1", "teammate_2"],
            },
            {
                "fact_id": "p-b",
                "candidate_id": "b",
                "text": "Principal evidence for B.",
                "valence": "positive",
                "information_type": "unique",
                "visible_to_roles": ["principal"],
            },
            {
                "fact_id": "t1-c",
                "candidate_id": "c",
                "text": "Teammate 1 evidence for C.",
                "valence": "negative",
                "information_type": "unique",
                "visible_to_roles": ["teammate_1"],
            },
            {
                "fact_id": "t2-b",
                "candidate_id": "b",
                "text": "Teammate 2 evidence for B.",
                "valence": "positive",
                "information_type": "unique",
                "visible_to_roles": ["teammate_2"],
            },
        ],
    }


def _formal_session(service):
    task = service.create_task_definition(RESEARCHER, _task())
    service.validate_task_definition(task["task_definition_id"], RESEARCHER, task["task_version"])
    created = service.create_session(
        "Formal export",
        task_definition_id=task["task_definition_id"],
    )
    session_id = created["session"]["session_id"]
    identities = {}
    for invite in created["invites"]:
        identity = service.exchange_invite(invite["token"])["identity"]
        identities[identity["role"]] = identity
    snapshot = service.repository.sessions[session_id]
    snapshot["status"] = "running"
    snapshot["phase"] = "PRE_VOTE"
    snapshot["completion"] = {}
    return session_id, identities


def _team_final_content():
    return {
        "candidate_id": "a",
        "rationale": "The team agreed on A after reviewing the shared evidence.",
        "confidence": 6,
        "decision_status": "settled",
    }


def test_formal_export_includes_formal_records_and_ordered_instruments(memory_service):
    session_id, actors = _formal_session(memory_service)
    memory_service.submit(
        session_id,
        actors["principal"],
        "pre_vote",
        "2.0",
        {"decision": "a", "rationale": "Shared evidence", "confidence": 5},
    )
    memory_service.submit_instrument_response(
        session_id,
        actors["principal"],
        "pre-individual-v2",
        "2.0",
        [
            {"item_id": "candidate_id", "response": "a"},
            {"item_id": "rationale", "response": "Shared evidence"},
            {"item_id": "confidence", "response": 5},
        ],
    )
    memory_service.repository.sessions[session_id]["phase"] = "FINAL_DECISION"
    revision = memory_service.create_shared_revision(
        session_id,
        actors["principal"],
        "team_final",
        None,
        _team_final_content(),
    )
    for role in ("principal", "teammate_1", "teammate_2"):
        memory_service.confirm_shared_revision(
            session_id, actors[role], "team_final", revision["revision_id"]
        )
    export_buffer = memory_service.export_bundle(session_id)

    with zipfile.ZipFile(export_buffer) as archive:
        names = set(archive.namelist())
        assert {
            "task_definition.json",
            "task_facts.jsonl",
            "role_assignments.jsonl",
            "fact_assignments.jsonl",
            "protocol_snapshot.json",
            "decisions.jsonl",
            "shared_artifacts.json",
            "shared_revisions.jsonl",
            "shared_confirmations.jsonl",
            "ordered_instruments.json",
        } <= names
        schema = json.loads(archive.read("schema_version.json"))
        assert schema["formal_certifiable"] is True
        assert schema["certification_status"] == "certifiable"


def test_formal_export_missing_data_uses_projected_instrument_completion(memory_service):
    session_id, actors = _formal_session(memory_service)
    snapshot = memory_service.repository.sessions[session_id]
    snapshot["phase"] = "DELEGATION_EXPECTATION"
    snapshot["completion"] = {}
    instrument = memory_service.get_current_instrument(session_id, actors["principal"])
    memory_service.submit_instrument_response(
        session_id,
        actors["principal"],
        instrument["instrument_definition_id"],
        instrument["instrument_version"],
        [
            {"item_id": "expected_information_shared", "response": "X should share only authorized principal priorities."},
            {"item_id": "expected_recommendation", "response": "X should not make a final recommendation."},
            {"item_id": "expected_tentative_agreement", "response": "X may acknowledge a tentative preference."},
            {"item_id": "confidence", "response": 5},
        ],
    )
    export_buffer = memory_service.export_bundle(session_id)

    with zipfile.ZipFile(export_buffer) as archive:
        schema = json.loads(archive.read("schema_version.json"))
        ordered = json.loads(archive.read("ordered_instruments.json"))

    assert "delegation_expectation:principal" not in schema["missing_data"]["submissions"]
    assert "2.0" in schema["instrument_versions"]
    assert ordered["responses"][0]["instrument_definition_id"] == "delegation-expectation-v2"


def test_legacy_export_is_marked_uncertifiable(memory_service):
    created = memory_service.create_session("Legacy export")
    export_buffer = memory_service.export_bundle(created["session"]["session_id"])

    with zipfile.ZipFile(export_buffer) as archive:
        schema = json.loads(archive.read("schema_version.json"))
        assert schema["formal_certifiable"] is False
        assert schema["certification_status"] == "uncertifiable"
