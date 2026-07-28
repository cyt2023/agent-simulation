# Study 1 Media Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Study 1's independent B-side audio meeting and single-Proxy service, integrate it through A's authenticated boundary, and preserve A as the only experiment-phase and primary-database authority.

**Architecture:** `media_service/` is an async FastAPI deployment backed by its own PostgreSQL schema. It accepts idempotent A-to-B commands, manages LiveKit audio rooms and the single server-side X participant, creates timestamped transcripts and neutral summaries, then publishes artifacts and events to A through a durable outbox. Browsers continue to authenticate only with A; A issues short-lived, role-filtered media access and proxies protected status, replay, and export operations.

**Tech Stack:** Python 3.11, FastAPI, Uvicorn, Pydantic 2, SQLAlchemy 2, PostgreSQL 16, HTTPX, LiveKit OSS/Python SDK, OpenAI/Azure-compatible async adapters, Vue 3, `livekit-client`, Docker Compose, pytest.

---

## File Map

- `media_service/app/`: FastAPI boundary, configuration, persistence, command orchestration, providers, LiveKit adapter, runtime, artifacts, outbox, and recovery.
- `media_service/tests/`: unit and contract tests that run without external credentials; LiveKit integration tests are separately marked.
- `backend/study1/media_gateway.py`: A-side Mock/HTTP gateway selection and command transport.
- `backend/study1/services.py`: role-filtered Proxy context and B command construction.
- `backend/study1/routes.py`: authenticated media access, status, replay, retry, and export proxy routes.
- `backend/study1/export_service.py`: merge B's media bundle into A's final ZIP without exposing B storage paths.
- `frontend/src/study1/components/Study1VoiceRoom.vue`: audio-only device and LiveKit room experience.
- `frontend/src/study1/services/study1Api.js`: A-only browser API calls for media access.
- `docker-compose.yml`: isolated B database schema, LiveKit, and media service processes.

### Task 1: Align the design and scaffold the service

**Files:**
- Modify: `docs/superpowers/specs/2026-07-26-study1-media-service-design.md`
- Create: `media_service/pyproject.toml`
- Create: `media_service/Dockerfile`
- Create: `media_service/app/__init__.py`
- Create: `media_service/app/config.py`
- Create: `media_service/app/main.py`
- Test: `media_service/tests/test_health.py`

- [ ] **Step 1: Write the failing health/config test**

```python
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_reports_service_and_schema(monkeypatch):
    settings = Settings(
        database_url="postgresql+psycopg://media:secret@postgres/study1_media",
        database_schema="study1_media",
        a_to_b_service_token="a-secret",
        b_to_a_internal_key="b-secret",
        a_base_url="http://backend:5000",
        livekit_url="ws://livekit:7880",
        livekit_api_key="devkey",
        livekit_api_secret="secret",
    )
    response = TestClient(create_app(settings, initialize_database=False)).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"service": "study1-media", "status": "ok", "schema": "study1_media"}
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_health.py -q`

Expected: collection fails because `app.config` and `app.main` do not exist.

- [ ] **Step 3: Implement settings, application factory, dependencies, and container entrypoint**

`Settings` must use the exact environment names `MEDIA_DATABASE_URL`, `MEDIA_DATABASE_SCHEMA`, `A_TO_B_SERVICE_TOKEN`, `STUDY1_INTERNAL_API_KEY`, `A_BASE_URL`, `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET`. `create_app(settings, initialize_database=True)` must expose `/healthz` and attach settings/database/services to `app.state`.

- [ ] **Step 4: Replace every active SQLite/WAL design statement**

The design must state that B uses a dedicated `study1_media` PostgreSQL schema/user, may share the cluster, and its credentials cannot access `humanagent_collab`.

- [ ] **Step 5: Run the test and commit**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_health.py -q`

Expected: `1 passed`.

Commit: `git commit -m "feat: scaffold Study 1 media service"`

### Task 2: Persist commands, runtimes, artifacts, and outbox rows

**Files:**
- Create: `media_service/app/db.py`
- Create: `media_service/app/models.py`
- Create: `media_service/app/schemas.py`
- Create: `media_service/app/repository.py`
- Test: `media_service/tests/conftest.py`
- Test: `media_service/tests/test_repository.py`

- [ ] **Step 1: Write repository tests for durable idempotency**

```python
def test_command_id_and_semantic_key_are_idempotent(repository, command):
    first = repository.accept_command(command, semantic_key="s:5:START_PROXY_MEETING")
    replay = repository.accept_command(command, semantic_key="s:5:START_PROXY_MEETING")
    same_effect = repository.accept_command(
        command.model_copy(update={"command_id": "other-id"}),
        semantic_key="s:5:START_PROXY_MEETING",
    )
    assert first.duplicate is False
    assert replay.duplicate is True
    assert same_effect.duplicate is True
    assert same_effect.command_id == first.command_id
```

Add tests for persisted runtime state, participant connections, transcript segments, artifacts, incidents, and outbox retry fields.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_repository.py -q`

Expected: fails because repository models do not exist.

- [ ] **Step 3: Implement the schema**

Create SQLAlchemy models `MediaCommand`, `MediaRuntime`, `MediaConnection`, `TranscriptSegment`, `MediaArtifact`, `MediaIncident`, and `OutboxMessage`. Enforce unique constraints on `command_id`, `semantic_key`, `(session_id, kind, version)`, and `event_id`. Store JSON payloads as JSON and all timestamps as timezone-aware UTC.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_repository.py -q`

Expected: all repository tests pass against SQLite only as an injected test engine; production settings remain PostgreSQL-only.

Commit: `git commit -m "feat: persist media commands and runtime data"`

### Task 3: Authenticate and validate the single command endpoint

**Files:**
- Create: `media_service/app/auth.py`
- Create: `media_service/app/commands.py`
- Modify: `media_service/app/main.py`
- Test: `media_service/tests/test_commands.py`

- [ ] **Step 1: Write failing command-contract tests**

Test that missing/wrong bearer credentials return 401, malformed envelopes return 422, unsupported commands return 422, accepted commands return 202, exact replay returns `duplicate: true`, and a second command ID with the same semantic lifecycle key returns the original result.

```python
def test_command_requires_service_bearer(client, valid_envelope):
    assert client.post("/internal/commands", json=valid_envelope).status_code == 401


def test_command_replay_returns_original_result(client, auth_headers, valid_envelope):
    first = client.post("/internal/commands", headers=auth_headers, json=valid_envelope)
    replay = client.post("/internal/commands", headers=auth_headers, json=valid_envelope)
    assert first.status_code == replay.status_code == 202
    assert replay.json()["duplicate"] is True
    assert replay.json()["command_id"] == valid_envelope["command_id"]
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_commands.py -q`

Expected: route returns 404.

- [ ] **Step 3: Implement command schemas and dispatcher**

Support exactly `START_PROXY_MEETING`, `END_CURRENT_MEETING`, `BEGIN_HANDOFF`, `START_SYNC_MEETING`, `REGENERATE_SUMMARY`, and `STOP_SESSION`. Persist before returning. Lifecycle semantic keys are `{session_id}:{phase_version}:{command}`; summary keys include source transcript checksum and source summary version.

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_commands.py -q`

Expected: all command tests pass.

Commit: `git commit -m "feat: accept authenticated idempotent media commands"`

### Task 4: Enforce the LiveKit room and role access matrix

**Files:**
- Create: `media_service/app/livekit.py`
- Create: `media_service/app/access.py`
- Modify: `media_service/app/main.py`
- Test: `media_service/tests/test_access.py`

- [ ] **Step 1: Write failing role-matrix tests**

```python
@pytest.mark.parametrize(
    ("phase", "role", "allowed"),
    [
        ("PROXY_MEETING", "principal", False),
        ("PROXY_MEETING", "teammate_1", True),
        ("PROXY_MEETING", "teammate_2", True),
        ("SYNC_MEETING", "principal", True),
        ("SYNC_MEETING", "teammate_1", True),
        ("SYNC_MEETING", "teammate_2", True),
    ],
)
def test_access_matrix(access_service, phase, role, allowed):
    result = access_service.issue_access("session-1", phase, 7, role, f"id-{role}")
    assert (result is not None) is allowed
```

Also assert X gets only the Proxy room, X is absent from sync grants, all browser grants deny video/screen publishing, room names are deterministic, tokens expire, and P receives a 403 rather than an empty Proxy token.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_access.py -q`

Expected: `AccessService` is missing.

- [ ] **Step 3: Implement token issuing and internal access route**

`POST /internal/media-access` accepts only A-authenticated identity and authoritative phase data. Return `room_name`, `url`, `token`, `expires_at`, and `captions_enabled: false`. Never accept a browser-supplied role directly.

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_access.py -q`

Commit: `git commit -m "feat: enforce Study 1 audio room access"`

### Task 5: Run one Proxy participant and an audio-only sync room

**Files:**
- Create: `media_service/app/runtime.py`
- Create: `media_service/app/audio.py`
- Create: `media_service/app/recording.py`
- Modify: `media_service/app/commands.py`
- Test: `media_service/tests/test_runtime.py`

- [ ] **Step 1: Write failing runtime lifecycle tests**

Use an injected `FakeLiveKit` and real runtime coordinator. Assert one X participant per session, subscriptions only to T1/T2 microphone tracks, one X audio track published to both, reconnect does not create a second X, explicit end stops recording and emits `MEETING_ENDED`, handoff cancels TTS and removes X before `HANDOFF_COMPLETE`, and sync never invokes Proxy providers.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_runtime.py -q`

- [ ] **Step 3: Implement the coordinator**

Model states `IDLE`, `PREPARING`, `READY`, `ACTIVE`, `ENDING`, `PROCESSING`, `HANDING_OFF`, `STOPPED`, and `ERROR`. Long-lived work is created through an injected task launcher so command HTTP responses remain bounded. On restart, reconcile persisted nonterminal runtimes with LiveKit before starting work.

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_runtime.py -q`

Commit: `git commit -m "feat: add single Proxy media runtime"`

### Task 6: Add provider abstractions and neutral transcript/summary artifacts

**Files:**
- Create: `media_service/app/providers/base.py`
- Create: `media_service/app/providers/mock.py`
- Create: `media_service/app/providers/openai.py`
- Create: `media_service/app/providers/azure.py`
- Create: `media_service/app/transcript.py`
- Create: `media_service/app/summary.py`
- Create: `media_service/app/prompts/proxy-v1.txt`
- Create: `media_service/app/prompts/neutral-summary-v1.txt`
- Test: `media_service/tests/test_transcript_summary.py`

- [ ] **Step 1: Write failing provider and neutrality tests**

Assert segments preserve speaker, start/end milliseconds, text, confidence, provider version, and final/interim status. Summary output must use only transcript facts, contain no recommendation or second-person instruction, include uncertainty when evidence conflicts, and retain prompt/model/config versions.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_transcript_summary.py -q`

- [ ] **Step 3: Implement async protocols and adapters**

Define `StreamingAsrProvider`, `LanguageModelProvider`, and `StreamingTtsProvider`; implement deterministic Mock adapters and OpenAI/Azure adapters selected by environment. Proxy prompts may read only A's `authorized_context`; never append T1/T2 transcripts as hidden private material. Validate summaries with a deterministic prohibited-language check and fail closed into `MEDIA_ERROR` after one configured retry.

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_transcript_summary.py -q`

Commit: `git commit -m "feat: generate auditable neutral media artifacts"`

### Task 7: Deliver callbacks through a durable outbox and export protected media

**Files:**
- Create: `media_service/app/callbacks.py`
- Create: `media_service/app/outbox.py`
- Create: `media_service/app/export.py`
- Modify: `media_service/app/main.py`
- Test: `media_service/tests/test_outbox_export.py`

- [ ] **Step 1: Write failing delivery and export tests**

Assert B sends only to A's media-event/artifact endpoints with `X-Study1-Internal-Key`, retries transient failures without duplicate effects, resumes pending rows after restart, exposes researcher status with device/ASR/Proxy/recording/provider versions, and exports only paths belonging to the requested session.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_outbox_export.py -q`

- [ ] **Step 3: Implement outbox/status/replay/export endpoints**

Add authenticated internal routes `GET /internal/sessions/{session_id}/status`, `GET /internal/sessions/{session_id}/export`, and `GET /internal/sessions/{session_id}/recordings/{recording_id}` with validated byte ranges. ZIP contents are `media_status.json`, `commands.jsonl`, `runtime_events.jsonl`, `connections.jsonl`, `transcript.json`, `summary.json`, `recording_manifest.json`, `agent_log.jsonl`, `incidents.jsonl`, and referenced audio files.

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_outbox_export.py -q`

Commit: `git commit -m "feat: deliver and export Study 1 media data"`

### Task 8: Connect A to B without changing phase authority

**Files:**
- Modify: `backend/study1/media_gateway.py`
- Modify: `backend/study1/services.py`
- Modify: `backend/study1/routes.py`
- Modify: `backend/study1/export_service.py`
- Modify: `backend/app.py`
- Test: `backend/tests/study1/test_http_media_gateway.py`
- Test: `backend/tests/study1/test_media_access.py`

- [ ] **Step 1: Write failing A-side gateway and authorization tests**

Use a fake HTTP transport. Assert `MEDIA_GATEWAY_MODE=http` selects `HttpMediaGateway`, A sends a bearer token, timeouts return a controlled 502, `START_PROXY_MEETING` payload is built from the principal's locked authorization/config submissions and authorized P materials only, P cannot receive Proxy access, and T1/T2 private material is absent.

- [ ] **Step 2: Verify RED**

Run: `$env:PYTHONPATH=(Resolve-Path 'backend').Path; python -m pytest -p no:cacheprovider backend/tests/study1/test_http_media_gateway.py backend/tests/study1/test_media_access.py -q`

- [ ] **Step 3: Implement HTTP gateway and A-only browser proxies**

Add participant `POST /api/study1/sessions/{session_id}/media-access`; researcher `GET /media-status`, `POST /media-commands` with the two v1 commands, and `GET /media-export`; and principal-only review recording range proxy. A supplies token identity and current phase/version and never forwards a client role claim. Existing Mock remains the default for regression tests.

- [ ] **Step 4: Merge B data into A's export**

When HTTP media is configured, place B's ZIP entries under `media/` in the final A export. If B is unavailable, retain A export and add `media/media_export_error.json` so the failure is auditable.

- [ ] **Step 5: Verify GREEN and commit**

Run: `$env:PYTHONPATH=(Resolve-Path 'backend').Path; python -m pytest -p no:cacheprovider backend/tests/study1 -q`

Expected: all old 33 tests plus new A integration tests pass.

Commit: `git commit -m "feat: integrate workflow service with media service"`

### Task 9: Add the Study 1 audio-room UI

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/src/study1/services/study1Api.js`
- Create: `frontend/src/study1/components/Study1VoiceRoom.vue`
- Modify: `frontend/src/study1/views/Study1Participant.vue`
- Test: `frontend/src/study1/components/Study1VoiceRoom.spec.js`

- [ ] **Step 1: Add Vitest and write failing component tests**

Test microphone permission/device selection, muted/joining/connected/reconnecting/error states, neutral P/T1/T2/X avatars, no video/screen controls, no caption panel by default, P waiting-room isolation during Proxy meeting, and room disconnect on phase/version change.

- [ ] **Step 2: Verify RED**

Run: `npm --prefix frontend test -- --run`

Expected: component/module missing.

- [ ] **Step 3: Implement the room**

Call A's `/media-access`, connect using `livekit-client`, publish only the selected microphone track, render remote audio elements, and disconnect on unmount or authoritative phase change. The component never calls B directly and does not cache a room token beyond memory.

- [ ] **Step 4: Mount by role and phase**

Show `Study1VoiceRoom` for T1/T2 in `PROXY_MEETING` and P/T1/T2 in `SYNC_MEETING`; keep P in the existing isolated waiting room during `PROXY_MEETING`; show handoff status without X media during `HANDOFF`.

- [ ] **Step 5: Verify and commit**

Run: `npm --prefix frontend test -- --run && npm --prefix frontend run build`

Expected: component tests pass and Vite build succeeds.

Commit: `git commit -m "feat: add Study 1 audio meeting experience"`

### Task 10: Extend researcher operations

**Files:**
- Modify: `frontend/src/study1/services/study1Api.js`
- Modify: `frontend/src/study1/views/Study1Researcher.vue`
- Test: `frontend/src/study1/views/Study1Researcher.spec.js`

- [ ] **Step 1: Write failing researcher-console tests**

Assert the console displays B health, room, participant/device, ASR, Proxy, recording, provider/prompt versions, and incidents; offers `END_CURRENT_MEETING` only in active meeting phases; requires a reason for `REGENERATE_SUMMARY`; labels Mock controls only when `mode=mock`; and refreshes status after commands.

- [ ] **Step 2: Verify RED**

Run: `npm --prefix frontend test -- --run Study1Researcher.spec.js`

- [ ] **Step 3: Implement controls and status polling**

Poll A's media-status proxy every five seconds while a session is selected. Disable controls while commands are pending. Summary retry sends `{reason, source_summary_version}` and never changes A's phase.

- [ ] **Step 4: Verify and commit**

Run: `npm --prefix frontend test -- --run && npm --prefix frontend run build`

Commit: `git commit -m "feat: expose Study 1 media operations to researchers"`

### Task 11: Wire local deployment and operational documentation

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Create: `livekit.yaml`
- Modify: `docs/study1-integration-guide.md`
- Create: `media_service/README.md`
- Test: `media_service/tests/test_compose_contract.py`

- [ ] **Step 1: Write a failing Compose contract test**

Parse Compose YAML and assert services `livekit` and `media-service` exist; B receives a `MEDIA_DATABASE_URL` scoped to `study1_media`; LiveKit TCP/UDP ports are published; A uses `MEDIA_GATEWAY_MODE=http` and `MEDIA_SERVICE_URL=http://media-service:8000`; no secret has a production default; and dependency health checks are present.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_compose_contract.py -q`

- [ ] **Step 3: Add deployment configuration**

Run LiveKit on `7880`, media service on internal `8000`, and publish LiveKit RTC ports needed by browsers. Initialize the dedicated schema/user through `backend/database/docker-init.sql` while denying its access to `humanagent_collab`. Document TLS/WSS and TURN requirements for non-local deployment.

- [ ] **Step 4: Verify and commit**

Run: `docker compose config --quiet`

Expected: exit 0 with no unresolved required configuration.

Commit: `git commit -m "build: add Study 1 media deployment"`

### Task 12: End-to-end verification and PR

**Files:**
- Modify: `contracts/study1-media-contract.md`
- Modify: `docs/study1-integration-guide.md`

- [ ] **Step 1: Update the v1 contract**

Document `END_CURRENT_MEETING`, `REGENERATE_SUMMARY`, media access/status/export/replay endpoints, accepted/duplicate/runtime-state responses, authorized Proxy context, and the rule that these v1 extensions will be aligned with A later without changing their security semantics.

- [ ] **Step 2: Run all automated checks**

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest -p no:cacheprovider backend\tests\study1 media_service\tests -q
npm --prefix frontend test -- --run
npm --prefix frontend run build
docker compose config --quiet
```

Expected: all tests pass, Vite build succeeds, and Compose validates.

- [ ] **Step 3: Run the local integration smoke test**

Run: `docker compose up --build -d postgres livekit media-service backend frontend`

Verify: health endpoints respond; P receives 403 for Proxy media access; T1 receives a LiveKit token; exact command replay reports duplicate; researcher meeting end creates one outbox event; and the final export contains `media/` entries.

- [ ] **Step 4: Review the diff and commit remaining documentation**

Run: `git diff --check && git status --short`

Expected: no whitespace errors and only intended tracked changes plus the pre-existing untracked `Agent Simulation/` and `output/` directories.

- [ ] **Step 5: Push and create a PR without merging**

```powershell
git push -u origin codex/study1-media-service
gh pr create --base main --head codex/study1-media-service --title "feat: add Study 1 media and Proxy service" --body-file docs/superpowers/plans/2026-07-26-study1-media-service-pr.md
```

Expected: GitHub returns a pull-request URL. Do not merge the PR.

---

## Self-review

- Spec coverage: room isolation, single X, handoff, explicit meeting end, ASR, neutral summary, recording, callbacks, retry, replay, status, full export, A authority, device/reconnect UI, and researcher controls are mapped to Tasks 3-12.
- Placeholder scan: the plan contains no deferred implementation markers; post-v1 contract alignment is explicitly treated as documentation, not missing behavior.
- Type consistency: command, event, role, phase, runtime-state, artifact, and endpoint names match the design and v1 extensions throughout.
