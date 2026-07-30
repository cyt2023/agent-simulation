from __future__ import annotations


RESEARCHER = {"participant_id": "researcher", "role": "researcher"}


def _task(task_definition_id: str = "formal-state-task") -> dict:
    return {
        "task_definition_id": task_definition_id,
        "task_version": "1.0",
        "title": "Formal state task",
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


def _formal_session_in(memory_service, phase: str):
    task = memory_service.create_task_definition(RESEARCHER, _task())
    memory_service.validate_task_definition(
        task["task_definition_id"], RESEARCHER, task["task_version"]
    )
    created = memory_service.create_session(
        "Formal state",
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


def _team_final_content():
    return {
        "candidate_id": "a",
        "rationale": "The team agreed that the shared evidence supports A.",
        "confidence": 6,
        "decision_status": "settled",
    }


def _final_decision():
    return {
        "candidate_id": "a",
        "rationale": "I accept A as the final decision.",
        "confidence": 6,
    }


def test_final_readiness_uses_locked_team_artifact_and_private_final_decisions(
    memory_service,
):
    session_id, actors = _formal_session_in(memory_service, "FINAL_DECISION")
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
    memory_service.create_individual_decision(
        session_id, actors["principal"], "final_individual", _final_decision()
    )

    memory_service.repository.sessions[session_id]["completion"] = {}
    dto = memory_service.session_dto(
        memory_service.repository.get_session(session_id), "principal"
    )

    assert dto["missing_prerequisites"] == [
        "final_individual:teammate_1",
        "final_individual:teammate_2",
    ]


def test_pre_vote_capability_uses_pre_individual_decision_records(memory_service):
    session_id, actors = _formal_session_in(memory_service, "PRE_VOTE")

    before = memory_service.session_dto(
        memory_service.repository.get_session(session_id), "principal"
    )
    assert before["capabilities"]["submit_pre_individual"] is True

    memory_service.create_individual_decision(
        session_id,
        actors["principal"],
        "pre_individual",
        {
            "candidate_id": "a",
            "rationale": "Shared evidence supports A.",
            "confidence": 5,
        },
    )
    memory_service.repository.sessions[session_id]["completion"] = {}
    after = memory_service.session_dto(
        memory_service.repository.get_session(session_id), "principal"
    )

    assert after["capabilities"]["submit_pre_individual"] is False
    assert after["missing_prerequisites"] == [
        "pre_individual:teammate_1",
        "pre_individual:teammate_2",
    ]
