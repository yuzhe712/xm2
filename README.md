# IntelliTicket 企业级智能工单自动化处理平台

IntelliTicket 是面向单一公司内部 IT 运维 / 客服 / 支持场景的智能工单处理系统。当前版本是单公司单实例 MVP：使用 FastAPI、本地 mock 运维数据和 Electron / React 桌面端，完成自然语言运维告警工单的分类、优先级判断、上下文检索、根因候选、处理建议、报告生成和可视化展示。

## 当前实现范围

已实现：

- `GET /api/v1/health` 健康检查；
- `POST /api/v1/tickets/process` 同步工单处理接口；
- 本地 `mock_data/` 运维数据集；
- 确定性 workflow trace：`ticket_intake → context_retrieval → diagnosis → routing → report`；
- 工单证据与溯源字段；
- `data_mode: "mock"` 显式标记；
- pytest 覆盖 health、mock 数据、service 和 API；
- Electron / React / Vite / TypeScript 本地桌面端；
- REST 工单提交、WebSocket Agent 实时进度、取消按钮和 mock 数据标识；
- SQLite completed / failed / cancelled 工单历史持久化；
- `GET /api/v1/tickets` 和 `GET /api/v1/tickets/{ticket_id}` 查询已处理工单。

未实现，仍是后续扩展点：

- 登录、内部操作员权限和审计；当前不做多租户隔离、租户后台或 SaaS 租户模型；
- Redis、Celery、Kubernetes；
- 正式 A2A、LangGraph；
- 真实 Prometheus、Grafana、Jira、飞书工单系统接入。

> 注意：当前所有运维上下文均来自本地 mock 数据，不代表真实生产系统。

## 架构边界：单公司单实例

当前产品选择 **单公司单实例**：一套部署、一套后端配置、一套 SQLite 历史库，服务于一个公司内部工单处理台。不要在当前 MVP 中引入 `tenant_id`、租户后台、跨租户隔离或 SaaS 多租户模型；如果另一家公司也要使用，应部署另一套独立实例。

默认运行在本机 `127.0.0.1:8000` 是为了本地开发和内部演示安全。需要放到内网服务器时，可以配置桌面端后端地址和后端 `FRONTEND_ALLOWED_ORIGINS`，但当前版本没有登录和权限系统，不能直接暴露到不可信网络。

## 环境准备

```powershell
cd "f:\wdxm\2.企业工单系统"
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

## 运行测试

```powershell
cd "f:\wdxm\2.企业工单系统"
.\.venv\Scripts\python -m pytest
```

## 启动后端

```powershell
cd "f:\wdxm\2.企业工单系统"
.\.venv\Scripts\python -m uvicorn intelliticket_backend.main:app --reload --host 127.0.0.1 --port 8000
```

## Eval CLI 报告器

独立 eval 报告器直接调用本地 mock 业务逻辑，不依赖 pytest，也不代表真实 Prometheus、Grafana、Jira 或飞书集成能力。

```powershell
cd "f:\wdxm\2.企业工单系统"
.\.venv\Scripts\python -m intelliticket_backend.eval_reporter --format text
.\.venv\Scripts\python -m intelliticket_backend.eval_reporter --format json --output reports/eval-report.json
.\.venv\Scripts\python -m intelliticket_backend.eval_reporter --list-cases
```

## 启动桌面端

桌面端需要后端先运行。默认连接 `http://127.0.0.1:8000`，也可以在界面中临时切换到内网服务器地址；当前桌面端只连接 FastAPI，不会自动启动或管理 Python 后端进程。

```powershell
cd "f:\wdxm\2.企业工单系统\frontend"
npm install
npm run dev
```

可通过 `frontend/.env` 设置默认后端地址，也可在桌面端页面中临时覆盖：

```env
VITE_INTELLITICKET_API_BASE_URL=http://127.0.0.1:8000
```

如果桌面端访问的不是默认 Vite 来源，需要同步配置后端 CORS：

```env
FRONTEND_ALLOWED_ORIGINS=["http://127.0.0.1:5173","http://localhost:5173"]
```

桌面端当前能力：

- 工单处理工作台布局：工单队列 / 当前工单 / 调查与证据；
- REST 提交 sample ticket 并展示 classification、context、diagnosis、routing、report 和 evidence；
- WebSocket 展示 `started`、5 个 `agent_progress`、`completed`、`error`、`cancelled`；
- 取消是 best-effort，可能收到 `cancelled`，也可能在取消前已完成而收到 `completed`；
- UI 明确显示“模拟数据 mock”，不代表真实生产系统。

## MVP 稳定性验收流

当前 MVP 稳定性验收应区分自动检查、真实运行观察和跳过项。测试通过不能替代真实 API、WebSocket、CLI 或 UI 行为观察。

推荐顺序：

1. 准备开发环境：

   ```powershell
   cd "f:\wdxm\2.企业工单系统"
   .\.venv\Scripts\python -m pip install -e ".[dev]"
   ```

2. 运行后端基线检查：

   ```powershell
   .\.venv\Scripts\python -m ruff check src tests
   .\.venv\Scripts\python -m pytest
   ```

3. 启动本地后端并观察运行面：

   ```powershell
   .\.venv\Scripts\python -m uvicorn intelliticket_backend.main:app --host 127.0.0.1 --port 8000
   ```

   至少观察：

   - `GET /api/v1/health` 返回 `data_mode: "mock"`；
   - `POST /api/v1/tickets/process` 能处理示例工单并返回 `ticket_id` / `run_id` / evidence；
   - `GET /api/v1/tickets` 和 `GET /api/v1/tickets/{ticket_id}` 能读取刚处理的历史；
   - WebSocket `/api/v1/tickets/process/ws` 在相关变更后能观察到 `started -> agent_progress x5 -> completed`。

4. 运行 eval CLI：

   ```powershell
   .\.venv\Scripts\python -m intelliticket_backend.eval_reporter --list-cases
   .\.venv\Scripts\python -m intelliticket_backend.eval_reporter --format text
   ```

5. 前端变更时，从 `frontend/` 运行并观察 UI：

   ```powershell
   npm run typecheck
   npm test
   npm run dev
   ```

   桌面端不会自动启动 Python 后端；必须先让后端运行，默认地址是 `http://127.0.0.1:8000`。

6. MCP 变更时，运行相关测试并用官方 MCP client 或 test harness 观察工具调用：

   ```powershell
   .\.venv\Scripts\python -m pytest tests/test_mcp_server.py
   .\.venv\Scripts\python -m intelliticket_backend.mcp_server --transport stdio
   ```

验收报告必须说明：执行过的命令、观察到的响应字段、失败输出、跳过项和原因。当前项目只使用本地 `mock_data/`，不代表真实 Prometheus、Grafana、Jira 或飞书接入；WebSocket 取消仍是 best-effort。

## 健康检查

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

示例响应：

```json
{
  "status": "ok",
  "service": "intelliticket-backend",
  "version": "0.1.0",
  "data_mode": "mock"
}
```

## SQLite 历史持久化

成功完成的工单会保存到本地 SQLite。默认路径：`data/intelliticket.sqlite3`，可通过环境变量覆盖：

```env
TICKET_HISTORY_DB_PATH=data/intelliticket.sqlite3
```

当前持久化 `completed` / `failed` / `cancelled` 终态工单。失败和取消记录只保存结构化错误与已产生的审计快照，不生成假的完整处理结果。

## 工单处理示例

```powershell
$body = @{
  text = "线上支付服务出现超时告警，订单量从正常1000/min降到300/min"
  data_mode = "mock"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/tickets/process `
  -ContentType "application/json" `
  -Body $body
```

接口会返回并保存：

- `ticket_id` / `run_id`；
- 工单分类和优先级；
- 影响服务；
- mock 上下文；
- 候选根因；
- 推荐处理团队和行动项；
- workflow trace；
- Supervisor route decisions；
- 最终报告；
- 所有证据条目。

## 工单历史查询

查询已持久化工单列表：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/tickets
```

分页参数：`limit` 默认 20、最大 100；`offset` 默认 0。空库会返回真实空列表，不返回示例或假数据。

查询单个工单：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/tickets/TCK-20260715-ABCDEF12
```

`ticket_id` 必须符合 `TCK-YYYYMMDD-XXXXXXXX` 格式。合法但不存在的 ID 返回结构化 `TICKET_NOT_FOUND`。

## WebSocket 进度流

当前还提供同一条工单处理流程的 WebSocket 进度接口：

```text
WS /api/v1/tickets/process/ws
```

连接后先发送 `start` 消息：

```json
{
  "type": "start",
  "request": {
    "text": "线上支付服务出现超时告警，订单量从正常1000/min降到300/min",
    "data_mode": "mock"
  }
}
```

服务端事件顺序：

```text
started -> agent_progress x5 -> completed
```

`agent_progress` 只包含 Agent 名称、步骤、状态、审计摘要和证据引用，不包含私有 chain-of-thought。

客户端可以发送：

```json
{"type": "cancel", "reason": "user_cancelled"}
```

取消是 best-effort：当前服务只在 Agent 边界检查取消信号。如果后端已经完成处理，服务端可能返回 `completed`；如果取消先被处理，则返回 `cancelled`。当前版本不支持断线恢复或事件 replay；`completed`、`failed` 和 `cancelled` 终态工单会进入 SQLite 历史，其中失败和取消不会生成假的完整处理结果。

## Mock Ops MCP 工具

当前提供一组 **mock-only** 本地运维知识 MCP 工具，用于查询 `mock_data/` 中的服务目录、指标快照、历史工单和 SOP 文档。它们不代表真实 Prometheus、Grafana、Jira 或飞书接入，所有返回证据都会显式标记 `data_mode: "mock"`。

可用工具：

- `lookup_service_catalog`
- `get_metric_snapshots`
- `get_incident_history`
- `get_sop_documents`

stdio 传输启动：

```powershell
cd "f:\wdxm\2.企业工单系统"
.\.venv\Scripts\python -m intelliticket_backend.mcp_server --transport stdio
```

HTTP / streamable HTTP 传输启动：

```powershell
cd "f:\wdxm\2.企业工单系统"
.\.venv\Scripts\python -m intelliticket_backend.mcp_server --transport streamable-http
```

> 注意：MCP 工具当前只暴露本地 mock 查询边界，不会在真实 provider 失败时自动回退到 mock 数据。

## 真实数据模式

当前 MVP 只支持 `data_mode: "mock"`。如果请求 `data_mode: "real"`，接口会返回结构化 `UNSUPPORTED_DATA_MODE` 错误，不会静默回退到 mock 数据。
