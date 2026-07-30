from __future__ import annotations

import pytest

from study1.services import Study1ServiceError


RESEARCHER = {"participant_id": "researcher", "role": "researcher"}


def _task():
    return {
        "task_definition_id": "shared-task",
        "task_version": "1.0",
        "title": "Shared decision task",
        "candidate_ids": ["a", "b", "c"],
        "facts": [
            {
                "fact_id": "shared",
                "candidate_id": "a",
                "text": "Shared fact.",
                "valence": "positive",
                "information_type": "shared",
                "visible_to_roles": ["principal", "teammate_1", "teammate_2"],
            },
            {
                "fact_id": "p",
                "candidate_id": "b",
                "text": "P fact.",
                "valence": "positive",
                "information_type": "unique",
                "visible_to_roles": ["principal"],
            },
            {
                "fact_id": "t1",
                "candidate_id": "c",
                "text": "T1 fact.",
                "valence": "negative",
                "information_type": "unique",
                "visible_to_roles": ["teammate_1"],
            },
            {
                "fact_id": "t2",
                "candidate_id": "b",
                "text": "T2 fact.",
                "valence": "positive",
                "information_type": "unique",
                "visible_to_roles": ["teammate_2"],
            },
        ],
    }


def _formal_session_in(memory_service, phase: str):
    memory_service.create_task_definition(RESEARCHER, _task())
    memory_service.validate_task_definition("shared-task", RESEARCHER, "1.0")
    created = memory_service.create_session(
        "Shared artifact session", task_definition_id="shared-task"
    )
    session_id = created["session"]["session_id"]
    identities = {}
    for invite in created["invites"]:
        exchange = memory_service.exchange_invite(invite["token"])
        identities[exchange["identity"]["role"]] = exchange["identity"]
    snapshot = memory_service.repository.sessions[session_id]
    snapshot["status"] = "running"
    snapshot["phase"] = phase
    return session_id, identities


def _team_final(candidate_id="a", rationale="Shared evidence supports A."):
    return {
        "candidate_id": candidate_id,
        "rationale": rationale,
        "confidence": 5,
        "ratings": {"decision_quality": 6},
        "decision_status": "final",
    }


def test_new_revision_invalidates_prior_confirmations(memory_service):
    session_id, actors = _formal_session_in(memory_service, "FINAL_DECISION")
    first = memory_service.create_shared_revision(
        session_id, actors["principal"], "team_final", None, _team_final()
    )
    memory_service.confirm_shared_revision(
        session_id, actors["principal"], "team_final", first["revision_id"]
    )
    memory_service.confirm_shared_revision(
        session_id, actors["teammate_1"], "team_final", first["revision_id"]
    )

    second = memory_service.create_shared_revision(
        session_id,
        actors["teammate_2"],
        "team_final",
        first["revision_id"],
        _team_final("b", "The combined evidence now supports B."),
    )

    assert second["revision_number"] == 2
    assert second["confirmed_roles"] == []
    assert second["locked"] is False
    current = memory_service.get_shared_artifact(
        session_id, actors["principal"], "team_final"
    )
    assert current["current_revision"]["revision_id"] == second["revision_id"]
    assert current["current_revision"]["confirmed_roles"] == []


def test_locks_only_after_all_three_confirm_and_creates_team_decision(memory_service):
    session_id, actors = _formal_session_in(memory_service, "FINAL_DECISION")
    revision = memory_service.create_shared_revision(
        session_id, actors["principal"], "team_final", None, _team_final()
    )

    for role in ("principal", "teammate_1"):
        result = memory_service.confirm_shared_revision(
            session_id, actors[role], "team_final", revision["revision_id"]
        )
        assert result["locked"] is False

    locked = memory_service.confirm_shared_revision(
        session_id, actors["teammate_2"], "team_final", revision["revision_id"]
    )
    assert locked["locked"] is True
    assert locked["confirmed_roles"] == ["principal", "teammate_1", "teammate_2"]

    decisions = memory_service.repository.list_decisions(session_id)
    assert len(decisions) == 1
    assert decisions[0]["decision_kind"] == "team_final"
    assert decisions[0]["participant_id"] is None
    assert decisions[0]["candidate_id"] == "a"
    assert decisions[0]["source_revision_id"] == revision["revision_id"]
    assert decisions[0]["locked"] is True
    assert memory_service.repository.get_session(session_id)["completion"][
        "team_final_locked"
    ] is True


def test_revision_requires_current_parent_and_locked_artifact_is_immutable(memory_service):
    session_id, actors = _formal_session_in(memory_service, "FINAL_DECISION")
    revision = memory_service.create_shared_revision(
        session_id, actors["principal"], "team_final", None, _team_final()
    )
    with pytest.raises(Study1ServiceError) as stale:
        memory_service.create_shared_revision(
            session_id,
            actors["teammate_1"],
            "team_final",
            None,
            _team_final("b", "Stale edit."),
        )
    assert stale.value.code == "SHARED_REVISION_CONFLICT"

    for actor in actors.values():
        memory_service.confirm_shared_revision(
            session_id, actor, "team_final", revision["revision_id"]
        )
    with pytest.raises(Study1ServiceError) as locked:
        memory_service.create_shared_revision(
            session_id,
            actors["teammate_1"],
            "team_final",
            revision["revision_id"],
            _team_final("b", "Too late."),
        )
    assert locked.value.code == "SHARED_ARTIFACT_LOCKED"


def test_followup_requires_structured_content(memory_service):
    session_id, actors = _formal_session_in(memory_service, "FOLLOWUP_TASK")
    with pytest.raises(Study1ServiceError) as error:
        memory_service.create_shared_revision(
            session_id,
            actors["principal"],
            "followup_task",
            None,
            {"implementation_plan": "Do it later."},
        )
    assert error.value.code == "INVALID_FOLLOWUP_CONTENT"

    revision = memory_service.create_shared_revision(
        session_id,
        actors["principal"],
        "followup_task",
        None,
        {
            "resource_allocation": [
                {"resource": "Budget", "allocation": "60% to implementation"}
            ],
            "ranked_actions": ["Validate the plan", "Assign owners"],
            "implementation_plan": "T1 validates; T2 assigns owners; P reviews.",
        },
    )
    assert revision["kind"] == "followup_task"
    assert revision["content"]["ranked_actions"][0] == "Validate the plan"


def test_sql_repository_locks_shared_revision_and_exports_confirmation_history(sql_service):
    sql_service.create_task_definition(RESEARCHER, _task())
    sql_service.validate_task_definition("shared-task", RESEARCHER, "1.0")
    created = sql_service.create_session(
        "SQL shared artifact session", task_definition_id="shared-task"
    )
    session_id = created["session"]["session_id"]
    actors = {}
    for invite in created["invites"]:
        exchange = sql_service.exchange_invite(invite["token"])
        actors[exchange["identity"]["role"]] = exchange["identity"]
    with sql_service.repository.SessionLocal() as db:
        from services.db import ResearchSessionRow

        row = db.get(ResearchSessionRow, session_id)
        payload = dict(row.payload)
        payload["status"] = "running"
        payload["phase"] = "FINAL_DECISION"
        row.payload = payload
        db.commit()

    revision = sql_service.create_shared_revision(
        session_id, actors["principal"], "team_final", None, _team_final()
    )
    for role in ("principal", "teammate_1", "teammate_2"):
        locked = sql_service.confirm_shared_revision(
            session_id, actors[role], "team_final", revision["revision_id"]
        )
    assert locked["locked"] is True
    exported = sql_service.repository.export_data(session_id)
    assert len(exported["shared_artifacts"]) == 1
    assert len(exported["shared_revisions"]) == 1
    assert len(exported["shared_confirmations"]) == 3
    assert len(exported["decisions"]) == 1
