# Study 1 中文 README 设计

## 目标

用中文重写仓库根目录 `README.md`，使第一次接触项目的研究者或开发者能够完成本地启动、配置、实验操作、接口定位、测试和故障排查。README 以当前 Study 1 实现为主，删除现有文档中“尚未实现 LiveKit、RTC、ASR、TTS 和 Proxy Runtime”等过时描述。

同时提交用户已经升级的 Proxy/摘要中性约束改动。该改动包括 prompt、运行时输出拦截逻辑和对应测试，作为一组完整变更处理。

## 受众与边界

主要受众：

- 负责部署和操作实验的研究者；
- 负责联调 A/B 服务的开发者；
- 需要复现实验、测试流程或导出数据的维护者。

README 不重复完整协议字段定义。根文档负责“如何使用”和“到哪里查”，字段级约束继续以 `contracts/study1-media-contract.md`、`docs/study1-integration-guide.md` 及实际路由实现为准。

旧平台保留兼容性说明和入口链接，但不再作为 README 的主叙事，也不修改旧页面或旧实验逻辑。

## 文档结构

README 采用“操作优先、契约可查”的顺序：

1. 项目定位和当前实现范围；
2. Study 1 实验流程；
3. A/B 架构及安全边界；
4. 环境要求和 Docker 快速启动；
5. 必填环境变量及媒体 Provider 配置；
6. Researcher、P、T1、T2 分角色使用教程；
7. 阶段状态机、Proxy Meeting、Review 和 Handoff 操作；
8. 页面、REST API、A 到 B Command、B 到 A Event/Artifact、Socket.IO 接口表；
9. 数据库、媒体文件和 ZIP 导出内容；
10. 自动化测试、日志查看和常见故障排查；
11. 旧平台兼容说明和详细文档索引。

PowerShell 作为 Windows 本地操作的首要示例，同时提供必要的跨平台命令。所有示例使用占位密钥，不写入任何本地 `.env` 内容。

## 接口表设计

每条 REST 接口至少列出：

- HTTP 方法；
- 路径；
- 调用方；
- 鉴权方式；
- 用途或阶段限制。

A/B 接口分别列出固定 Command、Event 和 Artifact 枚举。Socket.IO 表列出加入房间方式及 Study 1 推送事件。README 给出关键请求示例，但不会复制整份契约中的所有 JSON schema。

接口内容必须与实际代码交叉核对，不能只照抄可能过时的说明文档。

## Proxy 中性约束提交边界

将以下六个现有工作区修改作为一个独立提交：

- `media_service/app/prompts/proxy-v1.txt`；
- `media_service/app/prompts/neutral-summary-v1.txt`；
- `media_service/app/pipeline.py`；
- `media_service/app/summary.py`；
- `media_service/tests/test_proxy_pipeline.py`；
- `media_service/tests/test_transcript_summary.py`。

该提交的行为是：增强 Proxy 和摘要 prompt 的非建议、非排序、非劝服约束；在 TTS 发布前拦截非中性的 Proxy 输出；记录可审计的阻断事件；扩展英文和中文规范性/结论性表述测试。

## 验证标准

- README 中不存在已知过时的 Study 1 功能描述；
- Docker 命令、端口、页面地址和环境变量与 Compose 配置一致；
- 接口表与后端、媒体服务的实际路由一致；
- Proxy/摘要相关测试全部通过；
- 后端 Study 1 测试、前端测试和构建保持通过；
- `docker compose config --quiet` 通过；
- Git 只暂存 README、设计/计划文档及已确认的六个中性约束文件；
- `.env`、`Agent Simulation/` 和 `output/` 不提交；
- 提交推送到 `codex/study1-media-service` 并更新现有 PR，不合并 `main`。

## 非目标

- 不增加新的 API 或实验阶段；
- 不修改旧平台界面；
- 不在 README 中承诺 DeepSeek、通义千问等当前 B Provider 尚未实现的能力；
- 不修改用户本地密钥、数据库卷或媒体数据。
