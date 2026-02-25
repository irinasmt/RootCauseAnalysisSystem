import json
from pathlib import Path

import pytest

from rca.seed.mock_incident_generator import (
    ALL_STREAMS,
    DEFAULT_SCENARIOS,
    STREAM_FILE_NAMES,
    ExpectedOutputLabelSet,
    ScenarioDefinition,
    generate,
    validate_ground_truth_payload,
)


def test_scenario_definition_requires_all_streams():
    with pytest.raises(ValueError):
        ScenarioDefinition(
            scenario_id="x",
            display_name="X",
            trigger="x",
            root_cause_label="x",
            symptom_propagation=["x"],
            noise_profile_defaults={"low": 0.1},
            required_streams=["ui", "api"],
        )


def test_expected_output_label_set_validates_confidence_range():
    with pytest.raises(ValueError):
        ExpectedOutputLabelSet(
            bundle_id="b",
            scenario_id="s",
            root_cause="r",
            trigger="t",
            blast_radius="br",
            expected_first_signal="api",
            confidence_target_min=0.9,
            confidence_target_max=0.7,
        )


def test_invalid_scenario_raises_error(tmp_path: Path):
    with pytest.raises(ValueError, match="INVALID_SCENARIO"):
        generate(scenario="unknown", seed=1, output_root=tmp_path, time_anchor="2026-02-22T10:00:00Z")


def test_invalid_threshold_raises_error(tmp_path: Path):
    with pytest.raises(ValueError, match="INVALID_PARAMETER"):
        generate(
            scenario="normal_load",
            seed=1,
            output_root=tmp_path,
            threshold=1.5,
            time_anchor="2026-02-22T10:00:00Z",
        )


def test_complete_artifact_set_generation(tmp_path: Path):
    response = generate(
        scenario="db_connection_pool_exhaustion",
        seed=42,
        output_root=tmp_path,
        time_anchor="2026-02-22T10:00:00Z",
    )
    bundle_dir = tmp_path / response["bundle_id"]
    assert bundle_dir.exists()
    expected_files = {
        "manifest.json",
        "ground_truth.json",
        "ui_events.log",
        "api_logs.log",
        "db_events.log",
        "k8s_events.log",
        "mesh_events.jsonl",
    }
    assert expected_files == {path.name for path in bundle_dir.iterdir() if path.is_file()}


def test_exactly_one_ground_truth_per_bundle(tmp_path: Path):
    response = generate(
        scenario="normal_load",
        seed=7,
        output_root=tmp_path,
        time_anchor="2026-02-22T10:00:00Z",
    )
    bundle_dir = tmp_path / response["bundle_id"]
    matches = list(bundle_dir.glob("ground_truth.json"))
    assert len(matches) == 1


def test_ground_truth_required_fields(tmp_path: Path):
    response = generate(
        scenario="slow_query_regression",
        seed=9,
        output_root=tmp_path,
        time_anchor="2026-02-22T10:00:00Z",
    )
    payload = json.loads((tmp_path / response["bundle_id"] / "ground_truth.json").read_text(encoding="utf-8"))
    assert validate_ground_truth_payload(payload) is True


def test_threshold_policy_defaults_and_override(tmp_path: Path):
    response_default = generate(
        scenario="bad_api_rollout",
        seed=10,
        output_root=tmp_path,
        time_anchor="2026-02-22T10:00:00Z",
    )
    default_payload = json.loads((tmp_path / response_default["bundle_id"] / "ground_truth.json").read_text(encoding="utf-8"))
    assert default_payload["threshold_default"] == pytest.approx(0.70)
    assert default_payload["threshold_override"] is None

    response_override = generate(
        scenario="bad_api_rollout",
        seed=11,
        output_root=tmp_path,
        threshold=0.82,
        time_anchor="2026-02-22T10:00:00Z",
    )
    override_payload = json.loads((tmp_path / response_override["bundle_id"] / "ground_truth.json").read_text(encoding="utf-8"))
    assert override_payload["threshold_override"] == pytest.approx(0.82)


def test_contract_alignment_output_paths_and_naming(tmp_path: Path):
    response = generate(
        scenario="pod_oom_restart_loop",
        seed=21,
        output_root=tmp_path,
        time_anchor="2026-02-22T10:00:00Z",
    )
    artifacts = [Path(path) for path in response["artifacts"]]
    bundle_dir = tmp_path / response["bundle_id"]
    assert all(path.parent == bundle_dir for path in artifacts)
    assert (bundle_dir / "manifest.json").exists()
    assert (bundle_dir / "ground_truth.json").exists()
    for stream_name in ALL_STREAMS:
        assert (bundle_dir / STREAM_FILE_NAMES[stream_name]).exists()


def test_fixed_scenario_set_is_exactly_five():
    assert set(DEFAULT_SCENARIOS.keys()) == {
        "normal_load",
        "db_connection_pool_exhaustion",
        "slow_query_regression",
        "bad_api_rollout",
        "pod_oom_restart_loop",
    }
    assert len(DEFAULT_SCENARIOS) == 5


def test_db_pool_exhaustion_emits_failure_signals(tmp_path: Path):
    response = generate(
        scenario="db_connection_pool_exhaustion",
        seed=42,
        output_root=tmp_path,
        time_anchor="2026-02-22T10:00:00Z",
    )
    bundle_dir = tmp_path / response["bundle_id"]
    api_text = (bundle_dir / "api_logs.log").read_text(encoding="utf-8")
    db_text = (bundle_dir / "db_events.log").read_text(encoding="utf-8")
    assert "error=db_pool_exhausted" in api_text
    assert "event=pool_exhausted" in db_text
