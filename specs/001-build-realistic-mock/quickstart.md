# Quickstart: Realistic Mock Incident Data Generation

## Goal

Generate deterministic v0 mock incident bundles and validate evaluation-readiness contracts.

## Prerequisites

- Python 3.12+
- `uv`
- Repository initialized with Spec Kit

## 1) Generate one bundle

Example invocation:

```powershell
python -c "from rca.seed.mock_incident_generator import generate; generate(scenario='db_connection_pool_exhaustion', seed=42, time_anchor='2026-02-22T10:00:00Z')"
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

Runtime Brain scoring is deferred for this feature iteration.

Current v0 requirement is evaluation-readiness only:

- `ground_truth.json` exists for every bundle.
- Required label fields and threshold policy are present.
- Future Brain integration can consume this contract without schema changes.

Future hook placeholder:

```text
# Future integration point (not implemented in v0):
# brain.evaluate(bundle_path="tests/fixtures/mock_incidents/<bundle_id>")
```

Pass criteria:

- Metadata includes configurable threshold with default `0.70`.
- Bundle contract validates without Brain runtime dependencies.

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

## 5) Generate all scenarios (sweep)

```powershell
python -c "from rca.seed.mock_incident_generator import generate_all_scenarios; generate_all_scenarios(seed=42, time_anchor='2026-02-22T10:00:00Z')"
```

## 6) Run targeted tests

```powershell
pytest tests/unit/test_mock_fixture_utils.py tests/unit/test_mock_incident_generator.py tests/integration/test_mock_bundle_determinism.py
```

Optional full feature suite:

```powershell
pytest tests/unit tests/integration -k mock
```
