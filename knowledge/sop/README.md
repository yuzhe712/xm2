# IntelliTicket 运维 SOP Markdown 知识库

## 定位与边界

本目录用于沉淀可导入知识库的运维 SOP Markdown 文档，覆盖 Linux、Kubernetes/容器、CI/CD、消息队列、DNS/网络等常见企业运维场景。

当前边界：

- 当前 IntelliTicket 运行时仍使用 [mock_data/](../../mock_data/) 中的本地 mock 数据；
- 本目录暂不被后端自动读取，也不等同于运行时检索源；
- SOP 文档只作为知识参考，不代表当前故障事实；
- Kubernetes、Kafka、RabbitMQ、CI/CD、DNS/网络等是知识库支持的 SOP 主题，不代表当前项目已经接入这些生产系统；
- 第一版参考来源为公开资料候选，因生成时未逐条联网抓取校验，状态统一标记为 `draft_public_reference`。

## 文档状态

| 状态 | 含义 |
|---|---|
| `draft_public_reference` | 基于公开来源候选整理，待后续联网校验和人工复核。 |
| `reviewed_public_reference` | 已完成来源链接、内容摘录和适用性复核。 |
| `deprecated` | 不建议继续使用，保留用于历史追溯。 |

## 覆盖矩阵

| 分类 | SOP | 文件 | 状态 |
|---|---|---|---|
| Linux | CPU 使用率过高 | [linux/cpu-high.md](linux/cpu-high.md) | `draft_public_reference` |
| Linux | 内存使用率过高 | [linux/memory-high.md](linux/memory-high.md) | `draft_public_reference` |
| Linux | OOM | [linux/oom.md](linux/oom.md) | `draft_public_reference` |
| Linux | 磁盘空间不足 | [linux/disk-full.md](linux/disk-full.md) | `draft_public_reference` |
| Linux | inode 用尽 | [linux/inode-full.md](linux/inode-full.md) | `draft_public_reference` |
| Linux | 日志增长过快 | [linux/logs-growth.md](linux/logs-growth.md) | `draft_public_reference` |
| Kubernetes | CrashLoopBackOff | [kubernetes/crashloopbackoff.md](kubernetes/crashloopbackoff.md) | `draft_public_reference` |
| Kubernetes | ImagePullBackOff | [kubernetes/imagepullbackoff.md](kubernetes/imagepullbackoff.md) | `draft_public_reference` |
| Kubernetes | Pod Pending | [kubernetes/pod-pending.md](kubernetes/pod-pending.md) | `draft_public_reference` |
| Kubernetes | Service 无法访问 | [kubernetes/service-unreachable.md](kubernetes/service-unreachable.md) | `draft_public_reference` |
| Kubernetes | HPA 扩容异常 | [kubernetes/hpa-not-scaling.md](kubernetes/hpa-not-scaling.md) | `draft_public_reference` |
| Kubernetes | OOMKilled | [kubernetes/oomkilled.md](kubernetes/oomkilled.md) | `draft_public_reference` |
| CI/CD | 发布失败 | [cicd/release-failure.md](cicd/release-failure.md) | `draft_public_reference` |
| CI/CD | 回滚处理 | [cicd/rollback.md](cicd/rollback.md) | `draft_public_reference` |
| CI/CD | 配置变更导致故障 | [cicd/config-change.md](cicd/config-change.md) | `draft_public_reference` |
| CI/CD | 环境变量缺失或错误 | [cicd/env-var-issue.md](cicd/env-var-issue.md) | `draft_public_reference` |
| CI/CD | 依赖版本冲突 | [cicd/dependency-conflict.md](cicd/dependency-conflict.md) | `draft_public_reference` |
| CI/CD | 灰度发布失败 | [cicd/canary-failure.md](cicd/canary-failure.md) | `draft_public_reference` |
| 消息队列 | Kafka 消费积压 / Consumer Lag | [messaging/kafka-lag.md](messaging/kafka-lag.md) | `draft_public_reference` |
| 消息队列 | Kafka 重复消费 | [messaging/kafka-duplicate-messages.md](messaging/kafka-duplicate-messages.md) | `draft_public_reference` |
| 消息队列 | Kafka 消息丢失 | [messaging/kafka-message-loss.md](messaging/kafka-message-loss.md) | `draft_public_reference` |
| 消息队列 | RabbitMQ 队列堆积 | [messaging/rabbitmq-backlog.md](messaging/rabbitmq-backlog.md) | `draft_public_reference` |
| 消息队列 | RabbitMQ 重复消费 | [messaging/rabbitmq-duplicate-messages.md](messaging/rabbitmq-duplicate-messages.md) | `draft_public_reference` |
| 消息队列 | RabbitMQ 消息丢失 | [messaging/rabbitmq-message-loss.md](messaging/rabbitmq-message-loss.md) | `draft_public_reference` |
| DNS/网络 | DNS 解析失败 | [network/dns-resolution-failure.md](network/dns-resolution-failure.md) | `draft_public_reference` |
| DNS/网络 | 内网域名不可用 | [network/internal-domain-failure.md](network/internal-domain-failure.md) | `draft_public_reference` |
| DNS/网络 | 网络延迟升高 | [network/high-latency.md](network/high-latency.md) | `draft_public_reference` |
| DNS/网络 | 网络丢包 | [network/packet-loss.md](network/packet-loss.md) | `draft_public_reference` |
| DNS/网络 | 防火墙/安全组阻断 | [network/firewall-security-group-blocked.md](network/firewall-security-group-blocked.md) | `draft_public_reference` |
| DNS/网络 | 端口不通 | [network/port-unreachable.md](network/port-unreachable.md) | `draft_public_reference` |

## Frontmatter 规范

每篇 SOP 必须包含：

```yaml
---
sop_id: SOP-LINUX-CPU-HIGH
source_type: sop_document
service: linux
category: linux
title: Linux CPU 使用率过高处理 SOP
data_mode: public_reference
quality: draft_public_reference
last_reviewed_at: 2026-07-18
references:
  - title: Linux man-pages project
    url: https://man7.org/linux/man-pages/
---
```

字段说明：

- `sop_id`：稳定唯一标识，后续可用于导入、索引或 trace；
- `source_type`：保持为 `sop_document`，与现有证据语义接近；
- `service`：知识主题或适用技术域，不代表项目真实接入服务；
- `category`：分类目录；
- `data_mode`：使用 `public_reference`，表示公开知识参考；
- `quality`：第一版统一为 `draft_public_reference`；
- `references`：公开来源候选，后续需要联网校验。

## 维护流程

1. 新增 SOP 前先检查是否已有相近主题；
2. 使用统一章节结构：适用场景、不适用场景、处置目标、快速分级、证据保留、排查步骤、常用命令、缓解动作、恢复确认、风险注意事项、报告摘要、参考资料；
3. 只引用公开资料，不写入密钥、真实内网地址、账号、token；
4. 未联网校验前保持 `quality: draft_public_reference`；
5. 修改或新增 SOP 后同步更新本 README 覆盖矩阵；
6. 若后续要让后端读取 Markdown，需要另行设计导入、分块、检索和 evidence 映射流程。

## 禁止事项

- 禁止把公开资料说成当前系统实时观测；
- 禁止声称项目已经接入未实现的 Kubernetes、Kafka、RabbitMQ、Prometheus、CI/CD 或网络诊断系统；
- 禁止把未校验来源标记为 `reviewed_public_reference`；
- 禁止在 SOP 中写入公司敏感信息、密钥、真实内网域名或账号。