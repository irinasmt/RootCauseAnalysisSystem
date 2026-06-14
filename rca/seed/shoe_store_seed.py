from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .mock_diff_generator import FileEntry, MockDiffBundle


ARCHITECTURE = {
    "system": "shoe-ordering-platform",
    "services": [
        "ui-web",
        "order-service",
        "payment-service",
        "inventory-service",
        "shipping-service",
        "notification-service",
    ],
    "external_dependencies": [
        "payment-gateway",
        "shipping-carrier-api",
    ],
    "external_dependency_labels": {
        "payment-gateway": {
            "dependency_type": "third_party_api",
            "ownership": "external_not_owned",
            "is_in_mesh_topology": True,
        },
        "shipping-carrier-api": {
            "dependency_type": "third_party_api",
            "ownership": "external_not_owned",
            "is_in_mesh_topology": True,
        },
    },
    "edges": [
        {"from": "ui-web", "to": "order-service", "type": "sync_http"},
        {"from": "order-service", "to": "payment-service", "type": "sync_http"},
        {"from": "payment-service", "to": "payment-gateway", "type": "sync_http"},
        {"from": "order-service", "to": "inventory-service", "type": "sync_http"},
        {"from": "order-service", "to": "shipping-service", "type": "sync_http"},
        {"from": "shipping-service", "to": "shipping-carrier-api", "type": "sync_http"},
        {"from": "order-service", "to": "notification-service", "type": "async_event"},
    ],
}


_PAYMENT_AFTER = '''\
"""Payment client used by order-service checkout flow."""
from __future__ import annotations

import os
import httpx

PAYMENT_GATEWAY_URL = os.getenv("PAYMENT_GATEWAY_URL", "https://gateway.payments.example")
PAYMENT_TIMEOUT_SECONDS = float(os.getenv("PAYMENT_TIMEOUT_SECONDS", "10"))
PAYMENT_MAX_RETRIES = int(os.getenv("PAYMENT_MAX_RETRIES", "2"))


class PaymentGatewayClient:
    def __init__(self, timeout: float = PAYMENT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout
        self._client = httpx.Client(timeout=self._timeout)

    def charge(self, amount: float, token: str) -> dict:
        response = self._client.post(
            f"{PAYMENT_GATEWAY_URL}/charge",
            json={"amount": amount, "token": token},
        )
        response.raise_for_status()
        return response.json()
'''


_PAYMENT_DIFF = '''\
--- a/src/payment_gateway_client.py
+++ b/src/payment_gateway_client.py
@@ -5,6 +5,6 @@
 import httpx

 PAYMENT_GATEWAY_URL = os.getenv("PAYMENT_GATEWAY_URL", "https://gateway.payments.example")
-PAYMENT_TIMEOUT_SECONDS = float(os.getenv("PAYMENT_TIMEOUT_SECONDS", "30"))
+PAYMENT_TIMEOUT_SECONDS = float(os.getenv("PAYMENT_TIMEOUT_SECONDS", "10"))
 PAYMENT_MAX_RETRIES = int(os.getenv("PAYMENT_MAX_RETRIES", "2"))
'''


_PAYMENT_CONFIG_AFTER = '''\
apiVersion: v1
kind: ConfigMap
metadata:
  name: payment-service-config
  namespace: production
data:
  PAYMENT_GATEWAY_URL: "https://gateway.payments.example"
  PAYMENT_TIMEOUT_SECONDS: "10"
  PAYMENT_MAX_RETRIES: "2"
'''


_PAYMENT_CONFIG_DIFF = '''\
--- a/k8s/payment-service-configmap.yaml
+++ b/k8s/payment-service-configmap.yaml
@@ -5,5 +5,5 @@
 data:
   PAYMENT_GATEWAY_URL: "https://gateway.payments.example"
-  PAYMENT_TIMEOUT_SECONDS: "30"
+  PAYMENT_TIMEOUT_SECONDS: "10"
   PAYMENT_MAX_RETRIES: "2"
'''


PAYMENT_TIMEOUT_TIGHTENING = MockDiffBundle(
    scenario_id="payment_timeout_tightening",
    description=(
        "Payment timeout reduced from 30s to 10s in payment-service; under peak load "
        "the gateway often responds slower than 10s, causing retries/timeouts and "
        "cascading order-service latency."
    ),
    service="payment-service",
    commit_sha="shoepay10to30",
    files={
        "src/payment_gateway_client.py": FileEntry(
            content=_PAYMENT_AFTER,
            diff=_PAYMENT_DIFF,
            language="python",
        ),
        "k8s/payment-service-configmap.yaml": FileEntry(
            content=_PAYMENT_CONFIG_AFTER,
            diff=_PAYMENT_CONFIG_DIFF,
            language="yaml",
        ),
    },
)


# ---------------------------------------------------------------------------
# order_fails_missing_db_column scenario
# ---------------------------------------------------------------------------

_ORDER_MODEL_AFTER = '''\
"""ORM model for the orders table."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Order:
    order_id: str
    customer_id: str
    total_amount: float
    status: str
    promo_code: Optional[str] = None  # added in migration 0012
'''

_ORDER_MODEL_DIFF = '''\
--- a/src/models/order.py
+++ b/src/models/order.py
@@ -9,6 +9,7 @@
 @dataclass
 class Order:
     order_id: str
     customer_id: str
     total_amount: float
     status: str
+    promo_code: Optional[str] = None  # added in migration 0012
'''

_ORDER_REPO_AFTER = '''\
"""Repository for persisting orders to PostgreSQL."""
from __future__ import annotations

import psycopg2


class OrderRepository:
    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def insert(self, order) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO orders (order_id, customer_id, total_amount, status, promo_code)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (order.order_id, order.customer_id, order.total_amount, order.status, order.promo_code),
            )
        self._conn.commit()
'''

_ORDER_REPO_DIFF = '''\
--- a/src/repositories/order_repository.py
+++ b/src/repositories/order_repository.py
@@ -13,7 +13,7 @@
             cur.execute(
                 """
-                INSERT INTO orders (order_id, customer_id, total_amount, status)
-                VALUES (%s, %s, %s, %s)
+                INSERT INTO orders (order_id, customer_id, total_amount, status, promo_code)
+                VALUES (%s, %s, %s, %s, %s)
                 """,
-                (order.order_id, order.customer_id, order.total_amount, order.status),
+                (order.order_id, order.customer_id, order.total_amount, order.status, order.promo_code),
             )
         self._conn.commit()
'''

_PROMO_MIGRATION_AFTER = '''\
-- Migration 0012: add promo_code column to orders table
-- Run with: psql $DATABASE_URL -f migrations/0012_add_promo_code.sql

ALTER TABLE orders ADD COLUMN promo_code VARCHAR(50);
'''

_PROMO_MIGRATION_DIFF = '''\
--- /dev/null
+++ b/migrations/0012_add_promo_code.sql
@@ -0,0 +1,4 @@
+-- Migration 0012: add promo_code column to orders table
+-- Run with: psql $DATABASE_URL -f migrations/0012_add_promo_code.sql
+
+ALTER TABLE orders ADD COLUMN promo_code VARCHAR(50);
'''

ORDER_MISSING_DB_COLUMN = MockDiffBundle(
    scenario_id="order_missing_db_column",
    description=(
        "order-service deployed with code referencing a new 'promo_code' column, "
        "but migration 0012_add_promo_code.sql was not applied; every order INSERT "
        "fails with 'column promo_code of relation orders does not exist'."
    ),
    service="order-service",
    commit_sha="ordmig0012",
    files={
        "src/models/order.py": FileEntry(
            content=_ORDER_MODEL_AFTER,
            diff=_ORDER_MODEL_DIFF,
            language="python",
        ),
        "src/repositories/order_repository.py": FileEntry(
            content=_ORDER_REPO_AFTER,
            diff=_ORDER_REPO_DIFF,
            language="python",
        ),
        "migrations/0012_add_promo_code.sql": FileEntry(
            content=_PROMO_MIGRATION_AFTER,
            diff=_PROMO_MIGRATION_DIFF,
            language="text",
        ),
    },
)


def _write_mock_diff_bundle(bundle: MockDiffBundle, out_dir: Path) -> None:
    files_dir = out_dir / "files"
    diffs_dir = out_dir / "diffs"
    files_dir.mkdir(parents=True, exist_ok=True)
    diffs_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    for rel_path, item in bundle.files.items():
        file_dest = files_dir / rel_path
        file_dest.parent.mkdir(parents=True, exist_ok=True)
        file_dest.write_text(item.content, encoding="utf-8")

        diff_dest = diffs_dir / f"{rel_path}.diff"
        diff_dest.parent.mkdir(parents=True, exist_ok=True)
        diff_dest.write_text(item.diff, encoding="utf-8")

        entries.append(
            {
                "path": rel_path,
                "language": item.language,
                "content_file": f"files/{rel_path}",
                "diff_file": f"diffs/{rel_path}.diff",
            }
        )

    manifest = {
        "scenario_id": bundle.scenario_id,
        "service": bundle.service,
        "commit_sha": bundle.commit_sha,
        "description": bundle.description,
        "files": entries,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _mesh_events(anchor: datetime) -> list[dict]:
    rows: list[dict] = []
    for i in range(30):
        ts = anchor + timedelta(minutes=i)
        incident = i >= 15

        # order -> payment degrades in incident window
        rows.append(
            {
                "ts": ts.isoformat(),
                "stream": "mesh",
                "service": "order-service",
                "upstream": "payment-service",
                "latency_ms": 680 if incident else 95,
                "retry_count": 5 if incident else 0,
                "response_code": 503 if incident else 200,
                "policy": "default",
                "correlation_id": f"corr-order-pay-{i:03d}",
            }
        )

        # payment -> gateway is the real failing edge
        rows.append(
            {
                "ts": ts.isoformat(),
                "stream": "mesh",
                "service": "payment-service",
                "upstream": "payment-gateway",
                "latency_ms": 920 if incident else 130,
                "retry_count": 6 if incident else 1,
                "response_code": 504 if incident else 200,
                "policy": "default",
                "correlation_id": f"corr-pay-gw-{i:03d}",
            }
        )
    return rows


def _txt_log_rows(anchor: datetime) -> dict[str, list[str]]:
    ui_rows: list[str] = []
    order_rows: list[str] = []
    payment_rows: list[str] = []
    shipping_rows: list[str] = []

    for i in range(30):
        ts = (anchor + timedelta(minutes=i)).isoformat()
        incident = i >= 15

        if incident:
            ui_rows.append(
                f"{ts} level=ERROR stream=ui route=/checkout message=checkout_timed_out correlation_id=ui-{i:03d}"
            )
            order_rows.append(
                f"{ts} level=ERROR stream=order route=/orders status=503 latency_ms=1300 upstream=payment-service upstream_status=504 message=checkout_request_failed correlation_id=ord-{i:03d}"
            )
            payment_rows.append(
                f"{ts} level=ERROR stream=payment route=/charge status=504 latency_ms=980 upstream=payment-gateway timeout_ms=10000 retries=2 message=upstream_request_timed_out correlation_id=pay-{i:03d}"
            )
            shipping_rows.append(
                f"{ts} level=WARN stream=shipping event=dispatch_pending reason=payment_not_confirmed correlation_id=ship-{i:03d}"
            )
        else:
            ui_rows.append(
                f"{ts} level=INFO stream=ui route=/checkout message=checkout_ok correlation_id=ui-{i:03d}"
            )
            order_rows.append(
                f"{ts} level=INFO stream=order route=/orders status=created latency_ms=180 correlation_id=ord-{i:03d}"
            )
            payment_rows.append(
                f"{ts} level=INFO stream=payment route=/charge status=authorized latency_ms=120 correlation_id=pay-{i:03d}"
            )
            shipping_rows.append(
                f"{ts} level=INFO stream=shipping event=label_created correlation_id=ship-{i:03d}"
            )

    return {
        "ui_events.log": ui_rows,
        "order_logs.log": order_rows,
        "payment_logs.log": payment_rows,
        "shipping_logs.log": shipping_rows,
    }


def generate_order_slow_due_to_payment(
    output_root: str | Path = "tests/fixtures/shoe_store",
    *,
    time_anchor: str | datetime = "2026-02-22T10:00:00+00:00",
) -> dict:
    root = Path(output_root)
    scenario_dir = root / "order_slow_due_to_payment"
    incident_dir = scenario_dir / "incident"
    diff_dir = scenario_dir / "diffs" / PAYMENT_TIMEOUT_TIGHTENING.scenario_id
    scenario_dir.mkdir(parents=True, exist_ok=True)
    incident_dir.mkdir(parents=True, exist_ok=True)

    if isinstance(time_anchor, str):
        anchor = datetime.fromisoformat(time_anchor)
    else:
        anchor = time_anchor
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=UTC)
    else:
        anchor = anchor.astimezone(UTC)

    (scenario_dir / "architecture.json").write_text(
        json.dumps(ARCHITECTURE, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    mesh_rows = _mesh_events(anchor)
    (incident_dir / "mesh_events.jsonl").write_text(
        "\n".join(json.dumps(r, separators=(",", ":"), sort_keys=True) for r in mesh_rows) + "\n",
        encoding="utf-8",
    )

    for name, rows in _txt_log_rows(anchor).items():
        (incident_dir / name).write_text("\n".join(rows) + "\n", encoding="utf-8")

    manifest = {
        "scenario_id": "order_slow_due_to_payment",
        "triggered_service": "order-service",
        "changed_services": ["payment-service"],
        "time_anchor": anchor.isoformat(),
        "incident_window_start": (anchor + timedelta(minutes=15)).isoformat(),
        "incident_window_end": (anchor + timedelta(minutes=30)).isoformat(),
        "artifacts": [
            "ui_events.log",
            "order_logs.log",
            "payment_logs.log",
            "shipping_logs.log",
            "mesh_events.jsonl",
        ],
        "diff_fixture": f"diffs/{PAYMENT_TIMEOUT_TIGHTENING.scenario_id}",
    }
    (incident_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ground_truth = {
        "scenario_id": "order_slow_due_to_payment",
        "trigger": "order_service_latency_spike",
        "root_cause": "payment_gateway_timeout_too_aggressive",
        "affected_service": "order-service",
        "changed_service": "payment-service",
        "failing_edge": "order-service->payment-service",
        "upstream_failing_edge": "payment-service->payment-gateway",
        "expected_first_signal": "mesh_latency_and_503_on_order_to_payment",
    }
    (incident_dir / "ground_truth.json").write_text(
        json.dumps(ground_truth, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    _write_mock_diff_bundle(PAYMENT_TIMEOUT_TIGHTENING, diff_dir)

    return {
        "scenario_dir": str(scenario_dir),
        "incident_dir": str(incident_dir),
        "diff_dir": str(diff_dir),
        "scenario_id": "order_slow_due_to_payment",
    }


def _mesh_events_missing_column(anchor: datetime) -> list[dict]:
    rows: list[dict] = []
    for i in range(30):
        ts = anchor + timedelta(minutes=i)
        incident = i >= 15

        # ui-web -> order-service: 500 as soon as DB INSERT fails on missing column
        rows.append(
            {
                "ts": ts.isoformat(),
                "stream": "mesh",
                "service": "ui-web",
                "upstream": "order-service",
                "latency_ms": 45 if incident else 90,
                "retry_count": 0,
                "response_code": 500 if incident else 200,
                "policy": "default",
                "correlation_id": f"corr-ui-ord-{i:03d}",
            }
        )

        # order-service -> inventory-service: silent during incident (order fails at DB before inventory check)
        if not incident:
            rows.append(
                {
                    "ts": ts.isoformat(),
                    "stream": "mesh",
                    "service": "order-service",
                    "upstream": "inventory-service",
                    "latency_ms": 55,
                    "retry_count": 0,
                    "response_code": 200,
                    "policy": "default",
                    "correlation_id": f"corr-ord-inv-{i:03d}",
                }
            )
    return rows


def _txt_log_rows_missing_column(anchor: datetime) -> dict[str, list[str]]:
    ui_rows: list[str] = []
    order_rows: list[str] = []

    for i in range(30):
        ts = (anchor + timedelta(minutes=i)).isoformat()
        incident = i >= 15

        if incident:
            ui_rows.append(
                f"{ts} level=ERROR stream=ui route=/checkout message=checkout_failed status=500 correlation_id=ui-{i:03d}"
            )
            order_rows.append(
                f"{ts} level=ERROR stream=order route=/orders status=500 message=db_insert_failed"
                f" pg_error=\"column promo_code of relation orders does not exist\""
                f" correlation_id=ord-{i:03d}"
            )
        else:
            ui_rows.append(
                f"{ts} level=INFO stream=ui route=/checkout message=checkout_ok correlation_id=ui-{i:03d}"
            )
            order_rows.append(
                f"{ts} level=INFO stream=order route=/orders status=created latency_ms=185 correlation_id=ord-{i:03d}"
            )

    return {
        "ui_events.log": ui_rows,
        "order_logs.log": order_rows,
    }


def generate_order_fails_missing_db_column(
    output_root: str | Path = "tests/fixtures/shoe_store",
    *,
    time_anchor: str | datetime = "2026-03-15T10:00:00+00:00",
) -> dict:
    root = Path(output_root)
    scenario_dir = root / "order_fails_missing_db_column"
    incident_dir = scenario_dir / "incident"
    diff_dir = scenario_dir / "diffs" / ORDER_MISSING_DB_COLUMN.scenario_id
    scenario_dir.mkdir(parents=True, exist_ok=True)
    incident_dir.mkdir(parents=True, exist_ok=True)

    if isinstance(time_anchor, str):
        anchor = datetime.fromisoformat(time_anchor)
    else:
        anchor = time_anchor
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=UTC)
    else:
        anchor = anchor.astimezone(UTC)

    (scenario_dir / "architecture.json").write_text(
        json.dumps(ARCHITECTURE, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    mesh_rows = _mesh_events_missing_column(anchor)
    (incident_dir / "mesh_events.jsonl").write_text(
        "\n".join(json.dumps(r, separators=(",", ":"), sort_keys=True) for r in mesh_rows) + "\n",
        encoding="utf-8",
    )

    for name, rows in _txt_log_rows_missing_column(anchor).items():
        (incident_dir / name).write_text("\n".join(rows) + "\n", encoding="utf-8")

    manifest = {
        "scenario_id": "order_fails_missing_db_column",
        "triggered_service": "order-service",
        "changed_services": ["order-service"],
        "time_anchor": anchor.isoformat(),
        "incident_window_start": (anchor + timedelta(minutes=15)).isoformat(),
        "incident_window_end": (anchor + timedelta(minutes=30)).isoformat(),
        "artifacts": [
            "ui_events.log",
            "order_logs.log",
            "mesh_events.jsonl",
        ],
        "diff_fixture": f"diffs/{ORDER_MISSING_DB_COLUMN.scenario_id}",
    }
    (incident_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    ground_truth = {
        "scenario_id": "order_fails_missing_db_column",
        "trigger": "order_service_deployment_without_migration",
        "root_cause": "missing_db_migration_promo_code_column",
        "affected_service": "order-service",
        "changed_service": "order-service",
        "failing_edge": "ui-web->order-service",
        "upstream_failing_edge": "order-service->orders-db",
        "expected_first_signal": "order_service_500_on_db_insert_missing_column",
    }
    (incident_dir / "ground_truth.json").write_text(
        json.dumps(ground_truth, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    _write_mock_diff_bundle(ORDER_MISSING_DB_COLUMN, diff_dir)

    return {
        "scenario_dir": str(scenario_dir),
        "incident_dir": str(incident_dir),
        "diff_dir": str(diff_dir),
        "scenario_id": "order_fails_missing_db_column",
    }


def _main() -> None:
    result = generate_order_slow_due_to_payment()
    print("Generated shoe-store seed scenario:")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _main()
