# Seed Data Architecture (Shoe Store)

This folder now includes a dedicated seed path for a realistic **shoe ordering platform** used to test cross-service RCA behavior.

## Reference architecture

Core services:

- `ui-web` — customer storefront (browse shoes, checkout)
- `order-service` — owns order lifecycle and orchestration
- `payment-service` — authorization/capture/refund
- `inventory-service` — stock reservation and release
- `shipping-service` — shipment label + carrier booking
- `notification-service` — order confirmation / status updates

External dependencies:

- `payment-gateway` (3rd party)
- `shipping-carrier-api` (3rd party)

Primary synchronous request path:

`ui-web -> order-service -> payment-service -> payment-gateway`

Secondary path:

`order-service -> inventory-service`
`order-service -> shipping-service -> shipping-carrier-api`

Async side effects:

`order-service -> notification-service`

## First failure scenario

Scenario ID: `order_slow_due_to_payment`

- Triggered symptom: **order-service latency spike**
- Actual cause: **payment-service cannot process payments reliably**
- Blast radius: checkout flow slows/fails; shipping creation is delayed

This is intentionally cross-team:

- impacted service: `order-service`
- changed service: `payment-service`

## Seed outputs generated for scenario #1

`tests/fixtures/shoe_store/order_slow_due_to_payment/`

- `architecture.json` — service and edge model
- `incident/` — runtime evidence
  - `mesh_events.jsonl`
  - `ui_events.log`
  - `order_logs.log`
  - `payment_logs.log`
  - `shipping_logs.log`
  - `manifest.json`
  - `ground_truth.json`
- `diffs/payment_timeout_tightening/` — code/config change evidence in mock-diff format
  - `manifest.json`
  - `files/...`
  - `diffs/...`

## How to regenerate

Run:

`python -m rca.seed.shoe_store_seed`

The generator is deterministic and safe to re-run.

## Why this seed set exists

The existing `mock_incident_generator` scenarios remain unchanged for backwards compatibility.

This shoe-store seed path is focused on validating:

1. service-mesh dependency traversal,
2. cross-service suspect expansion,
3. graph-backed code evidence retrieval from the true changed service,
4. end-to-end Brain behavior when "affected service != changed service".
