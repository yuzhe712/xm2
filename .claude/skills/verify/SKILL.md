---
name: verify
description: Verify IntelliTicket changes end-to-end by running the affected backend API, WebSocket stream, eval CLI, desktop frontend, and MCP mock ops tools as applicable. Use after nontrivial product changes before claiming completion.
argument-hint: [changed area or flow]
---

# Verify IntelliTicket

Follow `CLAUDE.md`, especially completion standards, mock/real boundaries, evidence provenance, and the rule that changed product behavior is not complete until the affected runtime flow has been observed.

## Decide scope first

Inspect the current diff or requested change and choose the smallest verification set that exercises the changed runtime surface.

Do not run every check mechanically if the change only affects one area, but include every touched boundary:

- backend service/API
- WebSocket progress stream
- SQLite history persistence
- eval CLI
- Electron/React frontend
- MCP mock ops tools

Always report exact commands, observed results, failures, and skipped checks. Do not claim production readiness, real external integration, or high-concurrency support unless those behaviors were actually exercised.

## Baseline checks

From `f:\wdxm\2.企业工单系统`:

```powershell
python -m ruff check src tests
python -m pytest
```

If frontend files changed, from `f:\wdxm\2.企业工单系统\frontend`:

```powershell
npm run typecheck
npm test
```

These checks are not a substitute for runtime observation when product behavior changed.

## Backend API verification

Start the backend:

```powershell
cd "f:\wdxm\2.企业工单系统"
python -m uvicorn intelliticket_backend.main:app --host 127.0.0.1 --port 8000
```

Observe health:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

Exercise the real ticket processing route:

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

Confirm at minimum:

- response has `ticket_id` and `run_id`
- `data_mode` remains `mock`
- affected service is `payment-service`
- workflow trace includes intake, context retrieval, diagnosis, routing, and report
- evidence entries preserve `evidence_id` and source metadata
- no real Prometheus/Jira/Grafana/Feishu capability is claimed

## WebSocket verification

When WebSocket code or schemas changed, observe a live WebSocket flow against the running backend:

- connect to `ws://127.0.0.1:8000/api/v1/tickets/process/ws`
- send a `start` message with the sample ticket
- confirm event order: `started`, five `agent_progress` events, terminal `completed`
- confirm terminal result matches the REST processing contract
- confirm invalid or `real` mode inputs fail closed with structured errors when those paths changed
- confirm cancellation behavior is reported honestly as best-effort

Focused test support is available:

```powershell
python -m pytest tests/test_ticket_processing_ws.py
```

## SQLite history verification

After a completed, failed, or cancelled processing flow, query:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/tickets
Invoke-RestMethod http://127.0.0.1:8000/api/v1/tickets/<ticket_id>
```

Confirm:

- list shows the persisted ticket/run
- detail exposes `latest_run.status`
- completed runs have a full response
- failed/cancelled runs have `response: null` and structured `error`
- no fake historical row is returned when the database is empty

## Eval CLI verification

For eval, diagnosis, routing, report, or evidence behavior changes, run:

```powershell
python -m intelliticket_backend.eval_reporter --list-cases
python -m intelliticket_backend.eval_reporter --format text
```

If JSON output behavior changed, run:

```powershell
python -m intelliticket_backend.eval_reporter --format json
```

Confirm:

- expected cases are listed
- command exits successfully when all cases pass
- failures are explicit, not silently skipped
- report clearly says `data_mode: mock`
- evals still cover missing, stale, conflicting, mock/real, unknown-service, priority-boundary, and invalid-route behavior

## Frontend verification

The desktop app does not start the backend automatically. Start the backend first at `http://127.0.0.1:8000`.

From `f:\wdxm\2.企业工单系统\frontend`:

```powershell
npm run typecheck
npm test
npm run dev
```

Drive the actual UI when frontend behavior changed:

- submit the sample payment-service timeout ticket
- observe the final report
- observe Agent timeline/progress events
- confirm evidence is visible
- confirm the mock-data badge/label is visible
- confirm errors are understandable if backend is unavailable

Do not claim frontend behavior was verified from tests alone if UI behavior changed.

## MCP verification

For MCP changes, run focused tests:

```powershell
python -m pytest tests/test_mcp_server.py
```

Start the MCP server using the transport relevant to the change:

```powershell
python -m intelliticket_backend.mcp_server --transport stdio
```

or:

```powershell
python -m intelliticket_backend.mcp_server --transport streamable-http
```

Use an official MCP client or test harness to verify:

- initialize succeeds
- tools are discoverable
- `lookup_service_catalog` works for payment-service text
- invalid input returns structured `MCP_INVALID_INPUT`
- unknown service returns structured service-not-found error
- every returned record/evidence is marked `data_mode: "mock"`
- failures do not silently fall back to a different data source

If no official client/harness is available in the environment, say MCP runtime invocation was not fully observed instead of claiming it passed.

## Reporting format

End verification with:

- changed scope
- commands run
- runtime flows observed
- important response fields observed
- checks skipped and why
- failures and exact output
- unsupported claims that remain unverified

A stable report distinguishes passed, failed, blocked, and skipped observations. Do not hide skipped runtime surfaces behind a generic “tests passed”.
