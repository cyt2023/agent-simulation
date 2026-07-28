# Study 1 Chinese README Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the outdated root README with a Chinese, operations-first Study 1 guide and submit the user's upgraded neutral Proxy/summary safeguards.

**Architecture:** Treat executable routes, state enums, Compose, and `.env.example` as the source of truth. Keep the README useful as an entry point by documenting complete endpoint inventories and operational steps while linking field-level A/B schemas to the contract. Commit the existing prompt/runtime/test changes separately from documentation so reviewers can assess behavior and docs independently.

**Tech Stack:** Markdown, PowerShell, Docker Compose, Flask/Socket.IO, FastAPI, Vue 3, LiveKit, PostgreSQL, pytest, Vitest/Vite.

---

## File map

- Modify `README.md`: Chinese project overview, setup tutorial, role workflow, interfaces, export, tests, troubleshooting, and legacy compatibility.
- Commit existing changes in `media_service/app/prompts/proxy-v1.txt`: live Proxy neutral-relay instructions.
- Commit existing changes in `media_service/app/prompts/neutral-summary-v1.txt`: neutral summary instructions.
- Commit existing changes in `media_service/app/pipeline.py`: fail-closed live Proxy output validation and audit event.
- Commit existing changes in `media_service/app/summary.py`: shared neutral-language validator and expanded prohibited patterns.
- Commit existing changes in `media_service/tests/test_proxy_pipeline.py`: prompt and live-response blocking coverage.
- Commit existing changes in `media_service/tests/test_transcript_summary.py`: normative and conclusive framing coverage.
- Commit `docs/superpowers/plans/2026-07-27-study1-chinese-readme.md`: implementation record.

### Task 1: Validate and commit the upgraded neutral Proxy safeguards

**Files:**
- Modify: `media_service/app/prompts/proxy-v1.txt`
- Modify: `media_service/app/prompts/neutral-summary-v1.txt`
- Modify: `media_service/app/pipeline.py`
- Modify: `media_service/app/summary.py`
- Test: `media_service/tests/test_proxy_pipeline.py`
- Test: `media_service/tests/test_transcript_summary.py`

- [x] **Step 1: Review the six-file diff as one behavior boundary**

Run:

```powershell
git diff -- media_service/app/pipeline.py media_service/app/summary.py media_service/app/prompts/proxy-v1.txt media_service/app/prompts/neutral-summary-v1.txt media_service/tests/test_proxy_pipeline.py media_service/tests/test_transcript_summary.py
```

Confirm that the diff contains all and only these behaviors:

- Proxy is instructed to relay P-authorized claims with attribution;
- Proxy must not recommend, rank, persuade, pressure, vote, or decide;
- non-neutral live output is blocked before TTS and audio publication;
- a `MEDIA_PROXY_NEUTRALITY_BLOCKED` outbox event records a hash and provider/runtime context;
- summaries reject normative or conclusive framing in English and Chinese;
- tests cover both prompt wording and fail-closed runtime behavior.

- [x] **Step 2: Run focused media tests**

Run:

```powershell
python -m pytest -p no:cacheprovider media_service\tests\test_proxy_pipeline.py media_service\tests\test_transcript_summary.py -q
```

Expected: both test modules pass with zero failures.

- [x] **Step 3: Check formatting and commit only the six files**

Run:

```powershell
git diff --check -- media_service/app/pipeline.py media_service/app/summary.py media_service/app/prompts/proxy-v1.txt media_service/app/prompts/neutral-summary-v1.txt media_service/tests/test_proxy_pipeline.py media_service/tests/test_transcript_summary.py
git add -- media_service/app/pipeline.py media_service/app/summary.py media_service/app/prompts/proxy-v1.txt media_service/app/prompts/neutral-summary-v1.txt media_service/tests/test_proxy_pipeline.py media_service/tests/test_transcript_summary.py
git commit -m "feat: strengthen neutral Proxy safeguards"
```

Expected: one commit containing exactly six files.

### Task 2: Replace the root README with the Chinese Study 1 guide

**Files:**
- Modify: `README.md`

- [x] **Step 1: Write the operations-first README**

Replace the obsolete English README with Chinese content in this exact section order:

```markdown
# Study 1 人类与代理协作实验平台

## 项目简介
## 当前实现范围
## 实验流程
## 系统架构与职责边界
## 快速开始
### 环境要求
### 配置 `.env`
### 启动与检查
### 页面入口
## 完整使用教程
### Researcher
### P
### T1/T2
### Mock 模式
## 阶段状态机
## 配置说明
### 安全和数据库
### LiveKit
### Media Provider
## 接口总览
### 页面路由
### Study 1 REST API
### A 到 B 内部接口
### B 到 A 回调接口
### Socket.IO
## 数据与导出
## 测试与开发
## 常见问题
## 旧平台兼容性
## 详细文档
## 引用
```

The architecture section must state these invariants explicitly:

- A is the sole owner of Session, roles, permissions, phases, Hidden Profile, submissions, Review, researcher controls, the primary database, and the final export;
- B owns LiveKit audio, microphone handling, recording, ASR, LLM, TTS, the single X runtime, transcripts, and neutral summaries;
- browsers call A only; A calls B using `A_TO_B_SERVICE_TOKEN`; B calls A using `X-Study1-Internal-Key`;
- B never changes A's phase and never reads unshared T1/T2 materials;
- P never receives Proxy-room media access and remains isolated until handoff.

- [x] **Step 2: Add exact local setup commands**

Document these PowerShell commands and expected addresses:

```powershell
Copy-Item .env.example .env
notepad .env
docker compose config --quiet
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 postgres livekit media-service backend frontend
```

```text
Researcher:  http://localhost:8080/researcher/study1
Invitation:  http://localhost:8080/study1/join/{token}
Participant: http://localhost:8080/study1/participant
Backend:     http://localhost:5000
LiveKit:     ws://localhost:7880
```

The `.env` table must mark these local-stack variables as required: `FLASK_SECRET_KEY`, `STUDY1_RESEARCHER_KEY`, `STUDY1_INTERNAL_API_KEY`, `A_TO_B_SERVICE_TOKEN`, `MEDIA_DATABASE_PASSWORD`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET`. It must state that the last four service/media secrets have startup validation, that real secrets must not be committed, and that port conflicts can be solved with `POSTGRES_PORT`, `BACKEND_PORT`, and `FRONTEND_PORT`.

- [x] **Step 3: Document provider truthfully**

The README must list the B provider matrix exactly as implemented:

| `MEDIA_PROVIDER` | ASR/LLM/TTS | Required configuration | Use |
| --- | --- | --- | --- |
| `mock` | deterministic mock providers | no external model key | local workflow and integration testing |
| `openai` | OpenAI-compatible implementation currently targeting OpenAI endpoints | `OPENAI_API_KEY` | real media pipeline |
| `azure` | Azure OpenAI deployments | Azure endpoint, key, and deployment variables from `.env.example` | real media pipeline |

State explicitly that DeepSeek and Qwen are not selectable B providers in the current implementation; OpenAI-compatible claims must not be made until endpoint/base URL configuration exists in code.

- [x] **Step 4: Add the authoritative phase table**

List these phases in order with their unlock condition:

```text
SETUP
MATERIAL_READING
PRE_VOTE
PROXY_CONFIGURATION
PROXY_MEETING
TENTATIVE_DECISION
DELEGATION_EXPECTATION
REVIEW
COMPREHENSION_MEASUREMENT
HANDOFF
SYNC_MEETING
FINAL_DECISION
FOLLOWUP_TASK
POST_SURVEY
COMPLETED
```

Explain that only the Researcher advances phases, normal transitions require server-calculated prerequisites, and overrides require a non-empty audited reason.

### Task 3: Build and verify the interface tables against executable sources

**Files:**
- Modify: `README.md`

- [x] **Step 1: Add the complete browser-facing A REST inventory**

The table must include the following method/path pairs and identify `public`, `Researcher bearer`, `Participant bearer`, or `P bearer` authentication:

```text
POST /api/study1/auth/researcher
POST /api/study1/sessions
GET  /api/study1/sessions
POST /api/study1/invites/{token}/exchange
GET  /api/study1/sessions/{session_id}/me
GET  /api/study1/sessions/{session_id}/me/materials
POST /api/study1/sessions/{session_id}/materials/{role}
POST /api/study1/sessions/{session_id}/submissions/{submission_type}
POST /api/study1/sessions/{session_id}/submissions/{submission_id}/revisions
POST /api/study1/sessions/{session_id}/transition
GET  /api/study1/sessions/{session_id}/review
POST /api/study1/sessions/{session_id}/ui-events
GET  /api/study1/sessions/{session_id}/researcher
POST /api/study1/sessions/{session_id}/control/{action}
POST /api/study1/sessions/{session_id}/incidents
POST /api/study1/sessions/{session_id}/media-commands
POST /api/study1/sessions/{session_id}/media-access
POST /api/study1/sessions/{session_id}/media-device
GET  /api/study1/sessions/{session_id}/media-status
GET  /api/study1/sessions/{session_id}/recordings/{recording_id}
POST /api/study1/sessions/{session_id}/mock-media/complete
GET  /api/study1/sessions/{session_id}/export
```

Document valid submission types:

```text
material_ack, pre_vote, proxy_config, proxy_ready, tentative_decision,
delegation_expectation, comprehension_measurement, final_decision,
followup_task, post_survey
```

- [x] **Step 2: Add the internal A/B interface inventory**

Document these B endpoints as internal-only and authenticated with `Authorization: Bearer {A_TO_B_SERVICE_TOKEN}` except `/healthz`:

```text
GET  /healthz
POST /internal/commands
POST /internal/media-access
POST /internal/device-status
GET  /internal/sessions/{session_id}/status
GET  /internal/sessions/{session_id}/export
GET  /internal/sessions/{session_id}/recordings/{recording_id}
```

Document A callback endpoints authenticated with `X-Study1-Internal-Key`:

```text
POST /api/internal/study1/media-events
POST /api/internal/study1/sessions/{session_id}/artifacts
```

List the exact command values:

```text
START_PROXY_MEETING, END_CURRENT_MEETING, BEGIN_HANDOFF,
START_SYNC_MEETING, REGENERATE_SUMMARY, STOP_SESSION
```

List event values and artifact values from `contracts/study1-media-contract.md`:

```text
MEDIA_READY, PARTICIPANT_JOINED, PARTICIPANT_LEFT,
HANDOFF_COMPLETE, MEDIA_ERROR, MEETING_ENDED

transcript, summary, recording_manifest, agent_log_manifest
```

- [x] **Step 3: Add Socket.IO and data export tables**

Document `study1_join_session` and `study1_leave_session`, each carrying server-signed bearer identity, plus these pushed events:

```text
study1_phase_updated
study1_readiness_updated
study1_participant_status_updated
study1_artifact_ready
study1_incident_created
study1_session_terminated
```

Document the final ZIP contents:

```text
session.json
participants.csv
phase_events.csv
submissions.jsonl
ui_events.jsonl
incidents.csv
artifacts_manifest.json
materials_assignment.json
schema_version.json
media/
```

- [x] **Step 4: Cross-check README routes and links**

Run:

```powershell
Select-String -LiteralPath backend\study1\routes.py -Pattern '@study1_bp'
Select-String -LiteralPath media_service\app\main.py -Pattern '@app.get','@app.post'
Select-String -LiteralPath frontend\src\study1\services\study1Socket.js -Pattern "'study1_"
$links = @('docs\study1-integration-guide.md','contracts\study1-media-contract.md','backend\study1\README.md','media_service\README.md','.env.example','docker-compose.yml'); $links | ForEach-Object { if (-not (Test-Path -LiteralPath $_)) { throw "Missing README link target: $_" } }
```

Expected: every README endpoint appears in an executable source or the A/B contract, and all local links exist.

- [ ] **Step 5: Commit README and plan**

Run:

```powershell
git diff --check -- README.md docs/superpowers/plans/2026-07-27-study1-chinese-readme.md
git add -- README.md docs/superpowers/plans/2026-07-27-study1-chinese-readme.md
git commit -m "docs: add Chinese Study 1 guide"
```

Expected: documentation-only commit.

### Task 4: Run full verification and update the existing PR

**Files:**
- Verify all committed files; do not modify `.env`, `Agent Simulation/`, or `output/`.

- [ ] **Step 1: Run the complete media suite**

```powershell
python -m pytest -p no:cacheprovider media_service\tests -q
```

Expected: zero failures.

- [ ] **Step 2: Run the complete Study 1 backend suite**

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest -p no:cacheprovider backend\tests\study1 -q
```

Expected: zero failures.

- [ ] **Step 3: Run frontend tests and production build**

```powershell
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

Expected: all Vitest tests pass and Vite exits 0; the existing large-chunk warning is non-blocking.

- [ ] **Step 4: Validate Compose and repository state**

```powershell
docker compose config --quiet
git diff --check
git status --short --branch
```

Expected: Compose configuration and diff check exit 0. Only `.env`, `Agent Simulation/`, and `output/` may remain untracked; tracked implementation changes must be committed.

- [ ] **Step 5: Push without merging main**

```powershell
git push origin codex/study1-media-service
```

Expected: existing PR `https://github.com/cyt2023/agent-simulation/pull/1` updates with the new commits and remains based on `main`.
