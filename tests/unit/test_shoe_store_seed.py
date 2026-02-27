import json
from pathlib import Path

from rca.seed.shoe_store_seed import ARCHITECTURE, generate_order_slow_due_to_payment


def test_architecture_has_core_services():
    services = set(ARCHITECTURE["services"])
    assert "order-service" in services
    assert "payment-service" in services
    assert "shipping-service" in services
    assert "ui-web" in services


def test_generate_order_slow_due_to_payment_writes_expected_artifacts(tmp_path: Path):
    result = generate_order_slow_due_to_payment(output_root=tmp_path)

    scenario_dir = Path(result["scenario_dir"])
    incident_dir = scenario_dir / "incident"
    diff_dir = Path(result["diff_dir"])

    assert (scenario_dir / "architecture.json").exists()
    assert (incident_dir / "manifest.json").exists()
    assert (incident_dir / "ground_truth.json").exists()
    assert (incident_dir / "mesh_events.jsonl").exists()
    assert (incident_dir / "order_logs.log").exists()
    assert (incident_dir / "payment_logs.log").exists()
    assert (incident_dir / "shipping_logs.log").exists()
    assert (incident_dir / "ui_events.log").exists()

    assert (diff_dir / "manifest.json").exists()
    assert (diff_dir / "files" / "src" / "payment_gateway_client.py").exists()
    assert (diff_dir / "diffs" / "src" / "payment_gateway_client.py.diff").exists()


def test_mesh_fixture_contains_order_to_payment_and_payment_to_gateway(tmp_path: Path):
    result = generate_order_slow_due_to_payment(output_root=tmp_path)
    mesh_path = Path(result["incident_dir"]) / "mesh_events.jsonl"
    rows = [json.loads(line) for line in mesh_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert any(r["service"] == "order-service" and r["upstream"] == "payment-service" for r in rows)
    assert any(r["service"] == "payment-service" and r["upstream"] == "payment-gateway" for r in rows)


def test_order_logs_do_not_use_synthetic_error_token(tmp_path: Path):
    result = generate_order_slow_due_to_payment(output_root=tmp_path)
    order_log = Path(result["incident_dir"]) / "order_logs.log"
    text = order_log.read_text(encoding="utf-8")
    assert "payment_dependency_timeout" not in text
