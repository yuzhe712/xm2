# IntelliTicket - AI 增强型内部 IT 服务台

IntelliTicket 是一个面向单公司、单实例部署的内部 IT 工单系统。员工提交工单后，系统先把业务工单和 AI 运行记录持久化，再由 Redis/Celery Worker 异步完成分诊、上下文检索和诊断建议；认领、回复、解决、关闭仍由有权限的人员确认并写入审计时间线。

P0-P5 计划任务已完成，项目按当前证据范围正式收尾。项目所有者决定不再执行文档完成后的最终全量回归；最后一次完整基线和 P5 定向测试均已记录。真实 DeepSeek 冒烟因当前环境没有已轮换密钥而未执行，不能视为通过。当前结果只说明本仓库在已记录环境和负载下的表现，不代表生产容量或团队规模承诺。

## 本地 Docker 压测摘要

测试于 2026-07-28 在本机 Docker Compose 环境执行，不需要远程服务器。测试机为 i7-11800H（8 核/16 线程）、15.8 GiB 主机内存，Docker 分配约 7.7 GiB；运行 Python 3.13.9、Locust 2.46.2。验证库最终包含 436 张工单、436 个 AI run 和 941 个审计事件。

| 场景 | 请求/结果 | 错误率 | P50 | P95 | P99 |
|---|---:|---:|---:|---:|---:|
| 5 用户、30 秒限流内基线 | 382 请求，约 13.11 req/s | 0% | 29 ms | 290 ms | 390 ms |
| 创建工单 | 131 请求 | 0% | 31 ms | 58 ms | 95 ms |
| 队列查询 | 78 请求 | 0% | 230 ms | 390 ms | 590 ms |
| 工单详情 | 95 请求 | 0% | 10 ms | 20 ms | 38 ms |
| 并发认领不变量 | 21 次，均为一个成功、一个 409 | 0% | 27 ms | 49 ms | 51 ms |

压测窗口暂停 Worker 后，每个成功提交分别入队 AI 和通知任务，最终观察到 870 条队列积压；Worker 恢复后队列清零，任务没有因停止而丢失。10 用户超限测试还发现 Nginx 默认把限流返回成 503；配置已修正为 429，随后 200 个并发突发请求得到 42 个 200 和 158 个 429。当前主要性能瓶颈是队列查询，数据增长后 P95 明显高于创建和详情接口。

这些数字是本地受控基线，只用于复现和定位瓶颈，不能外推为生产服务器容量。完整环境、原始 CSV 和限制说明见 [测试报告](docs/test-report.md)。

## 已验证能力

| 能力 | 实现入口 | 验证证据 |
|---|---|---|
| 数据库用户、JWT、三种角色和停用失效 | `POST /api/v1/auth/login`、`/api/v1/users` | `tests/test_auth_security.py` |
| 人工工单闭环和乐观锁 | `/api/v1/tickets/{id}/claim`、评论、解决、确认、重开 | `tests/test_p5_workflow_e2e.py`、`tests/test_ticket_workflow.py` |
| 持久化异步 AI 运行 | `ai_runs`、Redis/Celery、状态查询和陈旧任务恢复 | `tests/test_ai_pipeline.py`、`tests/test_p5_fault_tolerance.py` |
| 证据、置信度、模型和 Prompt 版本 | `GET /api/v1/ai-runs/{run_id}` | `tests/test_ai_pipeline.py`、Agent Schema 测试 |
| 附件权限与内容校验 | `/api/v1/tickets/{id}/attachments` | `tests/test_attachments.py` |
| 钉钉异步通知和有限重试 | `notification_deliveries`、Celery delivery task | `tests/test_notification_delivery.py` |
| 角色化前端工作区 | 员工、运维、管理员路由和操作面板 | `frontend/src/renderer/src/App.test.tsx` |
| 健康、就绪和 Prometheus 指标 | `/health`、`/ready`、`/metrics` | `tests/test_health.py` |
| Compose、限流和备份恢复 | `compose.yaml`、Nginx、maintenance profile | [部署文档](docs/deployment.md)、[测试报告](docs/test-report.md) |
| 创建、队列、详情和并发认领压测 | `loadtests/locustfile.py` | [原始 CSV](reports/loadtest/)、[测试报告](docs/test-report.md) |

## 处理流程

```mermaid
flowchart LR
    employee["员工提交工单"] --> transaction["PostgreSQL: ticket + queued ai_run"]
    transaction --> redis["Redis 队列"]
    redis --> worker["Celery Worker"]
    worker --> triage["Triage"]
    triage --> diagnose["Retrieve + Diagnose"]
    diagnose --> gate["Quality Gate"]
    gate --> review["人工复核、认领与回复"]
    review --> resolve["解决并记录根因/动作/验证"]
    resolve --> close["员工确认关闭或重新打开"]
```

AI 失败不会把业务工单标记为失败。工单保持可人工处理，AI 运行单独记录错误、重试次数和终态。详细设计见 [架构文档](docs/architecture.md)。

## 技术栈

- 后端：FastAPI、Pydantic v2、SQLAlchemy 2、Alembic、PostgreSQL
- 异步任务：Celery、Redis
- 前端：React 18、TypeScript、Vite、Electron；容器部署使用 Nginx
- 外部集成：DeepSeek API、飞书知识目录、钉钉通知，均为可选配置
- 可观测性：Prometheus Python client、结构化健康/就绪检查
- 验证：pytest、Vitest、TypeScript、Ruff、Locust、Docker Compose

## 快速启动

要求：Docker Engine 及 Docker Compose。先在当前终端设置部署密钥，值由部署者生成，不要写入仓库：

```powershell
$env:JWT_SECRET_KEY = "<至少 32 位随机值>"
$env:POSTGRES_PASSWORD = "<数据库密码>"
$env:BOOTSTRAP_ADMIN_PASSWORD = "<首次管理员密码>"
docker compose up -d --build
```

默认入口为 `http://127.0.0.1:8080`。确认服务状态：

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8080/ready
docker compose ps -a
```

首次管理员用户名默认为 `admin`，密码来自 `BOOTSTRAP_ADMIN_PASSWORD`。生产部署创建管理员后，应从长期运行环境移除 bootstrap 密码。完整配置、升级、备份和恢复步骤见 [部署文档](docs/deployment.md)。

## 本地开发

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev,loadtest]"
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m uvicorn intelliticket_backend.main:app --reload
```

另一个终端启动 Worker：

```powershell
.\.venv\Scripts\python -m celery -A intelliticket_backend.worker:celery_app worker --pool=solo --loglevel=INFO
```

前端：

```powershell
cd frontend
npm ci
npm run dev:web
```

## 验证命令

```powershell
python -m pytest -q
python -m ruff check .
cd frontend
npm test
npm run typecheck
npm run build:web
```

真实 LLM 冒烟不会读取源码内密钥，也不会打印模型原始输入或响应：

```powershell
$env:DEEPSEEK_API_KEY = "<运行时密钥>"
python scripts/e2e_llm_test.py
```

压测所需账号和密码通过 `LOADTEST_*` 环境变量提供。复现命令、环境和结果见 [测试报告](docs/test-report.md)。

## API 主线

1. 员工登录并 `POST /api/v1/tickets/submit`。
2. 客户端使用 `ai_run_id` 查询或订阅持久化 AI 状态。
3. 运维从 `/api/v1/tickets/queue` 获取队列，以当前 `version` 原子认领。
4. 运维公开回复或添加内部备注；员工看不到内部内容。
5. 当前处理人提交解决摘要、根因、修复动作和验证结果。
6. 工单提交人确认关闭，或带原因重新打开。

可执行请求见 [API 示例](docs/api-examples.md)。

## 安全与边界

- 角色和数据范围在后端校验，前端隐藏按钮不是授权边界。
- 员工只能访问自己提交的工单；operator/admin 可处理队列；仅 admin 管理配置。
- 所有写操作携带 `version`，数据库条件更新保证并发认领只有一个成功者。
- 附件使用 UUID 存储键、签名/MIME/扩展名校验和 25 MiB 双层限制。
- `/ready` 只在 PostgreSQL 与 Redis 都可用时返回 200；`/health` 不依赖外部服务。
- Nginx API 限流为 20 req/s、burst 40，超限返回 429。
- 本仓库不包含部署密钥、演示密码或真实工单数据。

## 文档

- [部署与运维](docs/deployment.md)
- [架构与关键决策](docs/architecture.md)
- [API 示例](docs/api-examples.md)
- [测试与压测报告](docs/test-report.md)
- [面试问答与可验证项目描述](docs/interview-guide.md)
- [钉钉集成](docs/dingtalk-integration.md)
- [飞书知识集成](docs/feishu-knowledge-integration.md)

## 当前限制

- 仅验证单公司、单实例部署，没有多租户隔离设计。
- 压测结果来自单台开发机和受控数据集，不外推生产容量。
- 队列查询当前会加载并合并 SQL 与兼容存储记录，数据量增长时延迟上升，详见测试报告。
- 外部 LLM、飞书和钉钉的可用性及配额由各自服务决定；核心人工流程不依赖它们完成。

## 许可证

MIT License
