---
name: design-decision
description: Structured architecture decision-making framework for IntelliTicket. Compare alternatives, evaluate tradeoffs, and produce recommendations. Use before major design choices, technology selection, or when the user asks for方案设计、技术选型、架构决策.
argument-hint: decision topic
---

# Design Decision — 方案推演与决策

Apply the behavioral rules in `CLAUDE.md` §0.1–0.4 throughout. This skill adds structured decision-making, not permission to skip simpler alternatives.

## Phase 1 — Information alignment

Before proposing solutions, evaluate completeness:

1. Restate the core goal in one sentence.
2. Identify missing dimensions: 核心目标、技术约束、MVP 范围、数据来源、性能指标、交付时间。
3. If any critical dimension is missing, **stop and ask** with a numbered list. Do not guess.
4. If the user cannot answer immediately, offer 1–2 reasonable assumptions and sketch the direction each implies, so the user can pick or correct.

## Phase 2 — Design options

Produce 2–3 **meaningfully different** approaches. They must differ on at least one substantive axis: desktop vs web, simple workflow vs LangGraph, mock data vs real integration, local JSON vs SQLite, synchronous API vs streaming progress, simplicity vs capability.

Each option:
- One-paragraph summary.
- Key components / data flow.
- Why it was included (what scenario it fits).

Do not inflate the count — if only two approaches are genuinely different, present two.

## Phase 3 — Evaluation

For each option, list concrete pros and cons tied to the project's actual constraints (from `CLAUDE.md` §2–§12).

Produce a comparison table:

| Dimension | Option A | Option B | Weight / rationale |
|---|---|---|---|
| alignment with IntelliTicket MVP | | | |
| simplicity (CLAUDE.md §0.2) | | | |
| ticket evidence & provenance | | | |
| mock/demo/real separation | | | |
| failure behavior | | | |
| agent necessity | | | |
| desktop app demonstrability | | | |
| testability & verification | | | |
| implementation cost | | | |

Add project-specific rows when the decision touches additional constraints.

## Phase 4 — Recommendation

- State the recommended option and the decisive factor.
- Name what would change the recommendation (e.g. “if real-time Agent progress is required in the first demo, SSE/WebSocket becomes part of MVP”).
- Describe the first concrete step and how to verify it succeeded.

## Interaction rules

- 宁缺毋滥: if critical parameters are missing, ask before designing. A guess that skips a hard constraint wastes more time than one clarifying question.
- 分层追问: rank questions by impact; answering the top two should be enough to narrow the field.
- 量化优先: use concrete measures (ms, MB, token count, request rate) wherever possible.
- After the decision is made, record it: what was chosen, why, what was rejected, and under what conditions the rejected option would become correct.
