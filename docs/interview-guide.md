# 面试问答与可验证项目描述

## 为什么把 AI 做成异步任务

工单创建是业务主路径，外部模型调用延迟和失败率不可控。系统在同一数据库事务中先写 ticket、queued ai_run 和审计事件，提交成功后才投递 Redis。API 立即返回 `ticket_id/ai_run_id`，Worker 独立更新持久状态。这样浏览器断线不会取消任务，模型超时不会回滚工单，Worker 重启也能通过 heartbeat 和 stale recovery 恢复。

证据：`services/worker_tasks.py`、`repositories/ai_runs.py`、`tests/test_ai_pipeline.py`。

## 为什么 AI 结果必须人工确认

诊断模型只能基于当前证据提出候选根因和动作，不能证明真实变更已执行。Quality Gate 校验证据引用、记录置信度并强制 `requires_human_review=true`。运维可以采纳、修改或拒绝建议，最终解决必须写入根因、修复动作和验证结果；员工再确认关闭或重新打开。

证据：`services/ai_pipeline.py`、`tests/test_p5_workflow_e2e.py`。

## 如何防止重复认领

工单有递增 `version`。认领使用数据库条件更新：ticket_id、expected version 和允许状态必须同时匹配，并在同一语句中将 version 加一。两个请求并发执行时只有一个 rowcount 为 1；失败请求重新读取当前记录并返回 409 `TICKET_VERSION_CONFLICT`。这不是进程内锁，因此多线程请求仍由数据库裁决。

证据：`repositories/tickets.py::transition`、`tests/test_p5_fault_tolerance.py::test_concurrent_duplicate_claim_has_one_winner`、Locust 并发认领不变量。

## AI 完全不可用时怎么办

AI run 与 ticket 使用不同状态。LLM 超时或 Redis 投递失败只把 AI run 标记为 failed，记录 error_code 和审计事件；ticket 仍处于 pending/open，可由 operator 直接认领、回复、解决，员工照常确认关闭。`/ready` 在 Redis 不可用时返回 503，便于流量控制，但 `/health` 保持无依赖 liveness。

证据：`tests/test_p5_fault_tolerance.py` 的 LLM timeout 和 Redis failure 用例。

## 权限如何隔离

JWT 只证明 token 结构，服务端每次请求仍回查数据库用户和 active 状态。employee 只能查看自己提交的工单；operator/admin 可查看队列；admin 才能管理用户、团队、SLA 和服务目录。评论和附件复用工单可见性，internal 内容只返回给 operator/admin。停用用户后旧 Token 立即失败。

证据：`services/auth.py`、`services/ticket_workflow.py`、`api/attachments.py`、`tests/test_auth_security.py`、`tests/test_permissions.py`。

## SLA 怎么计算

SLA policy 按优先级维护响应和解决时限。系统用工单创建时间加 policy duration 得到 response_due_at/resolution_due_at；第一条运维公开回复设置 first_responded_at，解决设置 resolved_at。逾期查询分别判断两个 deadline，并暴露到 Prometheus gauge。

证据：`repositories/tickets.py::sla_deadlines`、`tests/test_ticket_workflow.py::test_sla_overdue_query_reports_response_and_resolution_breaches`。

## Worker 重启如何避免重复结果

Worker 开始前原子执行 `queued -> running`。若任务已 completed/failed，重复投递只读取已有终态，不再运行管线。running 任务的 heartbeat 超过阈值后恢复为 queued 并增加 retry_count；恢复后再次执行只写一次 `ai_triage_completed`。

证据：`tests/test_p5_fault_tolerance.py::test_worker_restart_recovery_is_idempotent`。

## 附件为什么不直接使用用户文件名

原文件名只作为展示元数据，磁盘路径使用服务端 UUID storage_key。上传采用流式写入并计算 SHA-256，同时校验扩展名、MIME、签名、空文件和大小；路径解析必须留在配置的附件根目录内。这样避免目录穿越、文件名碰撞和仅靠 Content-Type 的伪装。

证据：`services/attachments.py`、`tests/test_attachments.py`。

## 通知为什么独立持久化

钉钉是外部副作用，不应参与工单事务回滚。工单提交后创建 notification_delivery，再异步投递；attempt_count、task_id、error_message 和 sent/skipped/failed 状态可审计。网络失败有限重试，永久失败不会改变工单状态。

证据：`repositories/notifications.py`、`services/worker_tasks.py`、`tests/test_notification_delivery.py`。

## 压测说明了什么

5 用户、30 秒、约 13 req/s 的本地基线为 0 错误，聚合 P50/P95/P99 为 29/290/390 ms。队列查询 P95 390 ms，明显慢于创建和详情；10 用户超限运行触发 Nginx 限流，修正后突发请求返回 429。这个结果只能说明已记录环境，不支持外推生产人数或吞吐。

证据：[测试报告](test-report.md) 和 `reports/loadtest` 原始 CSV。

## 可验证的项目描述

以下表述可用于项目介绍或简历，并能在仓库中找到证据：

- 设计并实现 FastAPI + PostgreSQL 的角色化 IT 工单闭环，以数据库乐观锁处理并发认领，完整记录评论、内部备注、解决字段和审计事件。
- 将 AI 分诊改造成 Redis/Celery 持久化任务，支持有限重试、heartbeat 恢复、幂等终态和人工决策；LLM/Worker 故障不阻断人工流程。
- 使用 Docker Compose 部署 PostgreSQL、Redis、API、Worker 和 Nginx，补齐健康检查、Prometheus 指标、25 MiB 安全附件、异步通知及经全新实例验证的数据库/附件备份恢复。
- 编写后端、前端、故障和完整闭环测试，并用 Locust 记录请求分位数、错误率、限流行为和队列查询瓶颈。

不要写“支持某个团队人数”“高并发”“生产可用等级”等本项目没有验证的数据。
