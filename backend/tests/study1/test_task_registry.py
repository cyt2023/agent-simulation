from __future__ import annotations

import copy

import pytest

from study1.services import Study1ServiceError


RESEARCHER = {"participant_id": "researcher", "role": "researcher"}


def valid_task_payload(task_definition_id="hidden-profile-001"):
    return {
        "task_definition_id": task_definition_id,
        "task_version": "1.0",
        "title": "Three candidate hiring task",
        "candidate_ids": ["candidate-a", "candidate-b", "candidate-c"],
        "facts": [
            {
                "fact_id": "fact-shared-a",
                "candidate_id": "candidate-a",
                "text": "Candidate A has relevant experience.",
                "valence": "positive",
                "information_type": "shared",
                "visible_to_roles": ["principal", "teammate_1", "teammate_2"],
            },
            {
                "fact_id": "fact-p-b",
                "candidate_id": "candidate-b",
                "text": "Candidate B has a certification known to P.",
                "valence": "positive",
                "information_type": "unique",
                "visible_to_roles": ["principal"],
            },
            {
                "fact_id": "fact-t1-c",
                "candidate_id": "candidate-c",
                "text": "Candidate C missed a deadline known to T1.",
                "valence": "negative",
                "information_type": "unique",
                "visible_to_roles": ["teammate_1"],
            },
            {
                "fact_id": "fact-t2-b",
                "candidate_id": "candidate-b",
                "text": "Candidate B led a similar project known to T2.",
                "valence": "positive",
                "information_type": "unique",
                "visible_to_roles": ["teammate_2"],
            },
        ],
    }


def test_registered_task_requires_exactly_three_unique_candidates():
    from study1.task_registry import TaskDefinitionValidationError, validate_registered_task

    payload = valid_task_payload()
    payload["candidate_ids"] = ["candidate-a", "candidate-a", "candidate-b"]

    with pytest.raises(TaskDefinitionValidationError) as error:
        validate_registered_task(payload)

    assert error.value.code == "TASK_REQUIRES_THREE_UNIQUE_CANDIDATES"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda payload: payload["facts"][1].update(fact_id="fact-shared-a"),
            "DUPLICATE_TASK_FACT_ID",
        ),
        (
            lambda payload: payload["facts"][1].update(candidate_id="candidate-x"),
            "UNKNOWN_FACT_CANDIDATE",
        ),
        (
            lambda payload: payload["facts"][1].update(valence="important"),
            "INVALID_FACT_VALENCE",
        ),
        (
            lambda payload: payload["facts"][1].update(visible_to_roles=["researcher"]),
            "INVALID_FACT_VISIBILITY",
        ),
    ],
)
def test_registered_task_rejects_invalid_atomic_facts(mutation, expected_code):
    from study1.task_registry import TaskDefinitionValidationError, validate_registered_task

    payload = valid_task_payload()
    mutation(payload)

    with pytest.raises(TaskDefinitionValidationError) as error:
        validate_registered_task(payload)

    assert error.value.code == expected_code


@pytest.mark.parametrize("identifier_kind", ["task", "candidate", "fact"])
def test_registered_task_rejects_overlong_identifiers_before_checksum(
    identifier_kind,
):
    from study1.task_registry import TaskDefinitionValidationError, validate_registered_task

    payload = valid_task_payload()
    overlong = "x" * 129
    if identifier_kind == "task":
        payload["task_definition_id"] = overlong
    elif identifier_kind == "candidate":
        payload["candidate_ids"][0] = overlong
        payload["facts"][0]["candidate_id"] = overlong
    else:
        payload["facts"][0]["fact_id"] = overlong

    with pytest.raises(TaskDefinitionValidationError) as error:
        validate_registered_task(payload)

    assert error.value.code == "TASK_IDENTIFIER_TOO_LONG"


@pytest.mark.parametrize(
    ("field", "maximum", "expected_code"),
    [
        ("task_version", 64, "TASK_VERSION_TOO_LONG"),
        ("title", 512, "TASK_TITLE_TOO_LONG"),
    ],
)
def test_registered_task_rejects_overlong_bounded_text_fields(
    field, maximum, expected_code
):
    from study1.task_registry import TaskDefinitionValidationError, validate_registered_task

    payload = valid_task_payload()
    payload[field] = "x" * (maximum + 1)

    with pytest.raises(TaskDefinitionValidationError) as error:
        validate_registered_task(payload)

    assert error.value.code == expected_code


def test_registered_task_accepts_exact_storage_boundaries():
    from study1.task_registry import validate_registered_task

    payload = valid_task_payload("t" * 128)
    payload["task_version"] = "v" * 64
    payload["title"] = "T" * 512
    payload["candidate_ids"][0] = "c" * 128
    payload["facts"][0]["candidate_id"] = "c" * 128
    payload["facts"][0]["fact_id"] = "f" * 128

    canonical = validate_registered_task(payload)

    assert canonical["task_definition_id"] == payload["task_definition_id"]
    assert canonical["task_version"] == payload["task_version"]
    assert canonical["title"] == payload["title"]
    assert canonical["candidate_ids"][0] == payload["candidate_ids"][0]
    assert canonical["facts"][0]["fact_id"] == payload["facts"][0]["fact_id"]
    assert canonical["facts"][0]["candidate_id"] == payload["facts"][0]["candidate_id"]


def test_task_lifecycle_is_draft_then_validated_and_immutable(memory_service):
    created = memory_service.create_task_definition(RESEARCHER, valid_task_payload())
    assert created["status"] == "draft"

    validated = memory_service.validate_task_definition(
        created["task_definition_id"], RESEARCHER
    )
    assert validated["status"] == "validated"
    assert len(validated["content_checksum"]) == 64

    with pytest.raises(Study1ServiceError) as error:
        memory_service.replace_task_definition(
            created["task_definition_id"], RESEARCHER, valid_task_payload()
        )
    assert error.value.code == "TASK_DEFINITION_IMMUTABLE"


def test_memory_repository_atomically_rejects_validated_task_replacement(memory_service):
    created = memory_service.create_task_definition(RESEARCHER, valid_task_payload())
    validated = memory_service.validate_task_definition(
        created["task_definition_id"], RESEARCHER
    )
    replacement = copy.deepcopy(validated)
    replacement["title"] = "Replacement title"
    replacement["facts"][0]["text"] = "Replacement fact text."
    replacement["status"] = "draft"

    with pytest.raises(Study1ServiceError) as error:
        memory_service.repository.replace_task_definition(
            created["task_definition_id"], replacement
        )

    assert error.value.code == "TASK_DEFINITION_IMMUTABLE"
    persisted = memory_service.repository.get_task_definition(
        created["task_definition_id"], created["task_version"]
    )
    assert persisted == validated


def test_task_versions_share_logical_id_without_repository_ambiguity(memory_service):
    v1 = valid_task_payload("versioned-task")
    v2 = valid_task_payload("versioned-task")
    v2["task_version"] = "2.0"
    v2["title"] = "Version two"

    memory_service.create_task_definition(RESEARCHER, v1)
    memory_service.create_task_definition(RESEARCHER, v2)

    assert memory_service.get_task_definition("versioned-task", "1.0")["title"] == v1[
        "title"
    ]
    assert memory_service.get_task_definition("versioned-task", "2.0")["title"] == v2[
        "title"
    ]
    assert {
        (task["task_definition_id"], task["task_version"])
        for task in memory_service.list_task_definitions()
    } == {("versioned-task", "1.0"), ("versioned-task", "2.0")}


def test_sql_repository_replaces_draft_with_same_fact_ids(sql_service):
    payload = valid_task_payload("sql-replace-task")
    sql_service.create_task_definition(RESEARCHER, payload)
    replacement = copy.deepcopy(payload)
    replacement["facts"][0]["text"] = "Replacement shared fact."

    replaced = sql_service.replace_task_definition(
        payload["task_definition_id"], RESEARCHER, replacement
    )

    assert replaced["facts"][0]["text"] == "Replacement shared fact."
    persisted = sql_service.get_task_definition(
        payload["task_definition_id"], payload["task_version"]
    )
    assert persisted["facts"][0]["text"] == "Replacement shared fact."


def test_sql_repository_rechecks_immutability_after_stale_service_read(
    sql_service, monkeypatch
):
    payload = valid_task_payload("sql-stale-draft-task")
    created = sql_service.create_task_definition(RESEARCHER, payload)
    original_facts = copy.deepcopy(created["facts"])
    replacement = copy.deepcopy(payload)
    replacement["facts"][0]["text"] = "This replacement must not be persisted."
    repository = sql_service.repository
    original_replace = repository.replace_task_definition

    def validate_before_locked_replace(task_definition_id, task):
        repository.set_task_definition_status(
            task_definition_id,
            task["task_version"],
            "validated",
            created["content_checksum"],
        )
        return original_replace(task_definition_id, task)

    monkeypatch.setattr(
        repository, "replace_task_definition", validate_before_locked_replace
    )

    with pytest.raises(Study1ServiceError) as error:
        sql_service.replace_task_definition(
            created["task_definition_id"], RESEARCHER, replacement
        )

    assert error.value.code == "TASK_DEFINITION_IMMUTABLE"
    persisted = repository.get_task_definition(
        created["task_definition_id"], created["task_version"]
    )
    assert persisted["status"] == "validated"
    assert persisted["facts"] == original_facts


@pytest.mark.parametrize("service_fixture", ["memory_service", "sql_service"])
def test_validation_publish_rejects_concurrent_draft_change(
    request, service_fixture, monkeypatch
):
    service = request.getfixturevalue(service_fixture)
    payload = valid_task_payload(f"{service_fixture}-publish-race")
    created = service.create_task_definition(RESEARCHER, payload)
    replacement = copy.deepcopy(payload)
    replacement["title"] = "Concurrently replaced draft"
    replacement["facts"][0]["text"] = "This is the current draft fact."
    repository = service.repository
    original_publish = repository.set_task_definition_status

    def replace_before_locked_publish(
        task_definition_id, task_version, status, content_checksum
    ):
        service.replace_task_definition(
            task_definition_id,
            RESEARCHER,
            replacement,
            task_version,
        )
        return original_publish(
            task_definition_id,
            task_version,
            status,
            content_checksum,
        )

    monkeypatch.setattr(
        repository, "set_task_definition_status", replace_before_locked_publish
    )

    with pytest.raises(Study1ServiceError) as error:
        service.validate_task_definition(
            created["task_definition_id"], RESEARCHER, created["task_version"]
        )

    assert error.value.code == "TASK_DEFINITION_CHANGED"
    persisted = repository.get_task_definition(
        created["task_definition_id"], created["task_version"]
    )
    assert persisted["status"] == "draft"
    assert persisted["title"] == replacement["title"]
    assert persisted["facts"][0]["text"] == replacement["facts"][0]["text"]
    assert persisted["content_checksum"] != created["content_checksum"]


def test_sql_task_repository_keeps_two_versions_of_one_logical_task(sql_service):
    v1 = valid_task_payload("sql-versioned-task")
    v2 = valid_task_payload("sql-versioned-task")
    v2["task_version"] = "2.0"
    v2["title"] = "SQL version two"

    sql_service.create_task_definition(RESEARCHER, v1)
    sql_service.create_task_definition(RESEARCHER, v2)

    assert sql_service.get_task_definition("sql-versioned-task", "1.0")[
        "title"
    ] == v1["title"]
    assert sql_service.get_task_definition("sql-versioned-task", "2.0")[
        "title"
    ] == v2["title"]


def test_formal_session_requires_a_validated_registered_task(memory_service):
    draft = memory_service.create_task_definition(RESEARCHER, valid_task_payload())

    with pytest.raises(Study1ServiceError) as error:
        memory_service.create_session(
            "formal-session",
            task_definition_id=draft["task_definition_id"],
        )

    assert error.value.code == "TASK_NOT_VALIDATED"


def test_formal_session_persists_stable_role_and_fact_assignments(memory_service):
    task = memory_service.create_task_definition(RESEARCHER, valid_task_payload())
    memory_service.validate_task_definition(task["task_definition_id"], RESEARCHER)

    created = memory_service.create_session(
        "formal-session",
        task_definition_id=task["task_definition_id"],
        experiment_config={"randomization_seed": "stable-seed"},
    )
    session_id = created["session"]["session_id"]
    exported = memory_service.repository.export_data(session_id)

    assert created["session"]["protocol_mode"] == "formal_v2"
    assert created["session"]["task_definition_id"] == task["task_definition_id"]
    assert {item["role"] for item in exported["role_assignments"]} == {
        "principal",
        "teammate_1",
        "teammate_2",
    }
    assert len({item["participant_slot_id"] for item in exported["role_assignments"]}) == 3
    assert {
        (item["fact_id"], item["role"])
        for item in exported["fact_assignments"]
    } == {
        ("fact-shared-a", "principal"),
        ("fact-shared-a", "teammate_1"),
        ("fact-shared-a", "teammate_2"),
        ("fact-p-b", "principal"),
        ("fact-t1-c", "teammate_1"),
        ("fact-t2-b", "teammate_2"),
    }
    assert {
        event["event_type"] for event in exported["events"]
    } >= {"role_assignment_created", "fact_assignment_created"}

    before = copy.deepcopy(exported["role_assignments"])
    for invite in created["invites"]:
        memory_service.exchange_invite(invite["token"])
    after = memory_service.repository.export_data(session_id)["role_assignments"]
    assert after == before


def test_formal_materials_are_rendered_from_visible_registered_facts(memory_service):
    task = memory_service.create_task_definition(RESEARCHER, valid_task_payload())
    memory_service.validate_task_definition(task["task_definition_id"], RESEARCHER)
    created = memory_service.create_session(
        "formal-materials", task_definition_id=task["task_definition_id"]
    )
    session_id = created["session"]["session_id"]

    principal = memory_service.get_materials(session_id, "principal")
    teammate_1 = memory_service.get_materials(session_id, "teammate_1")

    assert "known to P" in principal[0]["content"]
    assert "known to T1" not in principal[0]["content"]
    assert "known to T1" in teammate_1[0]["content"]
    assert "known to P" not in teammate_1[0]["content"]


def test_sql_formal_assignments_and_private_materials_survive_reconnect(sql_service):
    payload = valid_task_payload("sql-formal-task")
    sql_service.create_task_definition(RESEARCHER, payload)
    sql_service.validate_task_definition(
        payload["task_definition_id"], RESEARCHER, payload["task_version"]
    )
    created = sql_service.create_session(
        "SQL formal session",
        task_definition_id=payload["task_definition_id"],
        experiment_config={
            "task_version": payload["task_version"],
            "randomization_seed": "sql-stable-seed",
        },
    )
    session_id = created["session"]["session_id"]

    principal = sql_service.get_materials(session_id, "principal")
    teammate_1 = sql_service.get_materials(session_id, "teammate_1")
    assert "known to P" in principal[0]["content"]
    assert "known to T1" not in principal[0]["content"]
    assert "known to T1" in teammate_1[0]["content"]
    assert "known to P" not in teammate_1[0]["content"]

    before = copy.deepcopy(
        sql_service.repository.export_data(session_id)["role_assignments"]
    )
    for invite in created["invites"]:
        sql_service.exchange_invite(invite["token"])
    after = sql_service.repository.export_data(session_id)["role_assignments"]
    assert after == before


def test_researcher_task_registry_routes(study1_client):
    token = study1_client.post(
        "/api/study1/auth/researcher", json={"key": "researcher-test-key"}
    ).get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = study1_client.post(
        "/api/study1/task-definitions", headers=headers, json=valid_task_payload("route-task")
    )
    assert created.status_code == 201
    task_id = created.get_json()["task_definition_id"]

    validated = study1_client.post(
        f"/api/study1/task-definitions/{task_id}/validate", headers=headers
    )
    assert validated.status_code == 200
    assert validated.get_json()["status"] == "validated"

    listed = study1_client.get(
        "/api/study1/task-definitions?status=validated", headers=headers
    )
    assert [item["task_definition_id"] for item in listed.get_json()["tasks"]] == [task_id]


def test_task_registry_route_can_select_an_explicit_version(study1_client):
    token = study1_client.post(
        "/api/study1/auth/researcher", json={"key": "researcher-test-key"}
    ).get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    v1 = valid_task_payload("route-versioned-task")
    v2 = valid_task_payload("route-versioned-task")
    v2["task_version"] = "2.0"
    v2["title"] = "Version two"
    assert study1_client.post(
        "/api/study1/task-definitions", headers=headers, json=v1
    ).status_code == 201
    assert study1_client.post(
        "/api/study1/task-definitions", headers=headers, json=v2
    ).status_code == 201

    selected = study1_client.get(
        "/api/study1/task-definitions/route-versioned-task?version=1.0",
        headers=headers,
    )
    assert selected.status_code == 200
    assert selected.get_json()["task_version"] == "1.0"
    latest = study1_client.get(
        "/api/study1/task-definitions/route-versioned-task", headers=headers
    )
    assert latest.status_code == 200
    assert latest.get_json()["task_version"] == "2.0"


def test_task_registry_routes_reject_participant_tokens(study1_client, memory_service):
    created = memory_service.create_session("Participant cannot manage tasks")
    participant = study1_client.post(
        f"/api/study1/invites/{created['invites'][0]['token']}/exchange"
    ).get_json()

    response = study1_client.post(
        "/api/study1/task-definitions",
        headers={"Authorization": f"Bearer {participant['token']}"},
        json=valid_task_payload("forbidden-task"),
    )

    assert response.status_code == 403
    assert response.get_json()["error"] == "FORBIDDEN"
