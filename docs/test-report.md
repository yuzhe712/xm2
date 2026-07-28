# 测试与压测报告

记录日期：2026-07-28。所有数据均来自本地隔离 Compose project，不包含真实账号、密钥或工单内容。

## 测试环境

| 项目 | 配置 |
|---|---|
| 操作系统 | Windows 10 家庭中文版 10.0.19045 |
| CPU | Intel Core i7-11800H，8 核/16 线程 |
| 主机内存 | 15.8 GiB |
| Docker Engine | 29.6.2，16 CPU，约 7.7 GiB 内存 |
| Python / Locust | Python 3.13.9 / Locust 2.46.2 |
| 部署 | PostgreSQL 16 Alpine、Redis 7 Alpine、FastAPI、Celery Worker、Nginx 1.27 Alpine |
| 模式 | `DATA_MODE=mock`，外部通知关闭 |

## 自动化测试

| 检查 | 结果 |
|---|---|
| P4 收尾后端全量 | 238 passed |
| P5 新增闭环与故障测试 | 6 passed |
| 前端 Vitest | 45 passed |
| TypeScript typecheck | 通过 |
| Vite production build | 通过 |
| P5 改动 Ruff | 通过 |

项目所有者在正式收尾时决定不再执行文档完成后的最终全量回归。上表保留最后一次完整 P4 收尾基线和 P5 新增测试的定向结果，不将被中止的回归记为通过或失败。

## P5 故障矩阵

| 场景 | 预期与结果 |
|---|---|
| LLM 连续超时 | AI run 记录 `LLM_TIMEOUT`；工单仍可人工认领、回复、解决和关闭 |
| Redis 投递失败 | AI run 记录 `AI_QUEUE_UNAVAILABLE`，通知 delivery 记录 failed；工单可查询 |
| Worker 重启 | stale run 恢复 queued；重复执行只产生一个 AI 完成事件 |
| 重复认领 | 两个并发请求恰好一个 200、一个 409 |
| 权限越权 | 其他员工不能查看工单/附件；employee 不能认领或访问 admin API |

对应测试：`tests/test_p5_fault_tolerance.py`。完整 AI + 人工闭环：`tests/test_p5_workflow_e2e.py`。

## Compose 冒烟

- 全新 PostgreSQL 从 Alembic 0001 顺序迁移到 0005，migration 退出码 0。
- PostgreSQL、Redis、API、Worker、Frontend/Nginx 全部启动；API 和前端 healthcheck healthy。
- `/health`、`/ready`、`/metrics` 和 Nginx 安全响应头通过。
- Worker 停止时成功创建并查询工单，`/ready` 仍只依赖 PostgreSQL/Redis。
- 员工附件上传/下载内容一致；非所有者员工下载返回 403。
- 数据库和附件备份在新 Compose project 的空卷中恢复，附件 ID、大小和 SHA-256 一致。

## Locust 场景

`loadtests/locustfile.py` 按权重执行：

- `POST /api/v1/tickets/submit`
- `GET /api/v1/tickets/queue`
- `GET /api/v1/tickets/{id}/workflow`
- 两名处理人对同一 version 并发 `POST .../claim`

并发认领除记录两个 HTTP 请求外，还记录 `concurrent claim invariant`；只有状态集合恰好为 `[200, 409]` 才算成功。为稳定验证 version 1 竞态，压测窗口暂停 Worker，同时记录 AI/通知队列堆积，结束后恢复 Worker。

## 限流内基线

参数：5 用户、spawn rate 1/s、30 秒。开始时约 244 张工单；运行后整个验证库最终达到 436 张工单、436 个 AI run、941 个审计事件。压测结束前队列堆积 870 个任务；Worker 恢复后队列下降到 0。

| 请求 | 数量 | 失败 | P50 | P95 | P99 |
|---|---:|---:|---:|---:|---:|
| 创建工单 | 131 | 0 | 31 ms | 58 ms | 95 ms |
| 队列查询 | 78 | 0 | 230 ms | 390 ms | 590 ms |
| 详情查询 | 95 | 0 | 10 ms | 20 ms | 38 ms |
| 认领请求 | 42 | 0 | 22 ms | 47 ms | 50 ms |
| 并发认领不变量 | 21 | 0 | 27 ms | 49 ms | 51 ms |
| 聚合 | 382 | 0 | 29 ms | 290 ms | 390 ms |

聚合吞吐约 13.11 req/s，错误率 0%。原始结果：`reports/loadtest/p5-20260728-baseline_*.csv`。

## 超限与瓶颈

首次 10 用户、30 秒运行达到约 26.66 req/s，原始 CSV 汇总 777 个请求、157 个失败，错误率 20.21%。失败由 Nginx `20r/s + burst 40` 限流触发；当时默认返回 503。验证后配置改为 `limit_req_status 429`，200 个并发 `/health` 突发请求得到 42 个 200 和 158 个 429，不再把限流伪装成服务不可用。

主要瓶颈是 `/tickets/queue`：当前实现加载全部 pending/open SQL 记录、逐项读取 AI 状态，再与兼容存储记录合并后才切片。随着数据从 244 增长到 436，10 用户短跑中的队列查询 P95 上升到约 1.4 秒。后续优化方向是数据库侧分页/计数、联表批量读取 AI 状态并停止运行时兼容存储合并。

这些结果只描述当前机器、数据量、配置和测试时段，不构成生产容量承诺。

## 复现

先准备隔离环境中的一个 employee 和两个 operator/admin 账号；密码只通过环境变量传入：

```powershell
$env:LOADTEST_EMPLOYEE_USERNAME = "<employee>"
$env:LOADTEST_EMPLOYEE_PASSWORD = "<password>"
$env:LOADTEST_OPERATOR_A_USERNAME = "<operator A>"
$env:LOADTEST_OPERATOR_A_PASSWORD = "<password>"
$env:LOADTEST_OPERATOR_B_USERNAME = "<operator B>"
$env:LOADTEST_OPERATOR_B_PASSWORD = "<password>"

python -m pip install -e ".[loadtest]"
python -m locust -f loadtests/locustfile.py --headless `
  --users 5 --spawn-rate 1 --run-time 30s `
  --host http://127.0.0.1:8080 --csv reports/loadtest/recheck
```

不要对含真实数据的生产实例执行该场景。

## 真实外部 API

安全审计发现旧冒烟脚本曾硬编码 DeepSeek 密钥，当前源码已删除该值并改为运行时读取。该旧密钥必须在服务端撤销/轮换，不能继续使用。当前环境没有新的 `DEEPSEEK_API_KEY`，因此真实外部 API 冒烟状态为 **未执行**，不是通过。

提供已轮换的运行时密钥后执行：

```powershell
$env:DEEPSEEK_API_KEY = "<rotated key>"
python scripts/e2e_llm_test.py
```

脚本成功条件：至少两次真实模型调用、Quality Gate passed、`requires_human_review=true` 且存在证据；输出不包含密钥、Prompt 或模型原始内容。
