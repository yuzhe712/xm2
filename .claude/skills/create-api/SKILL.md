---
name: create-api
description: Design and implement validated REST, SSE, or WebSocket boundaries for the IntelliTicket system. Use when adding ticket endpoints, processing runs, schemas, streaming events, authentication, or integrations.
argument-hint: [resource or endpoint]
---

# Create API

Follow `CLAUDE.md`. Start with the contract and failure behavior, not a generic route template.

## Define the contract

Before implementation specify:

- method/path or stream transport;
- request, response, event, and error schemas;
- authentication, authorization, tenant ownership, and idempotency if applicable;
- mock/demo/real behavior and provenance fields;
- status codes, pagination, filtering, timeouts, and cancellation;
- which existing service implements the behavior.

Do not mount an endpoint if its service is unfinished. Never return fake success, `{}`, or `[]` as implementation placeholders.

## Typical MVP endpoints

Use actual repository conventions, but the MVP usually needs only:

- `POST /api/v1/tickets/process`: submit natural-language ticket text and receive the completed processing result.
- `GET /api/v1/tickets/{ticket_id}`: read a stored/in-memory ticket result only after persistence exists.
- `GET /api/v1/tickets/{ticket_id}/events` or WebSocket equivalent: stream Agent progress only after the synchronous flow works.
- `GET /api/v1/health`: health check.

Prefer one synchronous processing endpoint first. Add streaming only when the UI needs live Agent progress.

## Boundary validation

Validate applicable fields: ticket IDs, run IDs, service IDs, team IDs, incident IDs, SOP IDs, timestamps, timezones, service names, metric names, units, numeric ranges, nullability, pagination, filters, file type/size, source freshness, and LLM/external structured output.

Use repository conventions and modern built-in generics such as `list[ResponseModel]`. Keep route, schema, service, and persistence responsibilities separated according to actual project size.

## Streaming requirements

For SSE or WebSocket define and test:

- authentication before subscription if authentication exists;
- typed event schema with ticket ID, run ID, agent name, status, timestamp, evidence references, and terminal event;
- heartbeat and idle timeout;
- disconnect/cancellation cleanup;
- bounded queues or other backpressure behavior;
- reconnect/resume semantics and duplicate handling;
- structured error events.

Do not expose private chain-of-thought in progress events. Show auditable action summaries, observations, evidence, and concise decision reasons only.

## Ticket response fields

When returning diagnoses or recommendations, include the applicable provenance contract and `data_mode`. Required evidence failure must produce abstention or a structured error, not a plausible synthetic diagnosis.

## Tests and verification

Add OpenAPI/schema tests, invalid-boundary tests, service integration tests, mock/demo labeling, provenance retention, and streaming disconnect/terminal behavior if streaming exists. Launch the API and exercise the real endpoint before reporting it complete.
