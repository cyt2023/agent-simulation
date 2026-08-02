from __future__ import annotations

RESEARCHER = {"participant_id": "researcher", "role": "researcher"}


def _formal_session_in(memory_service, phase):
    memory_service.create_task_definition(
        RESEARCHER,
        {
            "task_definition_id": "shared-route-task",
            "task_version": "1.0",
            "title": "Shared route task",
            "candidate_ids": ["a", "b", "c"],
            "facts": [
                {
                    "fact_id": "shared",
                    "candidate_id": "a",
                    "text": "Shared fact.",
                    "valence": "positive",
                    "information_type": "shared",
                    "visible_to_roles": [
                        "principal",
                        "teammate_1",
                        "teammate_2",
                    ],
                },
                *[
                    {
                        "fact_id": role,
                        "candidate_id": candidate,
                        "text": f"{role} fact.",
                        "valence": "positive",
                        "information_type": "unique",
                        "visible_to_roles": [role],
                    }
                    for role, candidate in (
                        ("principal", "b"),
                        ("teammate_1", "c"),
                        ("teammate_2", "b"),
                    )
                ],
            ],
        },
    )
    memory_service.validate_task_definition(
        "shared-route-task", RESEARCHER, "1.0"
    )
    created = memory_service.create_session(
        "Shared route session", task_definition_id="shared-route-task"
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


def _team_final():
    return {
        "candidate_id": "a",
        "rationale": "Shared evidence supports A.",
        "confidence": 5,
        "ratings": {},
        "decision_status": "final",
    }


def _headers(token_manager, identity):
    token = token_manager.issue_participant(
        identity["session_id"], identity["participant_id"], identity["role"]
    )
    return {"Authorization": f"Bearer {token}"}


def test_shared_artifact_revision_and_confirmation_routes(
    study1_client, memory_service, token_manager
):
    session_id, actors = _formal_session_in(memory_service, "FINAL_DECISION")
    principal_headers = _headers(token_manager, actors["principal"])

    created = study1_client.post(
        f"/api/study1/sessions/{session_id}/shared-artifacts/team_final/revisions",
        headers=principal_headers,
        json={"parent_revision_id": None, "content": _team_final()},
    )
    assert created.status_code == 201
    revision = created.get_json()
    assert revision["kind"] == "team_final"
    assert revision["locked"] is False

    for role in ("principal", "teammate_1", "teammate_2"):
        response = study1_client.post(
            f"/api/study1/sessions/{session_id}/shared-artifacts/team_final/"
            f"revisions/{revision['revision_id']}/confirm",
            headers=_headers(token_manager, actors[role]),
        )
        assert response.status_code == 200
    assert response.get_json()["locked"] is True

    fetched = study1_client.get(
        f"/api/study1/sessions/{session_id}/shared-artifacts/team_final",
        headers=principal_headers,
    )
    assert fetched.status_code == 200
    assert fetched.get_json()["locked_revision_id"] == revision["revision_id"]


def test_shared_artifact_route_rejects_wrong_phase(
    study1_client, memory_service, token_manager
):
    session_id, actors = _formal_session_in(memory_service, "FOLLOWUP_TASK")
    response = study1_client.post(
        f"/api/study1/sessions/{session_id}/shared-artifacts/team_final/revisions",
        headers=_headers(token_manager, actors["principal"]),
        json={"parent_revision_id": None, "content": _team_final()},
    )
    assert response.status_code == 409
    assert response.get_json()["error"] == "ACTION_NOT_ALLOWED_IN_PHASE"
