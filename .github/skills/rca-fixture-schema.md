---
description: >
  Schema reference and determinism rules for RCA fixtures under
  tests/fixtures/shoe_store/<scenario_slug>/. Apply this skill whenever
  creating or validating a shoe_store fixture bundle.
---

# RCA Fixture Schema

## Canonical Shoe Store Services

Only use services from this set. Any service outside it is invalid.

| Name | Role |
|---|---|
| `ui-web` | Browser front-end |
| `order-service` | Order placement and lifecycle |
| `payment-service` | Payment processing |
| `inventory-service` | Stock reservation |
| `shipping-service` | Shipment fulfilment |
| `notification-service` | Email / SMS notifications |
| `payment-gateway` | External payment network (third-party) |
| `shipping-carrier-api` | External shipping carrier (third-party) |

---

## Directory Layout

```
tests/fixtures/shoe_store/<scenario_slug>/
├── ui_events.log
├── api_logs.log
├── db_events.log
├── k8s_events.log
├── mesh_events.jsonl
├── manifest.json
└── ground_truth.json
```

All seven files are required. Do not add extra files or subdirectories at this level.

---

## Determinism Rules

These rules make fixtures byte-stable across runs.

1. **Fixed time anchor** — choose a concrete UTC datetime and pin it:
   ```
   time_anchor = "2026-03-15T10:00:00+00:00"
   ```
2. **Offset-based timestamps** — every timestamp is derived as:
   ```
   time_anchor + timedelta(seconds=offset)
   ```
   Never call `datetime.now()` or `time.time()` inside fixture generation.
3. **Sequential correlation IDs** — use zero-padded counters:
   ```
   correlation_id=ord-000, ord-001, ord-002, …
   ```
4. **Fixed seed** — always `seed = 42`.
5. **Deterministic `bundle_id`** — derive with:
   ```python
   import hashlib
   bundle_id = "mock-" + hashlib.sha1((scenario_id + "42").encode()).hexdigest()[:12]
   ```
6. **SHA-256 checksums** — compute after writing the file, never before:
   ```python
   import hashlib
   checksum = hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
   ```

---

## `manifest.json` Schema

Satisfies `rca.seed.mock_incident_generator.IncidentBundle`.

```json
{
  "bundle_id": "mock-<12-hex-chars>",
  "scenario_id": "<scenario_slug>",
  "scenario": "<scenario_slug>",
  "seed": 42,
  "time_anchor": "<ISO8601 UTC>",
  "duration_minutes": 30,
  "resolution_seconds": 60,
  "created_at": "<ISO8601 UTC — fixed, not datetime.now()>",
  "threshold": 0.7,
  "artifacts": [
    {
      "bundle_id": "<bundle_id>",
      "stream_name": "ui",
      "format": "txt",
      "file_name": "ui_events.log",
      "record_count": <int ≥ 1>,
      "checksum": "<sha256 hex>"
    },
    {
      "bundle_id": "<bundle_id>",
      "stream_name": "api",
      "format": "txt",
      "file_name": "api_logs.log",
      "record_count": <int ≥ 1>,
      "checksum": "<sha256 hex>"
    },
    {
      "bundle_id": "<bundle_id>",
      "stream_name": "db",
      "format": "txt",
      "file_name": "db_events.log",
      "record_count": <int ≥ 1>,
      "checksum": "<sha256 hex>"
    },
    {
      "bundle_id": "<bundle_id>",
      "stream_name": "k8s",
      "format": "txt",
      "file_name": "k8s_events.log",
      "record_count": <int ≥ 1>,
      "checksum": "<sha256 hex>"
    },
    {
      "bundle_id": "<bundle_id>",
      "stream_name": "mesh",
      "format": "jsonl",
      "file_name": "mesh_events.jsonl",
      "record_count": <int ≥ 1>,
      "checksum": "<sha256 hex>"
    }
  ]
}
```

**Rules:**
- `bundle_id` must start with `"mock-"` and contain exactly 17 characters.
- `duration_minutes` ≥ 15.
- `resolution_seconds` ≥ 1.
- All five streams (`ui`, `api`, `db`, `k8s`, `mesh`) must be present in `artifacts`.
- `record_count` must exactly equal the number of lines / JSON objects written.
- Checksums must be computed **after** writing the file.

---

## `ground_truth.json` Schema

Satisfies `rca.seed.mock_incident_generator.ExpectedOutputLabelSet`.
Required keys: `bundle_id`, `scenario_id`, `root_cause`, `trigger`, `blast_radius`, `expected_first_signal`, `confidence_target_min`, `confidence_target_max`, `threshold_default`, `threshold_override`.

```json
{
  "bundle_id": "<bundle_id>",
  "scenario_id": "<scenario_slug>",
  "root_cause": "<snake_case label — e.g. payment_gateway_timeout_too_aggressive>",
  "trigger": "<snake_case label — e.g. order_service_latency_spike>",
  "blast_radius": "<comma-separated canonical service names>",
  "expected_first_signal": "<snake_case label — e.g. mesh_latency_and_503_on_order_to_payment>",
  "confidence_target_min": 0.65,
  "confidence_target_max": 0.95,
  "threshold_default": 0.70,
  "threshold_override": null
}
```

**Rules:**
- `confidence_target_max` ≥ `confidence_target_min`.
- Both confidence values must be in [0.0, 1.0].
- `threshold_override` is `null` unless the scenario requires a non-default threshold.
- All label fields use `snake_case`.

---

## Stream File Formats

### `.log` files (ui, api, db, k8s) — plain text, one line per event

```
<ISO8601> level=<LEVEL> stream=<name> <key>=<value> [<key>=<value> …]
```

Example:
```
2026-03-15T10:00:00+00:00 level=INFO stream=order route=/orders status=created latency_ms=180 correlation_id=ord-000
2026-03-15T10:15:00+00:00 level=ERROR stream=order route=/orders status=503 latency_ms=1300 message=checkout_request_failed correlation_id=ord-015
```

**Common `stream` values:**
- `ui`: `stream=ui` — browser-side page events and click actions
- `api`: `stream=api` — service-to-service API calls
- `db`: `stream=db` — database query observations
- `k8s`: `stream=k8s` — pod restarts, OOMKills, ConfigMap updates

**Common key-value pairs by stream:**

| Stream | Typical keys |
|---|---|
| `ui` | `route`, `status`, `latency_ms`, `correlation_id` |
| `api` | `route`, `status`, `latency_ms`, `correlation_id` |
| `db` | `query`, `duration_ms`, `rows`, `correlation_id` |
| `k8s` | `resource`, `event`, `namespace`, `pod`, `reason` |

---

### `mesh_events.jsonl` — JSONL, one JSON object per line

```json
{"ts": "<ISO8601>", "from": "<service>", "to": "<service>", "status": "ok|error|degraded", "latency_ms": <int>, "error_code": "<string or null>", "correlation_id": "<string>", "stream": "mesh"}
```

All field names are required. `error_code` is `null` for `ok` events.

Example (normal → degraded transition):
```jsonl
{"ts":"2026-03-15T10:00:00+00:00","from":"order-service","to":"payment-service","status":"ok","latency_ms":95,"error_code":null,"correlation_id":"corr-order-pay-000","stream":"mesh"}
{"ts":"2026-03-15T10:15:00+00:00","from":"order-service","to":"payment-service","status":"error","latency_ms":1300,"error_code":"upstream_timeout","correlation_id":"corr-order-pay-015","stream":"mesh"}
```

---

## Event Narrative Structure

Every stream must tell a coherent 3-phase story:

| Phase | Event range | What to show |
|---|---|---|
| **Normal** | Events 1–5 | Healthy traffic across all relevant services; baseline latencies |
| **Degradation** | Events 6–15 | Trigger service shows first signal (latency spike, error spike, or crash); other services unaffected |
| **Blast radius** | Events 16–end | Downstream services report errors propagating from the trigger; mesh errors visible on affected edges |

**Minimum / maximum events per stream:** 20–40 events.

---

## `record_count` Verification

After writing each file, count lines before writing `manifest.json`:

```python
# For .log files:
record_count = sum(1 for line in Path(file_path).read_text().splitlines() if line.strip())

# For .jsonl files:
record_count = sum(1 for line in Path(file_path).read_text().splitlines() if line.strip())
```

These counts must exactly match the `record_count` fields in `manifest.json`.
