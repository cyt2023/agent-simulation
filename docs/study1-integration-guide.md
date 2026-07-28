# Study 1 集成与数据交换说明

本文档描述 Study 1 “A：实验流程、权限与数据”服务的端口、环境变量、鉴权方式、API、Socket.IO 事件以及 A/B 数据交换格式。

> `MockMediaGateway` 仍用于测试和显式 Mock 模式。Docker Compose 默认接入独立 B 服务、LiveKit OSS、服务端 ASR/LLM/TTS、单一 X、录音、逐字稿、摘要和持久 outbox。

## 1. 服务与端口

| 服务 | 本机默认地址 | Docker 内部地址 | 配置项 |
| --- | --- | --- | --- |
| 前端 | `http://localhost:8080` | `http://frontend:80` | `FRONTEND_PORT` |
| Flask REST API | `http://localhost:5000` | `http://backend:5000` | `BACKEND_PORT` |
| Socket.IO | `http://localhost:5000/socket.io` | `http://backend:5000/socket.io` | 与后端共用端口 |
| PostgreSQL | `127.0.0.1:5432` | `postgres:5432` | `POSTGRES_PORT` / `PGPORT` |
| Media Service B | 不暴露 | `http://media-service:8000` | `MEDIA_SERVICE_URL` |
| LiveKit OSS | `ws://localhost:7880` | `ws://livekit:7880` | `LIVEKIT_PUBLIC_URL` |

Docker Compose 中：

- `BACKEND_PORT` 和 `FRONTEND_PORT` 是宿主机暴露端口。
- PostgreSQL 仅绑定宿主机回环地址 `127.0.0.1`。
- 前端生产容器通过 nginx 将 `/api` 和 `/socket.io` 转发给后端。

Study 1 页面：

| 页面 | 地址 |
| --- | --- |
| Researcher 控制台 | `http://localhost:8080/researcher/study1` |
| 一次性邀请 | `http://localhost:8080/study1/join/{token}` |
| Participant 页面 | `http://localhost:8080/study1/participant` |

## 2. 必要环境变量

```dotenv
# PostgreSQL
DATABASE_URL=postgresql://postgres:changeme@postgres:5432/humanagent
PGSCHEMA=humanagent_collab

# Flask 和 Study 1 token 签名
FLASK_SECRET_KEY=replace-with-a-long-random-secret
# 可选；未设置时使用 FLASK_SECRET_KEY
STUDY1_TOKEN_SECRET=replace-with-an-independent-random-secret
STUDY1_AUTH_TOKEN_TTL_SECONDS=43200

# Researcher 登录密钥
STUDY1_RESEARCHER_KEY=replace-with-researcher-key

# B -> A 内部接口共享密钥
STUDY1_INTERNAL_API_KEY=replace-with-internal-service-key
A_TO_B_SERVICE_TOKEN=replace-with-a-different-service-key
MEDIA_GATEWAY_MODE=http
MEDIA_SERVICE_URL=http://media-service:8000

# B 独立 PostgreSQL schema/user
MEDIA_DATABASE_PASSWORD=replace-with-media-database-password
MEDIA_DATABASE_SCHEMA=study1_media

# LiveKit
LIVEKIT_API_KEY=replace-with-livekit-key
LIVEKIT_API_SECRET=replace-with-livekit-secret
LIVEKIT_PUBLIC_URL=ws://localhost:7880

# 写入 ZIP 导出的版本信息
STUDY1_FRONTEND_BUILD_VERSION=git-sha-or-release
STUDY1_BACKEND_BUILD_VERSION=git-sha-or-release

# 宿主机端口
BACKEND_PORT=5000
FRONTEND_PORT=8080
POSTGRES_PORT=5432
```

不要将实际密钥提交进 Git。

## 3. 启动

```bash
cp .env.example .env
# 编辑 .env 并设置密码和密钥
docker compose up --build
```

后端容器启动时会运行：

```bash
python -m scripts.init_db
python app.py
```

Study 1 使用以下数据表：

```text
study1_invites
study1_events
study1_submissions
study1_artifacts
study1_incidents
study1_materials
```

## 4. 鉴权

### 4.1 Researcher 登录

```http
POST /api/study1/auth/researcher
Content-Type: application/json
```

```json
{
  "key": "STUDY1_RESEARCHER_KEY 的值"
}
```

响应：

```json
{
  "token": "server-signed-bearer-token"
}
```

后续 Researcher 请求：

```http
Authorization: Bearer server-signed-bearer-token
```

### 4.2 Participant 一次性邀请

Researcher 创建 session 后，A 返回 P、T1、T2 三条独立邀请。原始 invite token 只返回一次，数据库只保存 SHA-256 hash。

兑换：

```http
POST /api/study1/invites/{raw_token}/exchange
```

响应示例：

```json
{
  "token": "server-signed-participant-token",
  "identity": {
    "session_id": "uuid",
    "participant_id": "uuid",
    "role": "principal"
  },
  "session": {
    "session_id": "uuid",
    "status": "waiting",
    "phase": "SETUP",
    "phase_version": 1,
    "ready_to_advance": true,
    "next_phase": "MATERIAL_READING",
    "missing_prerequisites": []
  }
}
```

同一条一次性邀请不能在第二台设备上再次兑换。Participant 的角色来自服务器签名 token，不读取请求 body 或 query 中的 `role`。

### 4.3 B -> A 内部鉴权

B 调用 A 时必须发送：

```http
X-Study1-Internal-Key: STUDY1_INTERNAL_API_KEY 的值
```

前端永远不能持有或发送该密钥，也不能直接调用 B。

## 5. Session 创建

```http
POST /api/study1/sessions
Authorization: Bearer {researcher_token}
Content-Type: application/json
```

```json
{
  "session_name": "study1-run-001",
  "invite_ttl_seconds": 86400,
  "minimum_review_seconds": 30,
  "materials_by_role": {
    "principal": [
      {
        "title": "Principal material",
        "content": "Private material for P"
      }
    ],
    "teammate_1": [
      {
        "title": "T1 material",
        "content": "Private material for T1"
      }
    ],
    "teammate_2": [
      {
        "title": "T2 material",
        "content": "Private material for T2"
      }
    ]
  }
}
```

创建后 session 保持：

```json
{
  "status": "waiting",
  "phase": "SETUP"
}
```

系统不会自动开始。Researcher 必须调用 Start Session。

## 6. 材料上传与隔离

Researcher 可上传 PDF、UTF-8 TXT 或 Markdown：

```http
POST /api/study1/sessions/{session_id}/materials/{role}
Authorization: Bearer {researcher_token}
Content-Type: multipart/form-data
```

表单字段：

```text
files=<one or more files>
```

允许的 `{role}`：

```text
principal
teammate_1
teammate_2
```

Participant 只能调用：

```http
GET /api/study1/sessions/{session_id}/me/materials
Authorization: Bearer {participant_token}
```

该接口没有可用的角色参数。即使修改 URL/query，服务端仍按 token 中的角色过滤。

## 7. Participant 提交

```http
POST /api/study1/sessions/{session_id}/submissions/{submission_type}
Authorization: Bearer {participant_token}
Content-Type: application/json
```

```json
{
  "instrument_version": "vote-v1",
  "payload": {
    "decision": "candidate-a",
    "rationale": "Evidence-based explanation"
  },
  "client_timestamp": "2026-07-26T10:00:00Z"
}
```

支持的 `submission_type`：

```text
material_ack
pre_vote
proxy_config
proxy_ready
tentative_decision
delegation_expectation
comprehension_measurement
final_decision
followup_task
post_survey
```

成功提交后原记录锁定。Researcher 修正会创建 revision，不覆盖原记录。

错误阶段响应：

```http
HTTP/1.1 409 Conflict
```

```json
{
  "error": "ACTION_NOT_ALLOWED_IN_PHASE",
  "message": "Action requires PRE_VOTE, current phase is MATERIAL_READING",
  "current_phase": "MATERIAL_READING",
  "required_phase": "PRE_VOTE"
}
```

## 8. Phase 控制

普通推进：

```http
POST /api/study1/sessions/{session_id}/transition
Authorization: Bearer {researcher_token}
Content-Type: application/json
```

```json
{
  "target_phase": "PRE_VOTE",
  "override": false,
  "reason": null
}
```

强制推进：

```json
{
  "target_phase": "PRE_VOTE",
  "override": true,
  "reason": "Participant withdrew; protocol exception approved"
}
```

Force Advance 的 `reason` 必填，并追加 `override` 与 `phase_transition` 两条审计事件。

其他固定控制入口：

```text
POST /api/study1/sessions/{session_id}/control/start
POST /api/study1/sessions/{session_id}/control/pause
POST /api/study1/sessions/{session_id}/control/resume
POST /api/study1/sessions/{session_id}/control/extend
POST /api/study1/sessions/{session_id}/control/terminate
```

Extend body：

```json
{
  "seconds": 300
}
```

不存在允许任意 PUT phase 的接口。

## 9. A -> B Command

未来 B 服务只暴露一个 command 入口：

```http
POST {B_SERVICE}/internal/commands
Content-Type: application/json
```

```json
{
  "command_id": "42edc424-4394-43a3-9bb6-313269545905",
  "session_id": "87c52b1d-81b6-4f52-b84f-da8e2c297775",
  "phase_version": 3,
  "command": "START_PROXY_MEETING",
  "issued_at": "2026-07-26T10:00:00Z",
  "payload": {}
}
```

允许的 command：

```text
START_PROXY_MEETING
END_CURRENT_MEETING
BEGIN_HANDOFF
START_SYNC_MEETING
REGENERATE_SUMMARY
STOP_SESSION
```

`END_CURRENT_MEETING` 由研究者显式结束当前 Proxy/同步会议。
`REGENERATE_SUMMARY` 必须携带原因、源 transcript checksum 和源 summary
version。两条命令都不会推进 A 的 phase。

### Media access 与研究者代理接口

```text
POST /api/study1/sessions/{session_id}/media-access
GET  /api/study1/sessions/{session_id}/media-status
GET  /api/study1/sessions/{session_id}/recordings/{recording_id}
GET  /api/study1/sessions/{session_id}/export
```

Participant media-access 忽略浏览器提交的角色，只使用 A 签名 token 中的身份。
P 不会获得 Proxy room token。录音回放只允许已提交委托预期的 P 在
Review/Comprehension 阶段使用，且每次必须请求不超过 1 MiB 的 Range。

`command_id` 是幂等键。相同 command 不得执行两次。

当前 A 中的 Researcher command API：

```http
POST /api/study1/sessions/{session_id}/media-commands
Authorization: Bearer {researcher_token}
Content-Type: application/json
```

```json
{
  "command_id": "optional-client-generated-uuid",
  "command": "START_PROXY_MEETING",
  "payload": {}
}
```

For `START_PROXY_MEETING`, A ignores this browser payload and constructs the
context from P's locked `proxy_config`. That submission must contain:

```json
{
  "priorities": "P-authored priorities",
  "boundaries": "P-authored boundaries",
  "authorization_confirmed": true,
  "authorized_material_ids": ["p-material-uuid"]
}
```

A validates that every ID belongs to P and sends only those selected materials
to B. Sync uses a hidden subscribe-only B recorder; X is never present in the
Sync room. `HANDOFF_COMPLETE` requires X to be stopped plus successful device
preflight records for P, T1, and T2.

## 10. B -> A Event

```http
POST /api/internal/study1/media-events
X-Study1-Internal-Key: {internal_key}
Content-Type: application/json
```

```json
{
  "event_id": "4dd7dc48-54dd-49f0-8dd7-e42c7620b808",
  "session_id": "87c52b1d-81b6-4f52-b84f-da8e2c297775",
  "phase_version": 3,
  "event_type": "MEETING_ENDED",
  "occurred_at": "2026-07-26T10:10:00Z",
  "payload": {}
}
```

允许的 event：

```text
MEDIA_READY
PARTICIPANT_JOINED
PARTICIPANT_LEFT
HANDOFF_COMPLETE
MEDIA_ERROR
MEETING_ENDED
```

`event_id` 是幂等键。重复 event 返回成功及 `"duplicate": true`，但不再次处理或写入。

Event 只更新状态或前置条件，不自动推进 phase：

| Event | 效果 |
| --- | --- |
| `MEDIA_READY` | media 状态变为 ready |
| `MEDIA_ERROR` | media 状态变为 error |
| `HANDOFF_COMPLETE` | 满足 HANDOFF 前置条件 |
| `MEETING_ENDED` | 满足当前 Proxy/Sync meeting 的结束条件 |

## 11. B -> A Artifact

```http
POST /api/internal/study1/sessions/{session_id}/artifacts
X-Study1-Internal-Key: {internal_key}
Content-Type: application/json
```

Inline 内容：

```json
{
  "artifact_id": "bb3da71e-92f7-4487-af67-74c0363934eb",
  "type": "summary",
  "version": "1",
  "content": "Neutral summary text",
  "storage_uri": null,
  "checksum": "SHA-256 hex digest of content",
  "created_at": "2026-07-26T10:11:00Z",
  "generator_version": "mock-b-1",
  "metadata": {}
}
```

外部存储：

```json
{
  "artifact_id": "7bb4c2be-ecce-4b79-a4ab-dae4ade5d610",
  "type": "recording_manifest",
  "version": "1",
  "content": null,
  "storage_uri": "s3://bucket/path/manifest.json",
  "checksum": "manifest checksum",
  "created_at": "2026-07-26T10:11:00Z",
  "generator_version": "future-b-1",
  "metadata": {}
}
```

允许的 artifact type：

```text
transcript
summary
recording_manifest
agent_log_manifest
```

Summary ready 只满足进入 Review 的一个前置条件，不会自动推进实验。

## 12. Review 与 UI Event

只有 principal 且已提交 delegation expectation 后，才能在 REVIEW 或 COMPREHENSION_MEASUREMENT 阶段调用：

```http
GET /api/study1/sessions/{session_id}/review
Authorization: Bearer {principal_token}
```

UI 日志：

```http
POST /api/study1/sessions/{session_id}/ui-events
Authorization: Bearer {principal_token}
Content-Type: application/json
```

```json
{
  "event_type": "scroll_depth",
  "payload": {
    "max_depth": 0.75,
    "visible_segments": ["segment-2", "segment-3"]
  }
}
```

支持：

```text
review_page_enter
review_page_leave
summary_visible
transcript_expand
transcript_collapse
transcript_segment_view
scroll_depth
active_reading_time
```

前端对滚动事件采用 750ms 节流。最短阅读时间根据服务器首次打开 Review 的时间计算，不信任客户端自行声明的时长。

## 13. Socket.IO

连接地址：

```text
http://localhost:5000/socket.io
```

当前客户端使用 Socket.IO polling transport。

加入房间：

```javascript
socket.emit('study1_join_session', {
  session_id: 'uuid',
  token: 'server-signed-bearer-token'
})
```

Study 1 独立事件：

```text
study1_phase_updated
study1_readiness_updated
study1_participant_status_updated
study1_artifact_ready
study1_incident_created
study1_session_terminated
```

Socket 事件只作为更新通知。断线重连后，前端必须重新加入 room，并通过 REST `/me` 获取权威 phase，不依赖断线前的本地状态。

## 14. ZIP 导出

```http
GET /api/study1/sessions/{session_id}/export
Authorization: Bearer {researcher_token}
```

响应类型：

```text
application/zip
```

ZIP 包含：

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
```

`schema_version.json` 包含：

- protocol/task/build 版本；
- phase schema version；
- instrument 和 artifact 版本；
- override 记录；
- 缺失 submission、artifact 和当前前置条件清单。

## 15. 测试

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest -p no:cacheprovider backend\tests\study1 -q
```

当前测试覆盖完整 Mock 流程：

```text
创建 Session
→ 三条角色邀请
→ 三人登录
→ 私有材料
→ 初始判断
→ Proxy 配置
→ Mock Proxy meeting
→ 暂定决定
→ 委托预期
→ Mock summary/transcript
→ Review
→ 理解测量
→ Mock handoff
→ Mock Sync meeting
→ 最终决定
→ 后续任务
→ 最终问卷
→ COMPLETED
→ ZIP 导出
```

更严格的 A/B 字段约束见 [`../contracts/study1-media-contract.md`](../contracts/study1-media-contract.md)。
