# Study 1 Platform Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Platform A enforce registered Hidden Profile tasks, immutable formal protocol configuration, status/phase authorization, separate decisions, shared team artifacts, and exact instruments.

**Architecture:** Add normalized formal-protocol tables beside the existing append-only Study 1 tables and classify existing Sessions as legacy. Keep orchestration in `Study1Service`, move validation rules into focused modules, and derive readiness and frontend capabilities from canonical persisted records.

**Tech Stack:** Python 3.11, Flask, SQLAlchemy 2, PostgreSQL/SQLite test adapters, pytest.

---

### Task 1: Add additive formal-protocol schema and migration guard

**Files:**
- Modify: `backend/study1/models.py`
- Modify: `backend/services/db.py`
- Modify: `backend/scripts/init_db.py`
- Create: `backend/study1/schema_migrations.py`
- Test: `backend/tests/study1/test_audio_completion_schema.py`
- Test: `backend/tests/study1/test_audio_completion_migration.py`

- [ ] **Step 1: Write failing schema tests**

```python
def test_formal_protocol_tables_are_registered():
    expected = {
        "study1_task_definitions", "study1_task_facts", "study1_role_assignments",
        "study1_protocol_snapshots", "study1_decisions", "study1_shared_artifacts",
        "study1_shared_revisions", "study1_shared_confirmations",
        "study1_instrument_definitions", "study1_instrument_responses",
    }
    assert expected <= set(Base.metadata.tables)

def test_legacy_session_migration_is_idempotent(migrated_repository):
    migrated_repository.run_schema_migrations()
    migrated_repository.run_schema_migrations()
    assert migrated_repository.protocol_mode("legacy-session") == "legacy_protocol"
```

- [ ] **Step 2: Run the new tests and verify RED**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_audio_completion_schema.py backend/tests/study1/test_audio_completion_migration.py -q`

Expected: failure because the formal tables and migration runner do not exist.

- [ ] **Step 3: Add ORM rows and an idempotent migration runner**

Define task/fact/assignment/protocol/decision/shared/instrument rows with explicit unique constraints. Add `Study1SchemaVersionRow(revision, applied_at)` and `run_study1_migrations(engine)` that creates additive tables and marks existing Study 1 snapshots as legacy without rewriting submissions or events.

```python
class Study1ProtocolSnapshotRow(Base):
    __tablename__ = "study1_protocol_snapshots"
    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    protocol_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 4: Run schema tests and the existing backend suite**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_audio_completion_schema.py backend/tests/study1/test_audio_completion_migration.py backend/tests/study1 -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/study1/models.py backend/study1/schema_migrations.py backend/services/db.py backend/scripts/init_db.py backend/tests/study1/test_audio_completion_schema.py backend/tests/study1/test_audio_completion_migration.py
git commit -m "feat(study1): add formal protocol schema"
```

### Task 2: Implement the validated three-candidate task registry

**Files:**
- Create: `backend/study1/task_registry.py`
- Modify: `backend/study1/services.py`
- Modify: `backend/study1/routes.py`
- Test: `backend/tests/study1/test_task_registry.py`
- Test: `backend/tests/study1/test_task_assignment.py`

- [ ] **Step 1: Write failing validation and route tests**

```python
def test_task_requires_exactly_three_candidates():
    with pytest.raises(TaskDefinitionError, match="exactly three"):
        validate_task_definition({"candidate_ids": ["a", "b"]}, [])

def test_fact_ids_are_unique_across_all_role_materials():
    facts = [fact("f-1", "a", ["principal"]), fact("f-1", "b", ["teammate_1"])]
    with pytest.raises(TaskDefinitionError, match="fact_id"):
        validate_task_definition(task(), facts)

def test_only_validated_task_can_create_formal_session(study1_client, researcher_headers):
    response = study1_client.post("/api/study1/sessions", headers=researcher_headers, json=formal_session("draft-task"))
    assert response.status_code == 409
    assert response.json["error"] == "TASK_NOT_VALIDATED"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_task_registry.py backend/tests/study1/test_task_assignment.py -q`

Expected: missing registry functions and routes.

- [ ] **Step 3: Implement registry validation and researcher APIs**

Implement `validate_task_definition`, `create_task_definition`, `replace_draft_facts`, `validate_and_publish_task`, and deterministic `assign_participant_slots`. Add researcher routes:

```text
POST /api/study1/task-definitions
PUT  /api/study1/task-definitions/{task_definition_id}
POST /api/study1/task-definitions/{task_definition_id}/validate
GET  /api/study1/task-definitions?status=validated
GET  /api/study1/task-definitions/{task_definition_id}
```

Persist role and fact assignments once and emit `role_assignment_created` and `fact_assignment_created` events.

- [ ] **Step 4: Run registry, permission, and material tests**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_task_registry.py backend/tests/study1/test_task_assignment.py backend/tests/study1/test_invites_permissions.py backend/tests/study1/test_submissions_materials.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/study1/task_registry.py backend/study1/services.py backend/study1/routes.py backend/tests/study1/test_task_registry.py backend/tests/study1/test_task_assignment.py
git commit -m "feat(study1): register validated hidden profile tasks"
```

### Task 3: Freeze canonical Session protocol configuration

**Files:**
- Create: `backend/study1/protocol_config.py`
- Modify: `backend/study1/services.py`
- Modify: `backend/study1/routes.py`
- Modify: `backend/study1/state_machine.py`
- Modify: `.env.example`
- Test: `backend/tests/study1/test_protocol_config.py`

- [ ] **Step 1: Write failing canonicalization and freeze tests**

```python
def test_protocol_requires_every_phase_duration_and_audio_only_mode():
    with pytest.raises(ProtocolConfigError):
        normalize_protocol_config_v2({"recording_mode": "audio_video"})

def test_started_session_rejects_material_and_config_mutation(formal_service):
    session = formal_service.started_session()
    with pytest.raises(Study1ServiceError) as error:
        formal_service.add_materials(session["session_id"], "principal", [material()])
    assert error.value.code == "CONFIGURATION_FROZEN"
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_protocol_config.py -q`

Expected: protocol V2 and freeze checks are absent.

- [ ] **Step 3: Implement the canonical V2 snapshot**

Implement `ProtocolConfigV2`, `normalize_protocol_config_v2`, `canonical_protocol_json`, `compute_protocol_checksum`, `freeze_protocol_snapshot`, `assert_protocol_runtime_match`, and `clone_protocol_values`. Require all phase keys, IANA timezone, audio-only mode, fixed authority, provider/model/prompt/template/sampling values, failure and retention policies, disabled ReSync flag, and non-unknown build IDs in formal mode.

Add `PUT /api/study1/sessions/{session_id}/protocol-config` for waiting SETUP only. Recompute the final checksum over configuration, task, assignments, and materials at start.

- [ ] **Step 4: Run protocol, clone, and researcher control tests**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_protocol_config.py backend/tests/study1/test_researcher_controls.py backend/tests/study1/test_formal_protocol_requirements.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/study1/protocol_config.py backend/study1/services.py backend/study1/routes.py backend/study1/state_machine.py backend/tests/study1/test_protocol_config.py .env.example
git commit -m "feat(study1): freeze canonical session protocol"
```

### Task 4: Centralize action policy and repair pause/material gates

**Files:**
- Create: `backend/study1/action_policy.py`
- Modify: `backend/study1/services.py`
- Modify: `backend/study1/state_machine.py`
- Modify: `backend/study1/routes.py`
- Test: `backend/tests/study1/test_action_policy.py`
- Test: `backend/tests/study1/test_protocol_bypass_regressions.py`

- [ ] **Step 1: Write failing policy regressions**

```python
@pytest.mark.parametrize("operation", ["submit", "advance", "issue_media_access"])
def test_paused_session_rejects_runtime_operations(formal_service, operation):
    session, actor = formal_service.paused_session()
    with pytest.raises(Study1ServiceError) as error:
        formal_service.invoke(operation, session, actor)
    assert error.value.code == "SESSION_PAUSED"

def test_material_read_is_phase_and_role_gated(formal_service):
    session, t1 = formal_service.session_in("PROXY_CONFIGURATION", role="teammate_1")
    with pytest.raises(Study1ServiceError) as error:
        formal_service.get_materials(session["session_id"], t1)
    assert error.value.code == "MATERIAL_ACCESS_NOT_AVAILABLE"
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_action_policy.py backend/tests/study1/test_protocol_bypass_regressions.py -q`

Expected: paused writes and early material reads currently succeed.

- [ ] **Step 3: Implement one policy source**

Define `ActionPolicy`, `ACTION_POLICIES`, `authorize_action`, and `capabilities_for`. Route submissions, material reads/writes, review access, media tokens, phase transitions, and controls through this policy. Require enumerated override `reason_code` and non-empty `note`. Termination emits an idempotent `STOP_SESSION` media command.

- [ ] **Step 4: Run policy, state, media, and material tests**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_action_policy.py backend/tests/study1/test_protocol_bypass_regressions.py backend/tests/study1/test_state_machine.py backend/tests/study1/test_media_access.py backend/tests/study1/test_submissions_materials.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/study1/action_policy.py backend/study1/services.py backend/study1/state_machine.py backend/study1/routes.py backend/tests/study1/test_action_policy.py backend/tests/study1/test_protocol_bypass_regressions.py
git commit -m "fix(study1): enforce status phase and material policy"
```

### Task 5: Bind exact formal instruments and separate individual decisions

**Files:**
- Create: `backend/study1/instruments.py`
- Create: `backend/study1/instrument_definitions/study1-v2.json`
- Create: `backend/study1/decisions.py`
- Modify: `backend/study1/services.py`
- Modify: `backend/study1/routes.py`
- Test: `backend/tests/study1/test_formal_instruments.py`
- Test: `backend/tests/study1/test_decisions.py`

- [ ] **Step 1: Write failing instrument and candidate tests**

```python
def test_formal_instrument_rejects_wrong_order(catalog, session_binding):
    answers = [{"item_id": "confidence", "response": 4}, {"item_id": "choice", "response": "a"}]
    with pytest.raises(InstrumentValidationError, match="order"):
        validate_ordered_responses(catalog, session_binding, answers)

def test_decision_rejects_free_text_candidate(formal_service, principal):
    with pytest.raises(Study1ServiceError) as error:
        formal_service.create_individual_decision(principal, "pre_individual", {"candidate_id": "Option A"})
    assert error.value.code == "INVALID_CANDIDATE_ID"
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_formal_instruments.py backend/tests/study1/test_decisions.py -q`

Expected: catalog and normalized decision services do not exist.

- [ ] **Step 3: Implement exact instruments and decision APIs**

Load a versioned role/phase instrument catalog with ordered item IDs and response constraints. Formal Sessions bind exact checksums; remove the `structured_instruments=false` bypass. Implement `DecisionKind` with `pre_individual`, `tentative_individual`, `team_final`, and `final_individual`.

```text
GET  /api/study1/sessions/{id}/me/instrument
POST /api/study1/sessions/{id}/decisions/pre-individual
POST /api/study1/sessions/{id}/decisions/tentative-individual
POST /api/study1/sessions/{id}/decisions/final-individual
```

Keep old submission endpoints as legacy adapters only.

- [ ] **Step 4: Run formal instrument, decision, and legacy submission tests**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_formal_instruments.py backend/tests/study1/test_decisions.py backend/tests/study1/test_submissions_materials.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/study1/instruments.py backend/study1/instrument_definitions/study1-v2.json backend/study1/decisions.py backend/study1/services.py backend/study1/routes.py backend/tests/study1/test_formal_instruments.py backend/tests/study1/test_decisions.py
git commit -m "feat(study1): enforce instruments and individual decisions"
```

### Task 6: Add shared team decision and follow-up revisions

**Files:**
- Create: `backend/study1/shared_artifacts.py`
- Modify: `backend/study1/services.py`
- Modify: `backend/study1/routes.py`
- Modify: `backend/study1/state_machine.py`
- Test: `backend/tests/study1/test_shared_artifacts.py`
- Test: `backend/tests/study1/test_shared_artifact_routes.py`

- [ ] **Step 1: Write failing three-confirmation tests**

```python
def test_new_revision_invalidates_prior_confirmations(team_service, three_actors):
    first = team_service.create_revision("team_final", None, {"candidate_id": "a", "rationale": "r"}, three_actors[0])
    for actor in three_actors:
        team_service.confirm(first.revision_id, actor)
    second = team_service.create_revision("team_final", first.revision_id, {"candidate_id": "b", "rationale": "new"}, three_actors[1])
    assert second.locked is False
    assert second.confirmed_roles == []

def test_locks_only_after_all_three_confirm_current_revision(team_service, three_actors):
    revision = team_service.current_revision()
    for actor in three_actors[:2]:
        assert team_service.confirm(revision.id, actor).locked is False
    assert team_service.confirm(revision.id, three_actors[2]).locked is True
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_shared_artifacts.py backend/tests/study1/test_shared_artifact_routes.py -q`

Expected: shared artifact service and routes do not exist.

- [ ] **Step 3: Implement append-only revisions and confirmations**

Implement optimistic parent revision checking, content validation, per-participant confirmation, lock projection, and immutable events. Locking `team_final` also creates the canonical `TEAM_FINAL` decision. Support:

```text
GET  /api/study1/sessions/{id}/shared-artifacts/{team_final|followup_task}
POST /api/study1/sessions/{id}/shared-artifacts/{kind}/revisions
POST /api/study1/sessions/{id}/shared-artifacts/{kind}/revisions/{revision_id}/confirm
```

- [ ] **Step 4: Run shared artifact and state tests**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_shared_artifacts.py backend/tests/study1/test_shared_artifact_routes.py backend/tests/study1/test_state_machine.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/study1/shared_artifacts.py backend/study1/services.py backend/study1/routes.py backend/study1/state_machine.py backend/tests/study1/test_shared_artifacts.py backend/tests/study1/test_shared_artifact_routes.py
git commit -m "feat(study1): add confirmed shared team artifacts"
```

### Task 7: Switch readiness and DTOs to canonical records

**Files:**
- Modify: `backend/study1/state_machine.py`
- Modify: `backend/study1/services.py`
- Modify: `backend/study1/export_service.py`
- Modify: `backend/tests/study1/test_end_to_end_export.py`
- Test: `backend/tests/study1/test_formal_state_machine.py`
- Test: `backend/tests/study1/test_formal_export.py`

- [ ] **Step 1: Write failing formal readiness tests**

```python
def test_final_phase_requires_team_lock_and_three_private_finals(formal_session):
    formal_session.lock_team_final()
    formal_session.submit_final("principal")
    assert formal_session.readiness()["missing_prerequisites"] == [
        "final_individual:teammate_1", "final_individual:teammate_2"
    ]

def test_pre_vote_capability_uses_pre_individual_completion(formal_session):
    dto = formal_session.participant_dto("principal")
    assert dto["capabilities"]["submit_pre_individual"] is True
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_formal_state_machine.py backend/tests/study1/test_formal_export.py -q`

Expected: readiness still uses legacy completion keys and export lacks formal objects.

- [ ] **Step 3: Implement canonical prerequisite projection and export**

Project prerequisites from persisted decisions, instruments, shared artifacts, review telemetry, and media events inside the repository transaction. Return `capabilities` in participant DTOs. Export task/facts/assignments, protocol snapshot, decisions, shared revisions/confirmations, and ordered instruments; mark legacy Sessions uncertifiable.

- [ ] **Step 4: Run the complete Platform A suite**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1 -q`

Expected: all backend Study 1 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/study1/state_machine.py backend/study1/services.py backend/study1/export_service.py backend/tests/study1/test_formal_state_machine.py backend/tests/study1/test_formal_export.py backend/tests/study1/test_end_to_end_export.py
git commit -m "feat(study1): drive workflow from canonical protocol records"
```
