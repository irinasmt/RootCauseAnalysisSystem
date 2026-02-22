# Quickstart: Realistic Mock Incident Data Generation

## Goal

Generate deterministic v0 mock incident bundles and validate RCA evaluation behavior.

## Prerequisites

- Python 3.12+
- `uv`
- Repository initialized with Spec Kit

## 1) Generate one bundle

Example invocation (placeholder command path):

```powershell
# Use the project generator entrypoint once implemented
# python -m rca.seed.mock_incident_generator --scenario db_connection_pool_exhaustion --seed 42 --time-anchor 2026-02-22T10:00:00Z
```

Expected output directory:

`tests/fixtures/mock_incidents/<bundle_id>/`

Expected files:

- `manifest.json`
- `ground_truth.json`
- `ui_events.log`
- `api_logs.log`
- `db_events.log`
- `k8s_events.log`
- `mesh_events.jsonl`

## 2) Validate determinism

Run generation twice with same scenario/seed/time anchor.

Pass criteria:

- Stream artifacts (`*.log`, `mesh_events.jsonl`) are byte-identical.
- Only `created_at` / run timestamp fields may differ in bundle-level metadata.

## 3) Run RCA evaluation

Evaluate Brain output against `ground_truth.json`.

Pass criteria:

- Evaluation uses configurable threshold with default `0.70`.
- Result clearly reports `pass`/`fail` and comparison rationale.

## 4) Validate v0 scenario coverage

Generate one bundle for each required scenario:

- `normal_load`
- `db_connection_pool_exhaustion`
- `slow_query_regression`
- `bad_api_rollout`
- `pod_oom_restart_loop`

Pass criteria:

- All five bundles generated successfully.
- Each bundle satisfies artifact contract and expected-output presence.
