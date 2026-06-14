---
description: Scaffold a complete, runnable RCA fixture from a plain-English production failure description.
tools:
  - read_file
  - create_file
  - run_in_terminal
  - file_search
  - grep_search
---

## User Input

```text
$ARGUMENTS
```

You **MUST** read the user's failure description carefully before proceeding. If no description is provided, ask: **"Describe the production failure scenario — which service failed, what the symptom was, and what you suspect caused it."**

## Goal

Turn a plain-English production failure description into a complete, deterministic, runnable RCA fixture under `tests/fixtures/shoe_store/<scenario_slug>/`. The output must pass `pytest tests/unit/ -q` without any external dependencies.

## Constraints

- Use only services from the canonical shoe_store architecture (`ui-web`, `order-service`, `payment-service`, `inventory-service`, `shipping-service`, `notification-service`, `payment-gateway`, `shipping-carrier-api`).
- All generated event data must be **deterministic**: derive every timestamp from `time_anchor + timedelta(seconds=offset)`, not from `datetime.now()`.
- Checksums in `manifest.json` must be SHA-256 of exact file content.
- Do NOT modify existing fixtures — only create new ones.
- Follow the `rca-fixture-schema` skill for all schemas and rules.

## Execution Steps

### Step 1 — Understand the Failure

Read the user's description and extract:
- **Trigger service**: which service exhibited the first symptom
- **Root cause**: the underlying change or failure (config change, bad deploy, external API degradation, resource exhaustion, etc.)
- **Blast radius**: which services were affected downstream
- **Signal type**: what kind of event surfaced it first (timeout, error spike, latency increase, crash, etc.)

If any of these are ambiguous, ask one targeted clarifying question before proceeding.

### Step 2 — Read Existing Fixture Patterns

Read these files to understand the existing patterns before generating anything:

1. Read `tests/fixtures/shoe_store/order_slow_due_to_payment/` — list its files and read `manifest.json` and `ground_truth.json`
2. Read `rca/seed/shoe_store_seed.py` — understand the architecture and service dependency edges
3. Read `rca/seed/mock_incident_generator.py` lines 1–100 — understand `ScenarioDefinition`, `StreamArtifact`, `ExpectedOutputLabelSet`
4. Read `tests/fixtures/mock_incidents/mock-14f0be6ccd38/manifest.json` — reference for bundle_id format

### Step 3 — Derive Fixture Parameters

Compute:
- `scenario_slug` = `snake_case` of the failure description (e.g. `payment_timeout_cascade`)
- `scenario_id` = same as `scenario_slug`
- `bundle_id` = `"mock-"` + first 12 chars of `sha1((scenario_id + "42").encode()).hexdigest()`
- `seed` = `42`
- `time_anchor` = `"2026-03-15T10:00:00+00:00"`
- `duration_minutes` = `30` (adjust up to `60` if blast radius spans 3+ services)
- `threshold` = `0.70`

### Step 4 — Generate Stream Files

Create `tests/fixtures/shoe_store/<scenario_slug>/` and write all five stream files.

**Event generation rules:**
- All timestamps: `time_anchor + timedelta(seconds=offset)` where `offset` increments from 0
- Minimum 20 events per stream, maximum 40
- Events must tell a coherent story:
  - First 5 events: normal operations across all services
  - Events 6–15: degradation begins in the trigger service, errors start propagating
  - Events 16–25: blast radius fully visible — downstream services reporting errors
  - Events 26–end: stabilization or escalation

**`mesh_events.jsonl`** — one JSON object per line:
```
{"ts": "<ISO8601>", "from": "<service>", "to": "<service>", "status": "ok|error|degraded", "latency_ms": <int>, "error_code": "<string or null>"}
```

**`api_logs.log`**, **`ui_events.log`**, **`db_events.log`**, **`k8s_events.log`** — one line per event:
```
[<ISO8601>] LEVEL <service> <message>
```

### Step 5 — Compute Checksums and Write manifest.json

After writing all five stream files, compute SHA-256 checksums:
```python
import hashlib
checksum = hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
```

Write `manifest.json` using the schema from the `rca-fixture-schema` skill.

### Step 6 — Write ground_truth.json

Write `ground_truth.json` using the schema from the `rca-fixture-schema` skill. Set:
- `confidence_target_min` = `0.65`
- `confidence_target_max` = `0.95`
- `threshold_default` = `0.70`
- `threshold_override` = `null`

### Step 7 — Validate

Run the unit tests to confirm the fixture is structurally valid:

```bash
pytest tests/unit/test_mock_fixture_utils.py tests/unit/test_mock_incident_generator.py -q
```

If tests fail, diagnose and fix the fixture before reporting success.

### Step 8 — Report

Tell the user:
1. The path to the new fixture directory
2. The `bundle_id` and `scenario_id`
3. How to run it end-to-end: `python run_brain.py tests/fixtures/shoe_store/<scenario_slug>/`
4. Which services appear in the blast radius and where Brain should focus its investigation
