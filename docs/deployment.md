# 部署与运维

## 前置条件

- Docker Engine 及 Docker Compose
- 可访问所需容器仓库；真实 AI 模式还需访问 DeepSeek API
- 三个必填部署变量：`JWT_SECRET_KEY`、`POSTGRES_PASSWORD`、`BOOTSTRAP_ADMIN_PASSWORD`

不要把真实密钥写入 `.env.example`、Compose、命令历史、日志或仓库。正式环境应使用宿主机密钥管理或受限权限的环境文件。

## 启动

PowerShell 示例中的值都是占位符：

```powershell
$env:JWT_SECRET_KEY = "<至少 32 位随机签名密钥>"
$env:POSTGRES_PASSWORD = "<PostgreSQL 密码，URL 保留字符需编码>"
$env:BOOTSTRAP_ADMIN_PASSWORD = "<首次管理员密码>"
$env:HTTP_PORT = "8080"
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
```

启动顺序由健康条件约束：PostgreSQL/Redis healthy -> migration 成功退出 -> API healthy -> Frontend/Nginx。Worker 也等待 migration 成功后启动。

| 服务 | 作用 | 持久数据 |
|---|---|---|
| `postgres` | 用户、工单、AI、通知、审计 | `postgres-data` |
| `redis` | Celery broker/result backend | `redis-data` |
| `migrate` | `alembic upgrade head` 一次性任务 | 无 |
| `api` | FastAPI | 共享附件卷 |
| `worker` | AI 和通知任务 | 共享附件卷 |
| `frontend` | Nginx + Web 静态资源 + API 代理 | 无 |

## 健康与监控

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8080/ready
Invoke-WebRequest http://127.0.0.1:8080/metrics
```

- `/health` 是无依赖 liveness。
- `/ready` 只检查 PostgreSQL 和 Redis；任一失败返回 503。
- `/metrics` 提供请求量/延迟、AI 任务 outcome、AI 队列长度和 SLA 逾期 gauge。

建议监控：ready 连续失败、5xx、P95 延迟、`intelliticket_ai_queue_length`、`AI_TASKS{outcome="failed"}` 比例和 SLA overdue。

## Nginx 边界

- API 限流：每来源 IP 20 req/s，burst 40，超限返回 429。
- 上传限制：25 MiB；后端 `ATTACHMENT_MAX_BYTES` 默认同为 25 MiB。
- 响应头：CSP、Referrer-Policy、X-Content-Type-Options、X-Frame-Options、Permissions-Policy。
- API 与前端同源；非默认端口/域名需配置 `FRONTEND_ALLOWED_ORIGINS`。

前端构建默认使用可覆盖的 npm/Electron 镜像参数，Web 镜像不会下载 Electron 二进制：

```powershell
$env:NPM_REGISTRY = "https://registry.npmjs.org"
$env:ELECTRON_MIRROR = "https://github.com/electron/electron/releases/download/"
docker compose build frontend
```

## 外部集成

需要真实 LLM 时只在运行环境设置：

```powershell
$env:DEEPSEEK_API_KEY = "<运行时密钥>"
$env:INTAKE_AGENT_STRATEGY = "llm"
$env:DIAGNOSIS_AGENT_STRATEGY = "llm"
python scripts/e2e_llm_test.py
```

冒烟脚本不打印密钥、Prompt 或模型原始响应。飞书和钉钉配置分别见独立集成文档；未配置时人工工单闭环仍可使用。

## 备份

maintenance profile 使用 PostgreSQL 官方镜像执行 `pg_dump`，同时归档附件并生成 SHA-256：

```powershell
$env:POSTGRES_PASSWORD = "<当前数据库密码>"
docker compose --profile maintenance run --rm backup
```

默认输出到 `./backups/<UTC timestamp>/`：

- `database.dump`
- `attachments.tar.gz`
- `checksums.sha256`
- `manifest.txt`

应将备份复制到独立受控存储，并定期执行恢复演练。只生成文件而未验证恢复，不算有效备份。

## 全新实例恢复

恢复会替换目标数据库对象，且要求目标附件卷为空。先确认 project 名和备份目录，避免对现有实例误操作：

```powershell
$env:POSTGRES_PASSWORD = "<目标数据库密码>"
$env:JWT_SECRET_KEY = "<目标实例签名密钥>"
$env:BOOTSTRAP_ADMIN_PASSWORD = "<仅用于 Compose 配置校验的安全值>"
$env:CONFIRM_RESTORE = "YES"
$env:RESTORE_SOURCE = "/backups/<UTC timestamp>"
docker compose -p intelliticket-restored --profile maintenance run --rm restore
docker compose -p intelliticket-restored up -d api worker frontend
```

恢复脚本先校验两个备份文件的 SHA-256 和附件归档路径安全，再执行 `pg_restore --clean --if-exists`。验收至少应查询原工单并下载一个附件比对哈希。

## 升级

1. 先执行并验证备份。
2. 拉取代码或镜像后运行 `docker compose config --quiet`。
3. `docker compose build`。
4. `docker compose up -d`，由 migration 容器先升级数据库。
5. 检查 migration 退出码、`/ready`、前端和 Worker 日志。
6. 执行登录、创建、查询和附件下载冒烟。

不要在启动脚本中手写 DDL，也不要跳过 Alembic 版本。

## 故障演练

```powershell
# Worker 停止时验证人工创建/查询仍可用
docker compose stop worker

# 恢复 Worker并观察队列下降
docker compose start worker
Invoke-WebRequest http://127.0.0.1:8080/metrics
```

停止 Redis 时 `/ready` 应为 503；恢复后应重新变为 200。生产演练必须在隔离环境执行，不要对含真实数据的实例随意停止依赖或运行 restore。

## 停止

```powershell
docker compose stop
```

`docker compose down -v` 会删除数据库、Redis 和附件卷，不属于日常停止操作；除非明确要销毁实例并已有可恢复备份，否则不要执行。
