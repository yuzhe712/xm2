---
name: create-orchestrator
description: Create or revise an IntelliTicket ticket-processing orchestrator with explicit reducers, validated routing, bounded execution, conflict handling, provenance, and abstention. Use for multi-agent coordination.
argument-hint: [workflow or agents]
---

# Create Orchestrator

Apply `CLAUDE.md`. Do not add a heavyweight orchestrator until at least two components require dynamic coordination. For the MVP, prefer a simple explicit workflow unless dynamic routing is genuinely needed.

## Design state before nodes

Define serializable state fields and reducers first. Prefer append-only immutable records such as `list[AgentRun]` containing agent name, ticket ID, run ID, status, result, provenance, evidence, timestamps, and errors.

- Parallel nodes must not overwrite a shared mutable dictionary.
- Derive keyed views during synthesis instead of mutating shared maps.
- DB sessions, HTTP clients, locks, services, and callbacks stay outside graph state.

## Recommended MVP workflow

Start with the fixed ops-alert chain unless requirements demand dynamic routing:

```text
ticket_intake_agent
  → context_retrieval_agent
  → diagnosis_agent
  → routing_agent
  → report_agent
```

Each step should append an auditable `AgentRun` record and pass only validated, serializable outputs to the next step.

## Routing

- Prefer deterministic routing for clear cases; use model routing only where classification or next-step selection is ambiguous.
- Validate model-selected routes against a known-node allowlist.
- Define invalid-route behavior, maximum graph steps, per-node timeout, retry policy, and deterministic termination.
- Keep provider/model parameters configurable and capability-aware; do not hardcode temperature or unsupported sampling settings.

## Synthesis / reporting

- Preserve every source and evidence reference.
- Separate facts, derived conclusions, assumptions, partial results, unknowns, and recommendations.
- Detect incompatible conclusions and surface the conflict.
- Re-query or verify only when a defined policy allows it.
- Abstain when required evidence is missing, stale, or irreconcilable; never manufacture consensus.
- The final report must include ticket type, priority, affected service, candidate causes, recommended actions, assigned team, confidence if justified, and Agent execution trace.

## Persistence

When using a checkpointer or database, define ticket/run identity, tenant/team isolation if applicable, retention, cleanup, resume behavior, and schema evolution. Never rely on process-global mutable state for persisted results.

## Tests

Cover reducer behavior under parallel updates if parallelism exists, valid and invalid routes, iteration limit, node timeout, partial failure, checkpoint/resume if implemented, conflicting evidence, insufficient evidence, provenance retention, and mock/demo labeling.

Run one realistic multi-node flow using the payment-service timeout example and inspect the final state before reporting completion.
