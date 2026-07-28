# IntelliTicket — 企业级智能工单自动化处理平台

<p align="center">
  <img src="https://img.shields.io/badge/version-0.1.0-blue" alt="Version">
  <img src="https://img.shields.io/badge/python-3.11+-green" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-yellow" alt="License">
  <img src="https://img.shields.io/badge/status-MVP-orange" alt="Status">
</p>

---

## 项目简介

IntelliTicket 是一个面向企业内部 IT 运维与支持场景的**多 Agent 协作式智能工单自动化处理平台**。系统接收自然语言描述的运维告警工单，通过确定性编排引擎驱动多个专项 Agent 协作，自动完成工单分类、优先级判定、运维上下文检索、根因诊断、处理建议生成与结构化报告输出，并提供完整的**证据溯源链**与**可审计执行轨迹**。

核心定位：**单公司单实例**，不引入 SaaS 多租户复杂性。所有运维上下文显式标记数据来源（`mock` / `real`），拒绝静默回退与幻觉结论。

---

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│                   Electron 桌面端                     │
│          React / Vite / TypeScript                   │
│   ┌─────────┐  ┌──────────┐  ┌─────────────────┐   │
│   │ 工单队列 │  │ 工单工作台 │  │ Agent 执行链路  │   │
│   └─────────┘  └──────────┘  └─────────────────┘   │
└──────────────────────┬──────────────────────────────┘
                       │ REST / WebSocket
┌──────────────────────▼──────────────────────────────┐
│                 FastAPI 后端                          │
│   ┌─────────────────────────────────────────────┐   │
│   │           API Layer (路由 + 验证)             │   │
│   ├──────┬──────┬──────┬──────┬──────┬─────────┤   │
│   │health│ticket│auth  │desks │eval  │knowledge│   │
│   └──────┴──────┴──────┴──────┴──────┴─────────┘   │
│   ┌─────────────────────────────────────────────┐   │
│   │       Service Layer (业务逻辑)                │   │
│   │  orchestrator · support_workflow             │   │
│   │  service_desk · ticket_processing            │   │
│   │  notifications · case_retrieval              │   │
│   └─────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────┐   │
│   │         Multi-Agent Engine                    │   │
│   │  Intake → Context → Diagnosis → Routing →   │   │
│   │  SupportReply → Reviewer → Report           │   │
│   └─────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────┐   │
│   │         Repository / Data Layer              │   │
│   │  ticket_history (SQLite) · mock_ops_data     │   │
│   │  user_repository · knowledge connectors      │   │
│   └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

---

## 多 Agent 协作引擎

### 编排模型

采用 **Supervisor + 确定性路由** 架构。Supervisor 根据每个 Agent 的输出状态（证据质量、置信度、冲突与缺口）决定是否衔接到下一个 Agent、跳过某个阶段或终止处理。

```
用户输入工单
    │
    ▼
┌──────────────┐    ┌─────────────────────────────────────────┐
│ Intake Agent │───▶│ 工单分类 · 优先级判定 · 症状/指标提取   │
└──────┬───────┘    └─────────────────────────────────────────┘
       │
       ▼
┌──────────────┐    ┌─────────────────────────────────────────┐
│Context Agent │───▶│ 部署记录 · 指标快照 · 历史工单 · SOP   │
└──────┬───────┘    └─────────────────────────────────────────┘
       │
       ▼
┌──────────────┐    ┌─────────────────────────────────────────┐
│Diagnosis     │───▶│ 根因候选 · 证据链 · 置信度 · 不确定性  │
│Agent         │    └─────────────────────────────────────────┘
└──────┬───────┘
       │
       ▼
┌──────────────┐    ┌─────────────────────────────────────────┐
│Routing Agent │───▶│ 处理团队 · 行动项 · SOP 引用 · 升级策略│
└──────┬───────┘    └─────────────────────────────────────────┘
       │
       ▼
┌──────────────┐
│Support Reply │───▶ 面向提交者的自然语言回复草稿
│Agent         │
└──────┬───────┘
       │
       ▼
┌──────────────┐    ┌─────────────────────────────────────────┐
│Reviewer      │───▶│ 质量审查 · 证据闭合检查 · 降级标记    │
│Agent         │    └─────────────────────────────────────────┘
└──────┬───────┘
       │
       ▼
┌──────────────┐    ┌─────────────────────────────────────────┐
│Report Agent  │───▶│ 最终报告 · 执行轨迹 · 证据汇总        │
└──────────────┘    └─────────────────────────────────────────┘
```

### Agent 职责矩阵

| Agent | 核心职责 | 输入 | 输出 |
|-------|---------|------|------|
| **Intake** | 自然语言理解、分类、定级 | 原始工单文本 | `TicketClassification` |
| **Context** | 运维上下文检索 | 分类结果 + 服务名 | `RetrievedContext` + 证据列表 |
| **Diagnosis** | 根因分析与证据推理 | 上下文 + 历史工单 | `DiagnosisResult` + 候选根因 |
| **Routing** | 处理分派与升级建议 | 诊断 + SOP | `RoutingRecommendation` |
| **Support Reply** | 面向提交者的回复草稿 | 全链路结果 | 自然语言回复 |
| **Reviewer** | 质量审查与证据闭合 | 全链路结果 | `ReviewResult` + 改进建议 |
| **Report** | 最终报告汇总 | 全链路结果 | `FinalReport` |

---

## 证据与溯源体系

系统遵循严格的证据契约，每一步推理均需记录可追溯的来源：

```
每个证据条目记录：
├── evidence_id      证据标识
├── source_type      来源类型（ticket_input / metric_snapshot / incident_history / sop_document）
├── source_id/name   数据源标识
├── observed_at      观测时间
├── service          关联服务
├── quality          数据质量状态
├── data_mode        mock / real 显式标记
└── confidence       置信度（如有可量化方法）
```

输出严格区分五类声明：

| 类别 | 说明 | 示例 |
|------|------|------|
| **事实** | 工单输入或数据源直接提供 | "订单量从 1000/min 降至 300/min" |
| **推导** | 规则或模型计算得出 | "降幅 70%，触发 P1 优先级规则" |
| **假设** | 输入不足时的前提 | "假定近 1 小时内无部署变更" |
| **未知** | 当前信息无法确定 | "缺乏 Pod 内存使用率数据" |
| **建议** | 基于事实、推导和 SOP | "建议检查 payment-gateway 连接池" |

---

## 技术栈

| 层级 | 技术选型 |
|------|---------|
| **桌面端** | Electron · React 18 · Vite · TypeScript |
| **后端框架** | FastAPI · asyncio · Pydantic v2 |
| **LLM 集成** | DeepSeek API（可配置切换）· 多模型路由与负载均衡 |
| **数据存储** | SQLAlchemy 2.0 · Alembic · PostgreSQL（生产）· SQLite（测试/兼容） |
| **实时通信** | WebSocket（Agent 进度推送） |
| **知识连接** | 飞书知识库 · 钉钉通知（可选扩展点） |
| **工具协议** | MCP（Mock Ops 运维数据查询工具） |
| **代码质量** | pytest（29 个测试文件）· ruff · type hints |
| **配置管理** | pydantic-settings · 从共享 secrets 文件安全加载密钥 |

---

## 项目结构

```
2.企业工单系统/
├── src/intelliticket_backend/    # Python 后端
│   ├── api/                       # REST 路由层
│   │   ├── tickets.py            # 工单处理 API（REST + WebSocket）
│   │   ├── auth.py               # 认证接口
│   │   ├── desks.py              # 服务台资源接口
│   │   └── health.py             # 健康检查
│   ├── services/                  # 业务逻辑层
│   │   ├── agents/               # 7 个专项 Agent
│   │   ├── knowledge/            # 知识库服务 + 连接器
│   │   ├── notifications/        # 通知服务（钉钉等）
│   │   ├── orchestrator.py       # Supervisor 编排引擎
│   │   ├── ticket_processing.py  # 工单处理流水线
│   │   ├── support_workflow.py   # 确定性工作流
│   │   └── llm.py               # LLM 客户端抽象
│   ├── schemas/                   # Pydantic 数据模型
│   ├── repositories/              # 数据访问层
│   ├── config.py                 # 配置中心（安全加载 secrets）
│   ├── errors.py                 # 结构化错误体系
│   ├── mcp_server.py             # MCP 工具服务器
│   └── main.py                   # 应用入口
├── frontend/                      # Electron 桌面端
│   └── src/renderer/src/
│       ├── components/            # 20+ React 组件
│       │   ├── TicketInputPanel   # 工单输入面板
│       │   ├── ClassificationPanel
│       │   ├── ContextPanel
│       │   ├── DiagnosisPanel
│       │   ├── RoutingPanel
│       │   ├── ResultReport       # 最终报告展示
│       │   ├── AgentTimeline      # Agent 执行链路可视化
│       │   └── EmployeeDashboard  # 工作台布局
│       ├── hooks/                 # 自定义 Hooks
│       ├── api/                   # API 调用封装
│       └── types/                 # TypeScript 类型定义
├── tests/                         # 29 个 pytest 测试文件
├── mock_data/                     # 本地模拟运维数据
│   ├── services.json              # 服务目录
│   ├── incidents.json             # 历史事件
│   ├── metrics.json               # 指标快照
│   ├── deploy_records.json        # 部署记录
│   └── sop_docs.json              # SOP 文档
├── docs/                          # 集成文档
├── pyproject.toml                 # 项目元数据与依赖
└── .env.example                   # 环境变量模板
```

---

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- npm 9+

### 1. 后端启动

```powershell
cd 2.企业工单系统

# 创建虚拟环境并安装依赖
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"

# 在忽略提交的 .env 中设置 JWT_SECRET_KEY、DATABASE_URL，以及首次启动所需的
# BOOTSTRAP_ADMIN_USERNAME / BOOTSTRAP_ADMIN_PASSWORD，然后执行迁移
.\.venv\Scripts\python -m alembic upgrade head

# 运行测试
.\.venv\Scripts\python -m pytest

# 启动服务
.\.venv\Scripts\python -m uvicorn intelliticket_backend.main:app --reload --host 127.0.0.1 --port 8000
```

验证：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

```json
{
  "status": "ok",
  "service": "intelliticket-backend",
  "version": "0.1.0",
  "data_mode": "mock"
}
```

### 2. 桌面端启动

```powershell
cd 2.企业工单系统\frontend
npm install
npm run dev
```

桌面端默认连接 `http://127.0.0.1:8000`，可在界面中切换到内网地址。

---

## API 概览

### 工单处理

```powershell
$loginBody = @{
  user_id = $env:INTELLITICKET_USERNAME
  password = $env:INTELLITICKET_PASSWORD
} | ConvertTo-Json
$login = Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/auth/login `
  -ContentType "application/json" -Body $loginBody
$headers = @{ Authorization = "Bearer $($login.token)" }

$body = @{
  text = "线上支付服务出现超时告警，订单量从正常1000/min降到300/min"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/tickets/process `
  -Headers $headers -ContentType "application/json" -Body $body
```

`data_mode` 由后端部署配置统一决定，客户端提交的同名字段不会改变运行模式。

响应用于返回并持久化：`ticket_id`、`run_id`、分类、优先级、影响服务、上下文、根因候选、处理建议、workflow trace、Supervisor 路由决策、最终报告及全部证据条目。

### WebSocket 实时进度

```
WS /api/v1/tickets/process/ws?access_token=<登录 token>
```

事件流：`started → agent_progress × N → completed / failed / cancelled`

### 历史查询

```powershell
# 分页列表
Invoke-RestMethod -Headers $headers `
  "http://127.0.0.1:8000/api/v1/tickets?limit=20&offset=0"

# 单个工单
Invoke-RestMethod -Headers $headers `
  http://127.0.0.1:8000/api/v1/tickets/TCK-20260715-ABCDEF12
```

### Eval CLI

```powershell
.\.venv\Scripts\python -m intelliticket_backend.eval_reporter --list-cases
.\.venv\Scripts\python -m intelliticket_backend.eval_reporter --format text
.\.venv\Scripts\python -m intelliticket_backend.eval_reporter --format json --output reports/eval-report.json
```

### MCP 工具

项目提供一组 Mock Ops MCP 工具，可查询本地运维数据集：

- `lookup_service_catalog` — 服务目录查询
- `get_metric_snapshots` — 指标快照查询
- `get_incident_history` — 历史事件查询
- `get_sop_documents` — SOP 文档查询

```powershell
.\.venv\Scripts\python -m intelliticket_backend.mcp_server --transport stdio
```

---

## 安全设计

| 层面 | 措施 |
|------|------|
| **密钥管理** | 从共享加密配置文件加载，禁止写入源码与日志 |
| **API Key** | `SecretStr` 类型包装，日志/响应中不可见 |
| **数据模式** | 所有证据显式标记 `mock` 或 `real`，拒绝静默回退 |
| **LLM 输出** | 经 Schema + Allowlist + 业务规则三重校验 |
| **错误策略** | 分级 fail-open / fail-closed，不可恢复证据缺失时 abstain |
| **CORS** | 白名单模式，仅允许配置的来源 |
| **单实例** | 不引入 `tenant_id`，从架构层面消除跨租户泄露风险 |

---

## 测试覆盖

29 个测试文件覆盖后端核心路径：

```powershell
.\.venv\Scripts\python -m pytest -v
```

| 测试模块 | 覆盖内容 |
|---------|---------|
| `test_config.py` | 配置加载、密钥解析、SecretStr 安全 |
| `test_health.py` | 健康检查接口 |
| `test_llm_client.py` | LLM 客户端抽象 |
| `test_agent_*.py` | 各 Agent 独立逻辑 |
| `test_*_orchestrator.py` | Supervisor 编排引擎 |
| `test_ticket_processing_*.py` | 工单处理 REST + WebSocket |
| `test_mcp_server.py` | MCP 工具与传输 |
| `test_notifications.py` | 通知服务（钉钉） |
| `test_feishu_knowledge_connector.py` | 飞书知识库连接 |

---

## 扩展路线

| 阶段 | 内容 |
|------|------|
| **P0（已完成）** | 数据库用户、角色权限、Alembic 迁移、部署密钥与服务端数据模式 |
| **P1（待执行）** | 人工受理、原子认领、分派、评论、解决与确认关闭闭环 |
| **P2（待执行）** | Redis/Celery AI 任务持久化与三阶段诊断流水线 |
| **P3（待执行）** | 员工、运维、管理员角色化 Web 工作区 |
| **P4（待执行）** | 附件、异步通知、Compose、健康检查与监控 |
| **P5（待执行）** | 完整集成、故障、部署和真实压测验证 |

---

## 许可证

MIT License
