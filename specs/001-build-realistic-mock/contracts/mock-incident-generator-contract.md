# Contract: Mock Incident Generator (v0)

## Scope

Contract for generating deterministic incident bundles and evaluation-ready metadata. Runtime Brain scoring integration is deferred for this feature iteration.

## Operation

`mock_incident_generator.generate`

## Request

```json
{
  "scenario": "db_connection_pool_exhaustion",
  "seed": 42,
  "duration_minutes": 30,
  "resolution_seconds": 60,
  "noise_profile": "medium",
  "threshold": 0.7,
  "time_anchor": "2026-02-22T10:00:00Z"
}
```

### Request constraints

- `scenario` MUST be one of:
  - `normal_load`
  - `db_connection_pool_exhaustion`
  - `slow_query_regression`
  - `bad_api_rollout`
  - `pod_oom_restart_loop`
- `seed` MUST be an integer.
- `threshold` is optional; default `0.70`.

## Response

```json
{
  "bundle_id": "mock-20260222-0001",
  "scenario": "db_connection_pool_exhaustion",
  "seed": 42,
  "artifacts": [
    "tests/fixtures/mock_incidents/mock-20260222-0001/manifest.json",
    "tests/fixtures/mock_incidents/mock-20260222-0001/ground_truth.json",
    "tests/fixtures/mock_incidents/mock-20260222-0001/ui_events.log",
    "tests/fixtures/mock_incidents/mock-20260222-0001/api_logs.log",
    "tests/fixtures/mock_incidents/mock-20260222-0001/db_events.log",
    "tests/fixtures/mock_incidents/mock-20260222-0001/k8s_events.log",
    "tests/fixtures/mock_incidents/mock-20260222-0001/mesh_events.jsonl"
  ],
  "determinism": {
    "stream_artifacts_byte_identical": true,
    "allowed_metadata_variation": ["created_at", "run_timestamp"]
  }
}
```

## Invariants

- Exactly one `ground_truth.json` per bundle.
- Non-mesh streams MUST be `.log` (TXT).
- Mesh stream MUST be `.jsonl`.
- Same `scenario + seed + time_anchor` MUST produce byte-identical stream artifacts.

## Error codes

- `INVALID_SCENARIO`
- `INVALID_PARAMETER`
- `INVALID_OUTPUT_FORMAT`
- `GENERATION_FAILED`
