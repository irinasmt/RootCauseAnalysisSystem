import json
from pathlib import Path

from rca.seed.mock_incident_generator import (
    DEFAULT_SCENARIOS,
    compare_deterministic_runs,
    generate,
    generate_all_scenarios,
)


def test_scenario_coverage_exact_five_set(tmp_path: Path):
    results = generate_all_scenarios(
        seed=42,
        output_root=tmp_path,
        time_anchor="2026-02-22T10:00:00Z",
    )
    assert len(results) == 5
    assert {result["scenario"] for result in results} == set(DEFAULT_SCENARIOS.keys())
    for result in results:
        bundle_dir = tmp_path / result["bundle_id"]
        assert (bundle_dir / "manifest.json").exists()
        assert (bundle_dir / "ground_truth.json").exists()


def test_deterministic_stream_artifact_equality_across_reruns(tmp_path: Path):
    run_a_root = tmp_path / "run_a"
    run_b_root = tmp_path / "run_b"
    result_a = generate(
        scenario="db_connection_pool_exhaustion",
        seed=42,
        output_root=run_a_root,
        time_anchor="2026-02-22T10:00:00Z",
    )
    result_b = generate(
        scenario="db_connection_pool_exhaustion",
        seed=42,
        output_root=run_b_root,
        time_anchor="2026-02-22T10:00:00Z",
    )
    comparison = compare_deterministic_runs(
        first_bundle_dir=run_a_root / result_a["bundle_id"],
        second_bundle_dir=run_b_root / result_b["bundle_id"],
    )
    assert comparison["stream_artifacts_byte_identical"] is True
    assert comparison["stream_diffs"] == []


def test_allowed_metadata_timestamp_variance_only(tmp_path: Path):
    run_a_root = tmp_path / "run_a"
    run_b_root = tmp_path / "run_b"
    result_a = generate(
        scenario="slow_query_regression",
        seed=31,
        output_root=run_a_root,
        time_anchor="2026-02-22T10:00:00Z",
    )
    result_b = generate(
        scenario="slow_query_regression",
        seed=31,
        output_root=run_b_root,
        time_anchor="2026-02-22T10:00:00Z",
    )

    manifest_b_path = run_b_root / result_b["bundle_id"] / "manifest.json"
    manifest_b = json.loads(manifest_b_path.read_text(encoding="utf-8"))
    manifest_b["created_at"] = "2026-02-22T10:00:05+00:00"
    manifest_b_path.write_text(json.dumps(manifest_b, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    comparison = compare_deterministic_runs(
        first_bundle_dir=run_a_root / result_a["bundle_id"],
        second_bundle_dir=run_b_root / result_b["bundle_id"],
    )
    assert comparison["pass"] is True
    assert "created_at" in comparison["allowed_metadata_variation"]
    assert comparison["illegal_metadata_variation"] == []


def test_edge_case_clock_skew_tolerated_for_metadata_only(tmp_path: Path):
    result = generate(
        scenario="normal_load",
        seed=5,
        output_root=tmp_path,
        time_anchor="2026-02-22T10:00:00Z",
    )
    bundle_dir = tmp_path / result["bundle_id"]
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["run_timestamp"] = "2026-02-22T09:59:59+00:00"
    (bundle_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert "run_timestamp" in json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))


def test_edge_case_partial_outage_is_generatable(tmp_path: Path):
    result = generate(
        scenario="pod_oom_restart_loop",
        seed=77,
        output_root=tmp_path,
        time_anchor="2026-02-22T10:00:00Z",
    )
    bundle_dir = tmp_path / result["bundle_id"]
    assert (bundle_dir / "k8s_events.log").exists()
    assert (bundle_dir / "api_logs.log").exists()


def test_edge_case_retry_storm_includes_mesh_stream(tmp_path: Path):
    result = generate(
        scenario="bad_api_rollout",
        seed=99,
        output_root=tmp_path,
        time_anchor="2026-02-22T10:00:00Z",
    )
    lines = (tmp_path / result["bundle_id"] / "mesh_events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) > 0
    assert all('"retry_count"' in line for line in lines)


def test_edge_case_mesh_policy_change_signal_present(tmp_path: Path):
    result = generate(
        scenario="db_connection_pool_exhaustion",
        seed=101,
        output_root=tmp_path,
        time_anchor="2026-02-22T10:00:00Z",
    )
    first_line = (tmp_path / result["bundle_id"] / "mesh_events.jsonl").read_text(encoding="utf-8").splitlines()[0]
    payload = json.loads(first_line)
    assert payload["stream"] == "mesh"
    assert "service" in payload and "upstream" in payload
