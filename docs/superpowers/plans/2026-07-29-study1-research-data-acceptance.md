# Study 1 Research Data and Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Study 1 review, privacy, Summary handling, markers, exports, Study 2 extension contracts, and release acceptance reconstructable and enforceable.

**Architecture:** Add append-only research-data services around the canonical Platform A protocol and Media B artifacts. Keep identity mappings outside analysis data, proxy all media access through scoped A authorization, and certify exports/releases only when version and integrity checks pass.

**Tech Stack:** Flask, SQLAlchemy, PostgreSQL, FastAPI internal APIs, cryptography/Fernet, JSON Schema, pytest, Vitest, GitHub Actions.

Run frontend `npm.cmd` commands from `frontend/`; run Python and Git commands from the repository root.

---

### Task 1: Add separate consent scopes and scoped researcher authorization

**Files:**
- Create: `backend/study1/privacy_models.py`
- Create: `backend/study1/privacy_service.py`
- Create: `backend/study1/privacy_routes.py`
- Modify: `backend/study1/permissions.py`
- Modify: `backend/study1/routes.py`
- Modify: `backend/study1/services.py`
- Modify: `frontend/src/study1/components/ConsentPhase.vue`
- Modify: `frontend/src/study1/services/study1Api.js`
- Test: `backend/tests/study1/test_consent_scopes.py`
- Test: `backend/tests/study1/test_researcher_scopes.py`
- Test: `frontend/src/study1/components/ConsentPhase.spec.js`

- [ ] **Step 1: Write failing scope tests**

```python
@pytest.mark.parametrize("scope", ["audio_recording", "transcription", "ui_telemetry", "external_agent_processing"])
def test_each_consent_scope_is_recorded_separately(privacy_service, participant, scope):
    privacy_service.record_consent(participant, {scope: True}, version="consent-v2")
    assert privacy_service.scope_state(participant, scope).granted is True

def test_raw_media_requires_researcher_scope(study1_client, operator_headers):
    response = study1_client.get("/api/study1/sessions/s1/recordings/r1", headers=operator_headers)
    assert response.status_code == 403
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_consent_scopes.py backend/tests/study1/test_researcher_scopes.py -q`

Expected: consent is one combined checkbox and researcher auth has no scopes.

- [ ] **Step 3: Implement audio-only consent and researcher scopes**

Persist versioned consent for audio recording, transcription, UI telemetry, and external Agent/provider processing. Do not add any video scope. Add researcher scopes `operate`, `export_analysis`, `read_raw_media`, `quality_audit`, and `privacy_admin`; enforce raw replay/download and privacy routes server-side.

- [ ] **Step 4: Run backend and frontend consent tests**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_consent_scopes.py backend/tests/study1/test_researcher_scopes.py -q`

Run: `npm.cmd test -- --run src/study1/components/ConsentPhase.spec.js`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/study1/privacy_models.py backend/study1/privacy_service.py backend/study1/privacy_routes.py backend/study1/permissions.py backend/study1/routes.py backend/study1/services.py backend/tests/study1/test_consent_scopes.py backend/tests/study1/test_researcher_scopes.py frontend/src/study1/components/ConsentPhase.vue frontend/src/study1/components/ConsentPhase.spec.js frontend/src/study1/services/study1Api.js
git commit -m "feat(study1): separate consent and researcher scopes"
```

### Task 2: Add encrypted identity vault and controlled retention workflow

**Files:**
- Create: `backend/study1/identity_vault.py`
- Create: `backend/study1/retention_service.py`
- Create: `backend/scripts/run_study1_retention.py`
- Create: `frontend/src/study1/components/WithdrawalPhase.vue`
- Create: `frontend/src/study1/components/WithdrawalPhase.spec.js`
- Modify: `backend/requirements.txt`
- Modify: `.env.example`
- Modify: `backend/study1/privacy_routes.py`
- Modify: `media_service/app/commands.py`
- Modify: `media_service/app/runtime.py`
- Test: `backend/tests/study1/test_identity_vault.py`
- Test: `backend/tests/study1/test_retention.py`
- Test: `media_service/tests/test_retention.py`

- [ ] **Step 1: Write failing vault isolation and dry-run tests**

```python
def test_identity_value_is_encrypted_and_absent_from_analysis_export(vault, export_service):
    vault.store("pseudo-1", "external-subject-7")
    assert b"external-subject-7" not in vault.raw_row("pseudo-1").encrypted_value
    assert "external-subject-7" not in export_service.export_text("session-1")

def test_retention_requires_dry_run_then_second_approval(retention):
    job = retention.create_dry_run("session-1")
    with pytest.raises(RetentionError):
        retention.execute(job.id, approved_manifest_checksum="wrong")
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_identity_vault.py backend/tests/study1/test_retention.py media_service/tests/test_retention.py -q`

Expected: vault and retention services do not exist.

- [ ] **Step 3: Implement isolated encryption and approved purge commands**

Use a separate `STUDY1_IDENTITY_DATABASE_URL` and `STUDY1_VAULT_KEY` for authenticated encryption. Analysis exports never join the vault. Implement withdrawal/disposition requests and retention jobs with dry-run manifests, checksum confirmation, second approval, A-issued `PURGE_SESSION_MEDIA`, and non-identifying tombstones.

- [ ] **Step 4: Run privacy and retention tests**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_identity_vault.py backend/tests/study1/test_retention.py media_service/tests/test_retention.py -q`

Run: `npm.cmd test -- --run src/study1/components/WithdrawalPhase.spec.js`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/study1/identity_vault.py backend/study1/retention_service.py backend/scripts/run_study1_retention.py backend/requirements.txt .env.example backend/study1/privacy_routes.py backend/tests/study1/test_identity_vault.py backend/tests/study1/test_retention.py media_service/app/commands.py media_service/app/runtime.py media_service/tests/test_retention.py frontend/src/study1/components/WithdrawalPhase.vue frontend/src/study1/components/WithdrawalPhase.spec.js
git commit -m "feat(study1): govern identity and data retention"
```

### Task 3: Compute reliable Review telemetry on the server

**Files:**
- Create: `backend/study1/review_telemetry.py`
- Modify: `backend/study1/models.py`
- Modify: `backend/study1/services.py`
- Modify: `backend/study1/routes.py`
- Modify: `backend/study1/state_machine.py`
- Test: `backend/tests/study1/test_review_telemetry.py`
- Test: `backend/tests/study1/test_review.py`

- [ ] **Step 1: Write failing deduplication and active-time tests**

```python
def test_hidden_or_stale_heartbeat_time_is_not_active(telemetry):
    telemetry.record_batch(visit("v1"), [enter(1), hidden(2), heartbeat(3, after_seconds=20)])
    assert telemetry.summary("v1").active_seconds == 0

def test_duplicate_sequence_is_idempotent(telemetry):
    event = heartbeat(2)
    telemetry.record_batch(visit("v1"), [event, event])
    assert telemetry.event_count("v1") == 1
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_review_telemetry.py backend/tests/study1/test_review.py -q`

Expected: server currently accepts client wall-clock active seconds.

- [ ] **Step 3: Implement visits, sequenced events, and server accumulation**

Persist review visits and append-only events keyed by `(visit_id, sequence_no)`. Add `POST /api/study1/sessions/{id}/review-events/batch`. Count time only while visible/focused with heartbeat gaps at most 15 seconds. Store segment intersection intervals, scroll ranges, transcript toggles, and replay ranges. Drive minimum-review readiness from server totals.

- [ ] **Step 4: Run Review and state tests**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_review_telemetry.py backend/tests/study1/test_review.py backend/tests/study1/test_state_machine.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/study1/review_telemetry.py backend/study1/models.py backend/study1/services.py backend/study1/routes.py backend/study1/state_machine.py backend/tests/study1/test_review_telemetry.py backend/tests/study1/test_review.py
git commit -m "feat(study1): compute active review telemetry"
```

### Task 4: Add deterministic Summary attempts, failure actions, and QA

**Files:**
- Create: `media_service/app/summary_attempts.py`
- Modify: `media_service/app/summary.py`
- Modify: `media_service/app/pipeline.py`
- Modify: `media_service/app/repository.py`
- Modify: `media_service/app/export.py`
- Create: `backend/study1/summary_service.py`
- Modify: `backend/study1/services.py`
- Modify: `backend/study1/routes.py`
- Modify: `backend/study1/state_machine.py`
- Test: `media_service/tests/test_summary_attempts.py`
- Test: `backend/tests/study1/test_summary_failure_policy.py`
- Test: `backend/tests/study1/test_summary_qa.py`

- [ ] **Step 1: Write failing first-attempt and drift tests**

```python
@pytest.mark.asyncio
async def test_first_summary_failure_can_retry_without_prior_summary(service):
    failed = await service.generate("s1", frozen_config())
    retried = await service.retry_same_config("s1", failed.attempt_id, reason="Provider recovered")
    assert retried.parent_attempt_id == failed.attempt_id

def test_retry_rejects_configuration_drift(summary_service):
    with pytest.raises(SummaryPolicyError, match="frozen"):
        summary_service.retry_same_config("s1", checksum="changed", reason="retry")
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_summary_attempts.py backend/tests/study1/test_summary_failure_policy.py backend/tests/study1/test_summary_qa.py -q`

Expected: Summary errors lack attempt records and first failure cannot use the existing retry UI.

- [ ] **Step 3: Implement attempts, five-section output, policy actions, and QA**

Persist every attempt with complete prompt, transcript checksum/version, model/provider, sampling, start/end, output/error, and frozen config checksum. Emit `SUMMARY_STARTED`, `SUMMARY_SUCCEEDED`, and `SUMMARY_FAILED`. Allow only `retry_same_config`, `transcript_only`, and `terminate`, each with reason. Add private researcher QA fields for omission, misattribution, hallucination, decision status, and action item errors.

- [ ] **Step 4: Run Summary suites**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_summary_attempts.py media_service/tests/test_transcript_summary.py backend/tests/study1/test_summary_failure_policy.py backend/tests/study1/test_summary_qa.py backend/tests/study1/test_state_machine.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add media_service/app/summary_attempts.py media_service/app/summary.py media_service/app/pipeline.py media_service/app/repository.py media_service/app/export.py media_service/tests/test_summary_attempts.py backend/study1/summary_service.py backend/study1/services.py backend/study1/routes.py backend/study1/state_machine.py backend/tests/study1/test_summary_failure_policy.py backend/tests/study1/test_summary_qa.py
git commit -m "feat(study1): govern summary attempts and quality"
```

### Task 5: Add typed markers and deterministic interview replay

**Files:**
- Create: `backend/study1/marker_service.py`
- Create: `backend/study1/replay_service.py`
- Modify: `backend/study1/models.py`
- Modify: `backend/study1/routes.py`
- Modify: `backend/study1/services.py`
- Test: `backend/tests/study1/test_markers_replay.py`

- [ ] **Step 1: Write failing visibility and merge tests**

```python
def test_researcher_marker_is_not_returned_to_participants(marker_service):
    marker_service.create(researcher_marker(participant_visible=False))
    assert marker_service.list_for_participant("s1", "principal") == []

def test_replay_merges_overlapping_context_windows(replay_service):
    items = replay_service.generate("s1", markers_at(30, 35), context_seconds=10)
    assert [(item.start_second, item.end_second) for item in items] == [(20, 45)]
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_markers_replay.py -q`

Expected: typed marker and replay services do not exist.

- [ ] **Step 3: Implement markers and fixed replay selection**

Support participant types `confusing`, `unexpected`, `uncomfortable`, and `key_decision`, plus researcher technical/other markers. Bind absolute ranges, segments, recordings, source, visibility, and reasons. Generate a versioned replay list using fixed context windows and overlap merging without LLM interpretation.

- [ ] **Step 4: Run marker, recording access, and Review tests**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_markers_replay.py backend/tests/study1/test_review.py backend/tests/study1/test_media_access.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/study1/marker_service.py backend/study1/replay_service.py backend/study1/models.py backend/study1/routes.py backend/study1/services.py backend/tests/study1/test_markers_replay.py
git commit -m "feat(study1): generate marked interview replay"
```

### Task 6: Normalize incident codes and aggregate authenticated quality data

**Files:**
- Create: `backend/study1/incident_codes.py`
- Create: `backend/study1/quality_service.py`
- Modify: `backend/study1/media_gateway.py`
- Modify: `backend/study1/services.py`
- Modify: `backend/study1/routes.py`
- Test: `backend/tests/study1/test_incident_codes.py`
- Test: `backend/tests/study1/test_quality_monitoring.py`

- [ ] **Step 1: Write failing error-code and stale-metric tests**

```python
def test_unknown_incident_code_is_rejected(quality_service):
    with pytest.raises(Study1ServiceError) as error:
        quality_service.record_incident("s1", code="free_text_failure", note="x")
    assert error.value.code == "INVALID_INCIDENT_CODE"

def test_stale_metric_is_reported_unknown(quality_service):
    quality_service.record_metrics("s1", metric_batch(observed_minutes_ago=10))
    assert quality_service.snapshot("s1")["rtc"]["status"] == "unknown"
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_incident_codes.py backend/tests/study1/test_quality_monitoring.py -q`

Expected: incidents accept arbitrary categories and there is no authenticated metric aggregation.

- [ ] **Step 3: Implement the catalog and quality endpoints**

Define stable codes for disconnect, recorder, ASR, LLM, TTS, Summary, callback, permission, and protocol errors. Add participant-authenticated metric ingestion, B status aggregation, staleness handling, p50/p95 latency, last success/error, and researcher-only quality/integrity views. Never translate a technical error into participant silence or a Proxy choice.

- [ ] **Step 4: Run quality, incident, and researcher tests**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_incident_codes.py backend/tests/study1/test_quality_monitoring.py backend/tests/study1/test_researcher_controls.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/study1/incident_codes.py backend/study1/quality_service.py backend/study1/media_gateway.py backend/study1/services.py backend/study1/routes.py backend/tests/study1/test_incident_codes.py backend/tests/study1/test_quality_monitoring.py
git commit -m "feat(study1): report coded media quality incidents"
```

### Task 7: Produce canonical export and actionable integrity reports

**Files:**
- Create: `backend/study1/export_schema.py`
- Create: `backend/study1/integrity_service.py`
- Modify: `backend/study1/export_service.py`
- Modify: `backend/study1/services.py`
- Create: `backend/scripts/audit_study1_export.py`
- Create: `docs/study1-data-dictionary.md`
- Test: `backend/tests/study1/test_export_schema.py`
- Test: `backend/tests/study1/test_integrity_service.py`
- Modify: `backend/tests/study1/test_end_to_end_export.py`

- [ ] **Step 1: Write failing golden-export assertions**

```python
def test_export_can_join_utterance_recording_marker_and_decision(export_zip):
    data = read_export(export_zip)
    assert data.utterances[0].clock_id == data.media_manifest[0].clock_id
    assert data.markers[0].segment_ids[0] == data.utterances[0].utterance_id
    assert data.export_manifest["build_versions"]["backend"] != "unknown"

def test_partial_media_export_is_explicit(export_without_b):
    report = read_json(export_without_b, "integrity_report.json")
    assert "MEDIA_EXPORT_UNAVAILABLE" in report["errors"]
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_export_schema.py backend/tests/study1/test_integrity_service.py backend/tests/study1/test_end_to_end_export.py -q`

Expected: current bundle drops media/Agent metadata and lacks the canonical manifest.

- [ ] **Step 3: Implement normalized export and certification**

Create `export_manifest.json` plus normalized events, utterances, Agent turns, Summary attempts/QA, decisions, instrument responses, Review visits/events, markers/replay, consent, incidents, media manifest, and integrity report. Include UTC, local timezone/offset, media-relative time, schema/protocol/task/release/build/model/prompt/template/instrument checksums. Refuse certification for unknown or mismatched versions.

- [ ] **Step 4: Run export and full backend tests**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_export_schema.py backend/tests/study1/test_integrity_service.py backend/tests/study1/test_end_to_end_export.py backend/tests/study1 -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/study1/export_schema.py backend/study1/integrity_service.py backend/study1/export_service.py backend/study1/services.py backend/scripts/audit_study1_export.py backend/tests/study1/test_export_schema.py backend/tests/study1/test_integrity_service.py backend/tests/study1/test_end_to_end_export.py docs/study1-data-dictionary.md
git commit -m "feat(study1): export reconstructable research data"
```

### Task 8: Add Study 2 read-only contracts and disabled extension slot

**Files:**
- Create: `backend/study1/study2_contracts.py`
- Create: `backend/study1/study2_service.py`
- Create: `backend/study1/study2_routes.py`
- Modify: `backend/app.py`
- Modify: `backend/study1/permissions.py`
- Create: `frontend/src/study1/components/StudyExtensionSlot.vue`
- Create: `frontend/src/study1/components/StudyExtensionSlot.spec.js`
- Create: `frontend/src/study1/extensions/registry.js`
- Create: `contracts/study2-readonly-contract-v1.md`
- Test: `backend/tests/study1/test_study2_contracts.py`
- Test: `backend/tests/study1/test_study2_permissions.py`

- [ ] **Step 1: Write failing isolation and feature tests**

```python
def test_principal_cannot_read_utterances_while_isolated(study2_service, principal):
    with pytest.raises(Study1ServiceError) as error:
        study2_service.utterances("s1", principal)
    assert error.value.code == "STUDY2_DATA_NOT_AVAILABLE"

def test_study1_always_disables_resync(study2_service):
    assert study2_service.features("s1")["resync_enabled"] is False
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_study2_contracts.py backend/tests/study1/test_study2_permissions.py -q`

Expected: dedicated read-only interfaces do not exist.

- [ ] **Step 3: Implement versioned read-only APIs and local slot**

Expose filtered utterances, decisions, facts, Proxy authority, baseline recap, features, and allowlisted module telemetry with cursor/ETag support. The Study 1 protocol rejects enabled ReSync or a module ID. The frontend slot loads only local allowlisted modules and renders nothing intelligent when disabled.

- [ ] **Step 4: Run backend and frontend Study 2 tests**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_study2_contracts.py backend/tests/study1/test_study2_permissions.py -q`

Run: `npm.cmd test -- --run src/study1/components/StudyExtensionSlot.spec.js`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/study1/study2_contracts.py backend/study1/study2_service.py backend/study1/study2_routes.py backend/app.py backend/study1/permissions.py backend/tests/study1/test_study2_contracts.py backend/tests/study1/test_study2_permissions.py frontend/src/study1/components/StudyExtensionSlot.vue frontend/src/study1/components/StudyExtensionSlot.spec.js frontend/src/study1/extensions/registry.js contracts/study2-readonly-contract-v1.md
git commit -m "feat(study1): expose Study 2 read only contracts"
```

### Task 9: Freeze releases and provide executable acceptance support

**Files:**
- Create: `scripts/build_study1_release_manifest.py`
- Create: `scripts/verify_study1_release.py`
- Create: `release/study1-release.schema.json`
- Create: `.github/workflows/study1-acceptance.yml`
- Create: `docs/study1-researcher-sop.md`
- Create: `docs/study1-pilot-checklist.md`
- Create: `docs/study1-known-issues.md`
- Create: `docs/study1-privacy-runbook.md`
- Create: `docs/study1-release-freeze.md`
- Modify: `docs/study1-formal-acceptance.md`
- Modify: `docs/study1-integration-guide.md`
- Test: `backend/tests/study1/test_release_freeze.py`
- Test: `media_service/tests/test_release_handshake.py`
- Test: `tests/acceptance/test_study1_export_reconstruction.py`

- [ ] **Step 1: Write failing release verification tests**

```python
def test_release_rejects_unknown_build(release_builder):
    with pytest.raises(ReleaseError, match="unknown"):
        release_builder.build({"backend_build": "unknown"})

def test_technical_acceptance_cannot_claim_data_collection_ready_without_signoffs(verifier):
    result = verifier.verify(manifest_without_external_signoffs())
    assert result.status == "technical_acceptance"
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1/test_release_freeze.py media_service/tests/test_release_handshake.py tests/acceptance/test_study1_export_reconstruction.py -q`

Expected: release builder, handshake, and acceptance reconstruction do not exist.

- [ ] **Step 3: Implement manifest, verification, CI, and operator materials**

Hash commit, images, DB revisions, protocol/task/facts, models/providers, Prompt/template files, sampling, consent/instrument/marker/replay/retention versions. A sends `release_id/checksum` to B and B rejects drift. Add a synthetic-audio runner and templates for ten stress runs, a three-device 60-minute stability run, three-to-five usability pilots, and three-to-five full pilots. Clearly mark IRB, real participants, production WSS/TURN, and production credentials as external signoffs.

- [ ] **Step 4: Run all automated acceptance gates**

Run: `python -m pytest -p no:cacheprovider backend/tests/study1 media_service/tests tests/acceptance -q`

Run: `npm.cmd test -- --run`

Run: `npm.cmd run build`

Expected: all tests and the frontend build pass.

- [ ] **Step 5: Commit**

```powershell
git add scripts/build_study1_release_manifest.py scripts/verify_study1_release.py release/study1-release.schema.json .github/workflows/study1-acceptance.yml docs/study1-researcher-sop.md docs/study1-pilot-checklist.md docs/study1-known-issues.md docs/study1-privacy-runbook.md docs/study1-release-freeze.md docs/study1-formal-acceptance.md docs/study1-integration-guide.md backend/tests/study1/test_release_freeze.py media_service/tests/test_release_handshake.py tests/acceptance/test_study1_export_reconstruction.py
git commit -m "chore(study1): freeze and verify formal releases"
```
