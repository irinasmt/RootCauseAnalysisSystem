---
name: new-fixture
description: Scaffold a new RCA fixture for a production failure scenario.
---

Scaffold a complete, deterministic RCA fixture for the following production failure:

**Failure description:** ${input:failure_description:Describe the failure — e.g. "payment-service is timing out, causing orders to fail"}

Use the canonical shoe_store service architecture (`ui-web`, `order-service`, `payment-service`, `inventory-service`, `shipping-service`, `notification-service`).

## Fixture Layout

All shoe_store fixtures live under `tests/fixtures/shoe_store/<scenario_slug>/` and follow this exact structure:

```
tests/fixtures/shoe_store/<scenario_slug>/
├── architecture.json                    # service mesh topology (reuse ARCHITECTURE from shoe_store_seed.py)
├── incident/
│   ├── manifest.json                    # scenario metadata, incident window, artifact list
│   ├── ground_truth.json                # root cause, failing edges, expected first signal
│   ├── mesh_events.jsonl                # one JSON object per line, sorted keys
│   ├── ui_events.log                    # stream=ui log lines
│   ├── <service>_logs.log ...           # one log file per relevant service (e.g. order_logs.log)
└── diffs/
    └── <diff_bundle_name>/
        ├── manifest.json                # diff bundle metadata: scenario_id, service, commit_sha, description, files[]
        ├── files/
        │   └── <path>                   # full file content after the change
        └── diffs/
            └── <path>.diff             # unified diff (--- a/... +++ b/...)
```

**Key rules:**

- Stream logs and `manifest.json` / `ground_truth.json` always go in `incident/`, not in the scenario root.
- Log filenames are service-specific (e.g. `order_logs.log`, `payment_logs.log`), not generic names like `api_logs.log` or `db_events.log`.
- `mesh_events.jsonl` uses sorted-key compact JSON, one object per line.
- `architecture.json` is the full service mesh topology — import and reuse `ARCHITECTURE` from `rca/seed/shoe_store_seed.py`.

## manifest.json schema (inside `incident/`)

```json
{
  "scenario_id": "<scenario_slug>",
  "triggered_service": "<service that shows the first user-visible error>",
  "changed_services": ["<service whose code/config was deployed>"],
  "time_anchor": "<ISO8601 UTC>",
  "incident_window_start": "<ISO8601 UTC>",
  "incident_window_end": "<ISO8601 UTC>",
  "artifacts": [
    "ui_events.log",
    "<service>_logs.log",
    "...",
    "mesh_events.jsonl"
  ],
  "diff_fixture": "diffs/<diff_bundle_name>"
}
```

## ground_truth.json schema (inside `incident/`)

```json
{
  "scenario_id": "<scenario_slug>",
  "trigger": "<what triggered the incident>",
  "root_cause": "<underlying root cause label>",
  "affected_service": "<service experiencing the degradation>",
  "changed_service": "<service where the bad change was deployed>",
  "failing_edge": "<from-service>-><to-service>",
  "upstream_failing_edge": "<from-service>-><upstream>",
  "expected_first_signal": "<signal label>"
}
```

## diff bundle manifest.json schema (inside `diffs/<bundle_name>/`)

```json
{
  "scenario_id": "<bundle_name>",
  "service": "<service-name>",
  "commit_sha": "<short sha or mnemonic>",
  "description": "<human-readable description of the change>",
  "files": [
    {
      "path": "src/some_file.py",
      "language": "python",
      "content_file": "files/src/some_file.py",
      "diff_file": "diffs/src/some_file.py.diff"
    }
  ]
}
```

## Implementation

**Do not** place static files only. Add a `generate_<scenario_slug>()` function in `rca/seed/shoe_store_seed.py` following the same pattern as `generate_order_slow_due_to_payment()`. This function must:

1. Accept `output_root` and `time_anchor` parameters.
2. Write all files deterministically (same inputs → byte-identical output).
3. Import and reuse `ARCHITECTURE` for `architecture.json`.
4. Return a dict with `scenario_dir`, `incident_dir`, `diff_dir`, `scenario_id`.

After adding the generator function, re-generate the static fixture files by running:

```bash
python -c "from rca.seed.shoe_store_seed import generate_<scenario_slug>; import json; print(json.dumps(generate_<scenario_slug>(), indent=2))"
```

Then add tests in `tests/unit/test_shoe_store_seed.py` — at minimum:

- All expected artifact files exist.
- `mesh_events.jsonl` contains the key failing edge rows.
- Log files contain the expected error tokens during the incident window.

After creating all files, run:

```bash
pytest tests/unit/test_shoe_store_seed.py -q
```

Report the fixture path and how to run the full pipeline with:

```bash
python run_fixture_pipeline.py tests/fixtures/shoe_store/<scenario_slug>
```
