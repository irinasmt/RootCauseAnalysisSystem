# Testing Strategy

This project needs tests that prevent two failure modes:
1) **incorrect blame** (false attribution)
2) **ungrounded claims** (missing evidence references)

## Test layers

### 1) Contract tests (schemas)

Goal: every node output and API response validates against its schema.

What to test
- Pydantic schema validation for:
  - `ApprovedIncident`
  - `EvidenceBundle`
  - `HypothesisSet`
  - `CriticReview`
  - `RCAReport`

Acceptance criteria
- Invalid shapes are rejected deterministically.
- Required evidence references are enforced.

### 2) Deterministic fixture tests (golden)

Goal: same inputs → same outputs (in deterministic mode), so regressions are obvious.

Approach
- Maintain a small library of fixtures:
  - regression-after-deploy
  - traffic spike / capacity
  - dependency slowdown
  - crashloop/config drift
- For each fixture, assert:
  - hypotheses ordering (top 1–3)
  - confidence bands (not exact floats; use ranges)
  - presence of evidence references per claim
  - report section structure

### 3) Critic “anti-hallucination” tests

Goal: ensure the Critic blocks ungrounded or contradictory conclusions.

Cases to include
- Regression starts **before** deployment → Critic must reject “deploy caused it”
- Accused service has normal error rate → Critic must downgrade
- Clear dependency regression exists → Critic must suggest dependency path

### 4) Integration tests (stores)

Goal: validate persistence and retrieval round-trips.

Approach
- Run with local databases only when needed.
- Assert that:
  - incidents persist
  - evidence artifacts persist
  - reports persist
  - UI-facing queries can rehydrate a full incident view

### 5) Performance and cost tests (lightweight)

Goal: prevent runaway investigation loops and expensive payloads.

Approach
- Budget assertions:
  - max iterations per incident
  - max commits sent to expensive summarization
  - max total retrieved chunks

## Test data management

- Fixtures should be human-readable JSON (or YAML) and checked into the repo.
- Every fixture must include:
  - anomaly window
  - deploy event(s)
  - metrics summary
  - candidate commits
  - expected output assertions

## Continuous verification (quality gates)

- No report can be considered “valid” unless it passes:
  - schema validation
  - evidence reference checks
  - confidence threshold policy
