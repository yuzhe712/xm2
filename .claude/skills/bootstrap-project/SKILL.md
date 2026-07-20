---
name: bootstrap-project
description: Initialize or extend the IntelliTicket desktop app + FastAPI ticket automation platform through the smallest runnable vertical slice. Use for project setup, scaffolding, first milestones, or adding major infrastructure.
argument-hint: [milestone or feature]
---

# Bootstrap Project

Apply the project rules in `CLAUDE.md`. Build incrementally; do not generate a complete speculative enterprise architecture in one pass.

## Before implementation

1. Inspect all existing files, dependency manifests, tests, environment examples, mock data, and launch scripts.
2. Restate the requested outcome and identify the smallest end-to-end ticket behavior that proves it.
3. List the exact files and dependencies to add or change.
4. Reuse existing working code before proposing a new abstraction.
5. If the user has not chosen a data source, app shell, authentication method, or external protocol version that changes the implementation, ask before coding.

## Vertical-slice order

Prefer this sequence unless the existing repository dictates otherwise:

1. Backend configuration, health endpoint, structured errors, and one test.
2. One real MVP flow: natural-language ops alert ticket → validated ticket processing response.
3. Mock ops data loader for services, metrics, deployments, historical incidents, and SOP documents.
4. Minimal Agent/workflow chain: intake → context retrieval → diagnosis → routing → report.
5. A minimal Electron + React screen that drives the real backend flow and displays the Agent run trace.
6. Persistence, SQLite, streaming progress, MCP/A2A adapters, Redis, or extra containers only when the current slice demonstrates the need.

## Required constraints

- Do not expose unfinished routes returning `{}`, `[]`, or fixed success values.
- Do not add fake authentication, wildcard production CORS, empty services, or dead abstractions.
- Mock/demo data failure must remain an explicit failure or partial result; never substitute plausible values silently.
- Mock/demo mode requires explicit `data_mode` in API responses and visible UI labeling.
- Do not claim real Jira, Prometheus, Grafana, Feishu, deployment, or production readiness without running and observing it.
- Keep provider/model settings and operational limits in configuration.
- Keep the first milestone focused on ops alert tickets; do not add login, multi-tenancy, Celery, Kubernetes, or multi-database support unless explicitly requested.

## Verification for each slice

- Run formatter/linter/type checks available in the repository.
- Add and run focused unit/API tests.
- Launch the affected backend or desktop-app flow and exercise the real ticket route/UI.
- Report exact commands, results, failures, and skipped infrastructure.

## Stop conditions

Stop and ask rather than guessing when the next step requires credentials, a paid API, an official protocol/SDK choice, destructive migration, or a ticket priority/routing business rule that is not established.
