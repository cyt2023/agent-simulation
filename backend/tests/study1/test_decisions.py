from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from study1.services import Study1ServiceError


RESEARCHER = {"participant_id": "researcher", "role": "researcher"}


def _task():
    return {
        "task_definition_id": "decision-task",
        "task_version": "1.0",
        "title": "Decision task",
        "candidate_ids": ["a", "b", "c"],
        "facts": [
            {"fact_id": "s", "candidate_id": "a", "text": "Shared.", "valence": "positive", "information_type": "shared", "visible_to_roles": ["principal", "teammate_1", "teammate_2"]},
            {"fact_id": "p", "candidate_id": "b", "text": "P fact.", "valence": "positive", "information_type": "unique", "visible_to_roles": ["principal"]},
            {"fact_id": "t1", "candidate_id": "c", "text": "T1 fact.", "valence": "negative", "information_type": "unique", "visible_to_roles": ["teammate_1"]},
            {"fact_id": "t2", "candidate_id": "b", "text": "T2 fact.", "valence": "positive", "information_type": "unique", "visible_to_roles": ["teammate_2"]}
        ]
    }


def _pre_vote(service):
    service.create_task_definition(RESEARCHER, _task())
    service.validate_task_definition("decision-task", RESEARCHER, "1.0")
    created = service.create_session("Decision session", task_definition_id="decision-task")
    identities = {}
    for invite in created["invites"]:
        exchange = service.exchange_invite(invite["token"])
        identities[exchange["identity"]["role"]] = exchange["identity"]
    session_id = created["session"]["session_id"]
    service.control(session_id, RESEARCHER, "start")
    for identity in identities.values():
        service.submit(session_id, identity, "material_ack", "2.0", {"acknowledged": True})
    service.advance(session_id, RESEARCHER, "PRE_VOTE")
    return session_id, identities


def _tentative_decision(service):
    session_id, identities = _pre_vote(service)
    for role, identity in identities.items():
        service.create_individual_decision(
            session_id,
            identity,
            "pre_individual",
            {
                "candidate_id": "a",
                "rationale": f"{role} pre-discussion rationale.",
                "confidence": 5,
            },
        )
    service.advance(session_id, RESEARCHER, "PROXY_CONFIGURATION")
    principal_material_id = service.get_materials(
        session_id, "principal"
    )[0]["material_id"]
    service.submit(
        session_id,
        identities["principal"],
        "proxy_config",
        "2.0",
        {
            "priorities": "Share authorized principal evidence neutrally.",
            "boundaries": "Do not make final commitments.",
            "authority_level": "suggest",
            "authorization_confirmed": True,
            "authorized_material_ids": [principal_material_id],
        },
    )
    for role in ("teammate_1", "teammate_2"):
        service.submit(
            session_id,
            identities[role],
            "proxy_ready",
            "2.0",
            {"ready": True},
        )
    service.advance(session_id, RESEARCHER, "PROXY_MEETING")
    proxy_meeting = service.repository.get_session(session_id)
    service.receive_media_event(
        {
            "event_id": str(uuid.uuid4()),
            "session_id": session_id,
            "phase_version": proxy_meeting["phase_version"],
            "event_type": "MEETING_ENDED",
            "occurred_at": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "payload": {"source": "test"},
        }
    )
    service.advance(session_id, RESEARCHER, "TENTATIVE_DECISION")
    return session_id, identities


def test_decision_rejects_free_text_candidate(memory_service):
    session_id, identities = _pre_vote(memory_service)
    with pytest.raises(Study1ServiceError) as error:
        memory_service.create_individual_decision(
            session_id,
            identities["principal"],
            "pre_individual",
            {"candidate_id": "Option A", "rationale": "Reason", "confidence": 4},
        )
    assert error.value.code == "INVALID_CANDIDATE_ID"


def test_individual_decision_locks_once_and_drives_completion(memory_service):
    session_id, identities = _pre_vote(memory_service)
    decision = memory_service.create_individual_decision(
        session_id,
        identities["principal"],
        "pre_individual",
        {"candidate_id": "a", "rationale": "Shared evidence", "confidence": 5},
    )
    assert decision["locked"] is True
    assert memory_service.repository.get_session(session_id)["completion"]["pre_vote:principal"] is True
    with pytest.raises(Study1ServiceError) as duplicate:
        memory_service.create_individual_decision(
            session_id,
            identities["principal"],
            "pre_individual",
            {"candidate_id": "b", "rationale": "Changed", "confidence": 4},
    )
    assert duplicate.value.code == "DECISION_ALREADY_SUBMITTED"


def test_tentative_decision_persists_proxy_expectation_fields(memory_service):
    session_id, identities = _tentative_decision(memory_service)

    decision = memory_service.create_individual_decision(
        session_id,
        identities["teammate_1"],
        "tentative_individual",
        {
            "candidate_id": "a",
            "rationale": "The Proxy meeting produced a tentative preference.",
            "confidence": 5,
            "decision_status": "tentative",
            "proxy_authority_belief": "uncertain",
            "expected_principal_acceptance": 4,
        },
    )

    assert decision["decision_status"] == "tentative"
    assert decision["ratings"]["proxy_authority_belief"] == "uncertain"
    assert decision["ratings"]["expected_principal_acceptance"] == 4
