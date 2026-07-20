---
name: create-agent
description: Decide whether an autonomous ticket-processing agent is justified, then create or revise it with bounded execution, evidence provenance, and tests. Use for intake, context retrieval, diagnosis, routing, report, or synthesis agents.
argument-hint: [agent responsibility]
---

# Create Agent

Follow `CLAUDE.md`, especially ticket evidence, mock-data, failure, and orchestration rules.

## First decide whether this should be an Agent

Use an Agent only when the component must dynamically choose tools, plan several uncertain steps, reconcile evidence, or adapt its next action to observations. Use a normal service, rule engine, or workflow for deterministic parsing, fixed mock-data lookup, simple priority rules, and fixed API sequences.

State the decision before implementing it.

## Recommended MVP agents

- `ticket_intake_agent`: classify ticket, extract service, symptoms, metrics, and priority.
- `context_retrieval_agent`: retrieve mock deployments, metrics, dependencies, similar incidents, and SOP docs.
- `diagnosis_agent`: generate candidate root causes with evidence and uncertainty.
- `routing_agent`: recommend owning team, next actions, escalation, and SOP references.
- `report_agent`: produce the final user-facing report and auditable execution summary.

Do not create all agents just because they are listed. Create only the one needed by the current vertical slice.

## Define the contract

Before code, define:

- typed input and output;
- required versus optional ticket evidence;
- provenance fields and freshness rules;
- failure and abstention behavior;
- allowed tools, mock-data sources, and actions;
- iteration, tool-call, timeout, retry, and concurrency limits;
- whether data mode is `mock`, `demo`, or `real`.

## Implementation rules

- Inherit the repository's actual Agent base class; do not create a second framework.
- Keep DB sessions, clients, locks, and service instances outside serializable state.
- Validate model-selected tools and arguments against an allowlist and schema.
- Record auditable actions, observations, evidence IDs, timing, and result status.
- Do not persist or expose private chain-of-thought. A concise decision reason is acceptable.
- Preserve structured tool errors and distinguish partial results from valid recommendations.
- Evidence required for a root-cause diagnosis or routing recommendation must not fail open.
- Register the Agent once through the existing registry mechanism.
- Do not hardcode a final demo conclusion in the Agent; derive it from input plus mock/real evidence.

## Internal envelope / A2A naming rule

Typed `TaskRequest`/`TaskResult` classes or `{from,to,ticket_id,message_type,payload}` messages are internal task envelopes, not A2A compliance. Call them A2A only when the implementation pins an official A2A specification or SDK and passes protocol-level conformance tests.

## Tests

Cover at minimum:

- valid ticket evidence and successful result;
- missing or stale required evidence and abstention;
- optional context source failure and partial result;
- timeout and iteration limit;
- malformed model output or invalid tool arguments;
- explicit mock/demo-mode labeling;
- provenance preserved through the final report.

Run the focused tests and one real ticket execution path before reporting completion.
