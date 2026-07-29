# Study 1 正式验收与数据交换说明

本文档对应 `Study1_系统开发任务书_v1.1` 中的正式实验流程、权限、媒体交接、测量和数据导出要求。系统默认以 Mock 模式供流程验收；切换真实模型和真实语音服务后，必须再执行本文末尾的人工 Pilot。

## 1. 服务入口与端口

| 服务 | 本机入口 | 容器内入口 | 说明 |
|---|---|---|---|
| 参与者/研究者前端 | `http://localhost:8080` | `http://frontend:80` | 浏览器唯一业务入口 |
| Flask A 服务 | `http://localhost:5000` | `http://backend:5000` | REST、Socket.IO、权限和状态机 |
| Socket.IO | `http://localhost:5000/socket.io` | 同 A 服务 | 阶段、在线状态和事故推送 |
| Media Service B | 不应暴露公网 | `http://media-service:8000` | ASR、X、TTS、录音、纪要 |
| LiveKit 信令 | `ws://localhost:7880` | `ws://livekit:7880` | 本地语音房间 |
| LiveKit RTC | `7881/TCP`、`50000-50100/UDP` | 同端口 | WebRTC 媒体 |
| PostgreSQL | 默认不暴露公网 | `postgres:5432` | A/B 分离 schema 和账号 |

研究者入口：`http://localhost:8080/researcher/study1`。

## 2. 已实现的正式协议约束

- P、T1、T2 和 Researcher 使用服务器签发身份；邀请链接一次兑换，所有权限由令牌角色决定。
- 会话创建时锁定任务实例、阶段时长、最低阅读时间、同意书、量表、纪要、转录策略和 Proxy 模型版本，并记录配置 SHA-256。
- 角色顺序按保存的随机种子随机化；克隆配置时保留协议配置和材料，但生成新的随机种子、参与者和一次性邀请。
- Hidden Profile 文本自动拆为原子事实，保存 `fact_id`、候选项、效价、共享/独有属性和可见角色；显式提供 facts 时执行服务端字段与可见性校验。
- 正式会话必须由三名参与者分别确认身份、角色、录音/转录和自愿参与，研究者才能开始。
- 所有阶段由单一服务端状态机推进；提交一次即锁定，研究者修订和强制推进必须记录原因。
- P 配置 X 时明确选择 `share_only`、`suggest` 或 `agree_tentative`，并逐项授权自己的材料；X 永远不能读取 T1/T2 私有材料。
- 前测、暂定决策、委托预期、理解测量、最终决策、协作任务和问卷均为结构化量表，不再使用一个通用文本框代替。
- Proxy 会议中 P 处于隔离等待室；handoff 使用稳定同步房间，P 加入、X 退出，T1/T2 从 HANDOFF 到 SYNC_MEETING 不主动断线重连。
- 真人开始说话时取消正在播放的 X 语音，并写入 `MEDIA_BARGE_IN`。
- 纪要固定为五部分，每条内容必须引用原始转录 `segment_id`；P 可展开转录、回放授权录音并标记关键片段。
- ASR 人工修订以 `transcript_correction` 追加制品保存，包含原文、修订文、原因、操作者、时间和来源校验和，不覆盖原始转录。
- Pause、Resume、Extend、Terminate 在正式会话中均要求研究者填写原因。

## 3. 主要数据交换格式

### 3.1 创建正式会话

`POST /api/study1/sessions`

```json
{
  "session_name": "pilot-001",
  "minimum_review_seconds": 300,
  "materials_by_role": {
    "principal": [{"title": "P material", "content": "fact one\nfact two"}],
    "teammate_1": [{"title": "T1 material", "content": "fact three"}],
    "teammate_2": [{"title": "T2 material", "content": "fact four"}]
  },
  "experiment_config": {
    "task_version": "2.0",
    "task_instance_id": "hidden-profile-01",
    "summary_template_version": "study1-five-section-v1",
    "transcript_access_policy": "principal_after_delegation",
    "proxy_model_version": "configured-at-runtime",
    "consent_version": "study1-consent-v1",
    "role_assignment_mode": "randomized",
    "require_consent": true,
    "structured_instruments": true,
    "phase_durations_seconds": {
      "MATERIAL_READING": 600,
      "PRE_VOTE": 300,
      "PROXY_MEETING": 900,
      "REVIEW": 600,
      "SYNC_MEETING": 900
    }
  }
}
```

响应只在本次创建请求中返回三个原始邀请令牌。数据库只保存令牌哈希。

### 3.2 参与者提交信封

`POST /api/study1/sessions/{session_id}/submissions/{submission_type}`

```json
{
  "instrument_version": "2.0",
  "client_timestamp": "2026-07-29T08:00:00.000Z",
  "payload": {}
}
```

常用 `payload`：

```json
{
  "consent_version": "study1-consent-v1",
  "identity_confirmed": true,
  "role_confirmed": true,
  "audio_recording_confirmed": true,
  "voluntary_participation_confirmed": true
}
```

```json
{
  "priorities": "Preserve factual accuracy",
  "boundaries": "Do not make a final commitment",
  "authority_level": "suggest",
  "authorization_confirmed": true,
  "authorized_material_ids": ["material-uuid"]
}
```

```json
{
  "decision": "Option A",
  "rationale": "Reason grounded in assigned facts",
  "confidence": 5,
  "decision_status": "tentative_consensus",
  "proxy_authority_belief": "yes",
  "expected_principal_acceptance": 4
}
```

所有正式量表必须为 `2.x` 版本；比例题取值为 1 至 7。原始提交不可覆盖。

### 3.3 A 到 B 的媒体命令

```json
{
  "command_id": "uuid",
  "session_id": "uuid",
  "phase_version": 5,
  "command": "START_PROXY_MEETING",
  "issued_at": "2026-07-29T08:00:00Z",
  "payload": {
    "authorized_context": {
      "authorization_submission_id": "uuid",
      "proxy_config_submission_id": "uuid",
      "materials": [],
      "proxy_config": {
        "authority_level": "suggest"
      }
    }
  }
}
```

B 只接受 A 内网身份认证的命令。`authorized_context` 由 A 从已锁定的 P 提交构造，浏览器不能自行传入。

### 3.4 B 到 A 的媒体事件

```json
{
  "event_id": "uuid",
  "session_id": "uuid",
  "phase_version": 5,
  "event_type": "MEDIA_BARGE_IN",
  "occurred_at": "2026-07-29T08:01:02Z",
  "payload": {
    "runtime_id": "uuid",
    "speaker": "teammate_1",
    "action": "proxy_tts_cancelled"
  }
}
```

事件以 `event_id` 幂等写入。过期 `phase_version` 不得改变当前阶段。

## 4. 导出包

研究者点击 Export Data 后获得一个 ZIP，至少包含：

- `session.json`
- `participants.csv`
- `phase_events.csv`
- `submissions.jsonl`
- `ui_events.jsonl`
- `incidents.csv`
- `artifacts_manifest.json`
- `materials_assignment.json`
- `schema_version.json`
- `integrity_report.json`
- `media/` 下的转录、五段式纪要、录音清单、Agent 日志和媒体事件

`integrity_report.json` 汇总缺失提交、缺失制品、当前阶段前置条件、事故、断线、强制推进和配置校验和。`agent_log_manifest` 保存模型/提示版本、授权等级、输入和提示哈希、响应、延迟、拦截或打断状态。录音清单保存时长、校验和和 consent scope。

## 5. 自动验收

```powershell
python -m pytest backend/tests/study1 media_service/tests -q
cd frontend
npm.cmd test -- --run
npm.cmd run build
cd ..
docker compose up -d --build
docker compose ps
```

正式回归至少覆盖：权限矩阵、阶段前置条件、同意门禁、提交锁定、原子事实、Proxy 材料隔离、授权等级、barge-in、handoff 房间连续性、五段式纪要引用、ASR 追加修订、录音回放、原因审计和完整导出。

## 6. 正式采集前必须完成的人工事项

以下事项不是代码可以代替的，完成前只能称为“技术验收通过”，不能称为“正式实验已验收”：

1. 将 IRB/伦理审批通过的最终同意书文本和版本号冻结到配置。
2. 配置正式 ASR、LLM、TTS 密钥以及生产 WSS/TURN；确认 `MEDIA_PROVIDER` 不再是 `mock`。
3. 使用三台真实设备和三名真人完成至少 10 次连续全流程 Pilot，覆盖拒绝麦克风、断线重连、X 被打断、handoff、暂停、事故、修订和导出。
4. 人工核对每次 Pilot 的角色隔离、X 授权边界、音频可懂度、ASR 时间戳、五段式纪要忠实度、最终量表和导出完整性。
5. 记录模型、提示、前后端镜像、题本、同意书和量表的最终版本；冻结后再开始正式采集。

完成以上五项并由负责人签字后，系统才达到正式数据采集条件。
