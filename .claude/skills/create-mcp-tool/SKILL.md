---
name: create-mcp-tool
description: Create or revise an MCP server, client, tool, prompt, or resource using the current official MCP SDK, validated schemas, provenance, and protocol tests. Use for external ticketing, monitoring, incident, or SOP integrations.
argument-hint: [tool or domain]
---

# Create MCP Tool

Follow `CLAUDE.md`. MCP is a real protocol, not a label for arbitrary JSON-RPC or subprocess wrappers.

## Before implementation

1. Inspect the installed language, package manager, MCP dependencies, server entry points, and test setup.
2. Determine whether the capability should be an MCP tool, resource, or prompt.
3. Confirm the current official MCP SDK and transport from authoritative documentation; pin the selected version in project dependencies.
4. Define the ticket/ops domain service separately from protocol transport.
5. Confirm whether the target system is real or still a mock/demo adapter.

## Architecture

- Domain service: monitoring/ticketing/SOP/database/calculation logic, callable and testable without MCP.
- MCP adapter: thin registration, schema validation, context extraction, result/error mapping.
- Client/integration: use the official client or test harness for initialization, discovery, invocation, and shutdown.

Do not manually parse stdin/stdout JSON and call it MCP. Do not automatically switch from a failed direct call to a semantically different subprocess, provider, or mock/demo data source.

## Candidate integrations

Introduce MCP only when it is actually needed for a real integration, such as:

- Prometheus/Grafana metric lookup;
- Jira/Feishu ticket creation or status lookup;
- incident-history search;
- SOP/document retrieval;
- service catalog or deployment-record lookup.

The MVP can use direct local JSON/SQLite services instead of MCP.

## Tool contract

Define:

- prescriptive name and description, including when the tool should be called;
- strict input and output schemas;
- authentication and tenant/team boundary if applicable;
- timeout, rate limit, retry, idempotency, and cancellation behavior;
- stable structured errors;
- `evidence_id`, `source_type`, `source_id`, source name, retrieval time, service, metric name, unit, quality, confidence method, and `data_mode` when applicable.

Validate all model-provided arguments at the boundary. Retries apply only to transient, idempotent calls.

## Verification

- Unit-test the transport-independent domain service.
- Use an official MCP client/test harness for initialize, list/discover, successful call, invalid input, tool error, timeout, and clean shutdown.
- Verify real data does not silently become mock/demo data when the provider fails.
- Run the server and perform one end-to-end invocation before claiming MCP support.

Stop if current official SDK details cannot be verified; do not invent API signatures from memory.
