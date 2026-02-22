# Research: Realistic Mock Incident Data Generation

## Decision 1: File-based artifact storage for v0

- Decision: Use fixture artifacts in repository storage (`tests/fixtures/mock_incidents/`) instead of database persistence.
- Rationale: Deterministic fixture replay, easier diffing in CI, simpler developer workflow, and direct alignment with RCA fixture testing.
- Alternatives considered:
  - Postgres metadata store: rejected for v0 due to added infrastructure and migration overhead.
  - Hybrid DB + files: rejected for v0 due to split source-of-truth complexity.

## Decision 2: Mixed stream format policy

- Decision: Emit TXT logs for UI/API/DB/K8s and JSONL for mesh stream.
- Rationale: Matches explicit product direction; preserves realistic text-log ingestion while keeping mesh telemetry structured for query/filter use cases.
- Alternatives considered:
  - All JSONL: rejected because it diverges from desired realism for non-mesh logs.
  - All TXT: rejected because it weakens mesh telemetry expressiveness and downstream parsing reliability.

## Decision 3: Determinism contract

- Decision: With same scenario + seed, stream artifacts must be byte-identical; only bundle-level metadata timestamps may vary (`created_at`, run timestamp).
- Rationale: Enables robust regression tests without brittle failures from run-time metadata.
- Alternatives considered:
  - Full byte identity including timestamps: rejected as too brittle for practical runs.
  - Metric-level equivalence only: rejected as too weak for fixture regression guarantees.

## Decision 4: v0 scenario scope

- Decision: Fix v0 to exactly five scenarios:
  1. `normal_load`
  2. `db_connection_pool_exhaustion`
  3. `slow_query_regression`
  4. `bad_api_rollout`
  5. `pod_oom_restart_loop`
- Rationale: Stable coverage baseline, predictable contracts, and manageable implementation scope.
- Alternatives considered:
  - Open-ended scenario list: rejected due to planning/task volatility.
  - Three-scenario MVP: rejected because it under-covers likely RCA patterns.

## Decision 5: RCA pass threshold policy

- Decision: Threshold is configurable with global default `0.70` in v0.
- Rationale: Balances immediate baseline consistency with future tuning flexibility.
- Alternatives considered:
  - Hard-coded 0.70: rejected due to inability to calibrate quickly.
  - Per-scenario thresholds only: rejected for unnecessary v0 complexity.

## Decision 6: Contract-first validation approach

- Decision: Validate artifact completeness and schema/field invariants before scoring RCA quality.
- Rationale: Ensures evaluation failures are interpretable (contract issue vs reasoning issue).
- Alternatives considered:
  - Direct RCA scoring without contract validation: rejected due to opaque failure modes.
