---
name: review-architecture
description: Audit the implemented IntelliTicket architecture for protocol conformance, concurrency, evidence integrity, mock/real separation, security, tests, and unsupported claims. Use at milestones or before release.
argument-hint: [scope]
---

# Review Architecture

Review only files that exist. Mark absent planned capabilities as `尚未实现`; do not invent defects in imagined code.

## Inspection order

1. Project guidance, dependency manifests, configuration, mock data, and launch/deployment files.
2. Ticket/ops domain services and evidence/provenance models.
3. Agents, workflow/LangGraph state/reducers, routing, diagnosis, routing recommendations, and report synthesis.
4. MCP/A2A adapters and protocol tests if present.
5. API, desktop app integration, authentication, tenant/team boundaries, streaming, and external integrations.
6. Tests, ticket evals, observability, and production-readiness or accuracy claims.

## Required review dimensions

- Protocol conformance and pinned official SDK/spec versions.
- Workflow/LangGraph state serialization, reducers, parallel update safety, termination, and checkpoints.
- Ticket evidence provenance, freshness, units, services, confidence methods, and abstention.
- Mock/demo/real data isolation and visible UI/API labeling.
- Failure classification, retries, timeouts, cancellation, and partial-result semantics.
- Authentication, authorization, tenant/team isolation, secrets, and boundary validation if implemented.
- Logging, ticket IDs, run IDs, metrics, and auditable decisions.
- Test/eval coverage and whether deployment/accuracy/integration claims have observed evidence.

## High-risk patterns to detect

- handmade stdin/stdout JSON-RPC labeled as MCP;
- internal dataclasses labeled A2A without conformance tests;
- parallel nodes overwriting shared mutable dictionaries;
- external failure silently replaced by fabricated mock/demo data;
- hardcoded model parameters, provider secrets, or demo conclusions;
- runtime `TODO`, `pass`, empty success responses, or unreachable stubs;
- private chain-of-thought exposed in logs or UI;
- claims of real Jira/Prometheus/Grafana/Feishu integration without working code and tests;
- production or accuracy claims unsupported by tests or a driven runtime flow.

## Finding format

For every confirmed finding include:

- severity: critical/high/medium/low;
- concrete file and line;
- failure scenario and impact;
- why current safeguards do not prevent it;
- minimal recommended correction;
- verification needed after correction.

Separate sections for `已确认缺陷`, `开放问题`, `尚未验证的声明`, and `尚未实现`. Rank actions by severity and dependency order. If nothing is confirmed, say so explicitly and list what was actually inspected.
