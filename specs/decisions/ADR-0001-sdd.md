# ADR-0001: Adopt Spec-Driven Development (SDD)

- Status: Accepted
- Date: 2026-02-19

## Context

This project is building an RCA system with multiple stores, multiple integrations, and an LLM-driven reasoning graph. Without strict contracts, it’s easy for behavior and data shapes to drift, creating brittle integrations and untestable reasoning.

## Decision

We will use **Spec-Driven Development (SDD)**.

- Specs are written/updated *before* implementation work.
- Specs live in `specs/` and are versioned alongside code.
- Acceptance criteria in specs are represented in tests.
- A PR that changes behavior/contracts must update the relevant spec(s).

## Consequences

- Positive:
  - Clear contracts for data, APIs, and Brain behavior
  - Easier reviews and fewer regressions
  - Tests trace directly to acceptance criteria
- Negative:
  - Slightly more upfront writing for changes
  - Requires discipline to keep specs current

## Alternatives considered

- “Code first” with docs later: rejected due to drift risk.
- Tickets-only requirements: rejected because specs need to be co-located with code and reviewable in PRs.
