from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
import random
from typing import Literal

from pydantic import BaseModel, Field, field_validator


NON_MESH_STREAMS: tuple[str, ...] = ("ui", "api", "db", "k8s")
ALL_STREAMS: tuple[str, ...] = (*NON_MESH_STREAMS, "mesh")
STREAM_FILE_NAMES = {
    "ui": "ui_events.log",
    "api": "api_logs.log",
    "db": "db_events.log",
    "k8s": "k8s_events.log",
    "mesh": "mesh_events.jsonl",
}
STREAM_FORMATS = {
    "ui": "txt",
    "api": "txt",
    "db": "txt",
    "k8s": "txt",
    "mesh": "jsonl",
}
REQUIRED_GROUND_TRUTH_KEYS = {
    "bundle_id",
    "scenario_id",
    "root_cause",
    "trigger",
    "blast_radius",
    "expected_first_signal",
    "confidence_target_min",
    "confidence_target_max",
    "threshold_default",
    "threshold_override",
}


class ScenarioDefinition(BaseModel):
    scenario_id: str
    display_name: str
    trigger: str
    root_cause_label: str
    symptom_propagation: list[str]
    noise_profile_defaults: dict[str, float]
    required_streams: list[Literal["ui", "api", "db", "k8s", "mesh"]]

    @field_validator("required_streams")
    @classmethod
    def _validate_required_streams(cls, value: list[str]) -> list[str]:
        if sorted(value) != sorted(ALL_STREAMS):
            raise ValueError("required_streams must include ui, api, db, k8s, mesh")
        return value


class StreamArtifact(BaseModel):
    bundle_id: str
    stream_name: Literal["ui", "api", "db", "k8s", "mesh"]
    format: Literal["txt", "jsonl"]
    file_name: str
    record_count: int = Field(ge=1)
    checksum: str


class ExpectedOutputLabelSet(BaseModel):
    bundle_id: str
    scenario_id: str
    root_cause: str
    trigger: str
    blast_radius: str
    expected_first_signal: str
    confidence_target_min: float = Field(ge=0.0, le=1.0)
    confidence_target_max: float = Field(ge=0.0, le=1.0)
    threshold_default: float = Field(ge=0.0, le=1.0, default=0.70)
    threshold_override: float | None = Field(ge=0.0, le=1.0, default=None)

    @field_validator("confidence_target_max")
    @classmethod
    def _validate_range(cls, value: float, info):
        if info.data.get("confidence_target_min") is not None and value < info.data["confidence_target_min"]:
            raise ValueError("confidence_target_max must be >= confidence_target_min")
        return value


class IncidentBundle(BaseModel):
    bundle_id: str
    scenario_id: str
    seed: int
    time_anchor: datetime
    duration_minutes: int = Field(ge=15)
    resolution_seconds: int = Field(ge=1)
    created_at: datetime
    artifacts_path: str
    stream_artifacts: list[StreamArtifact]


@dataclass(frozen=True)
class ScenarioTemplate:
    trigger: str
    root_cause: str
    blast_radius: str
    expected_first_signal: str
    symptom_propagation: tuple[str, ...]


DEFAULT_SCENARIOS: dict[str, ScenarioTemplate] = {
    "normal_load": ScenarioTemplate(
        trigger="none",
        root_cause="baseline_stable",
        blast_radius="none",
        expected_first_signal="none",
        symptom_propagation=("steady_rps", "stable_latency", "no_alerts"),
    ),
    "db_connection_pool_exhaustion": ScenarioTemplate(
        trigger="traffic_spike",
        root_cause="db_pool_limit",
        blast_radius="api_and_ui",
        expected_first_signal="api_error_rate",
        symptom_propagation=("api_timeout", "db_wait_queue", "k8s_probe_failures"),
    ),
    "slow_query_regression": ScenarioTemplate(
        trigger="query_plan_change",
        root_cause="missing_index",
        blast_radius="api_and_db",
        expected_first_signal="db_latency",
        symptom_propagation=("db_cpu_rise", "api_tail_latency", "ui_slow_render"),
    ),
    "bad_api_rollout": ScenarioTemplate(
        trigger="deployment_rollout",
        root_cause="unhandled_null_path",
        blast_radius="api",
        expected_first_signal="api_5xx",
        symptom_propagation=("api_5xx_spike", "mesh_retries", "ui_error_banner"),
    ),
    "pod_oom_restart_loop": ScenarioTemplate(
        trigger="memory_leak",
        root_cause="pod_memory_exhaustion",
        blast_radius="api_and_mesh",
        expected_first_signal="k8s_restarts",
        symptom_propagation=("k8s_oomkill", "mesh_reset", "api_unavailable"),
    ),
}


def _require_supported_scenario(scenario: str) -> ScenarioTemplate:
    if scenario not in DEFAULT_SCENARIOS:
        raise ValueError("INVALID_SCENARIO")
    return DEFAULT_SCENARIOS[scenario]


def _parse_time_anchor(time_anchor: str | datetime | None) -> datetime:
    if isinstance(time_anchor, datetime):
        parsed = time_anchor
    elif isinstance(time_anchor, str):
        parsed = datetime.fromisoformat(time_anchor.replace("Z", "+00:00"))
    else:
        parsed = datetime.now(tz=UTC).replace(microsecond=0)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _bundle_id_for(scenario: str, seed: int, time_anchor: datetime) -> str:
    digest = hashlib.sha256(f"{scenario}|{seed}|{time_anchor.isoformat()}".encode("utf-8")).hexdigest()[:12]
    return f"mock-{digest}"


def _format_guardrails() -> None:
    for stream_name in NON_MESH_STREAMS:
        if STREAM_FORMATS[stream_name] != "txt":
            raise ValueError("INVALID_OUTPUT_FORMAT")
    if STREAM_FORMATS["mesh"] != "jsonl":
        raise ValueError("INVALID_OUTPUT_FORMAT")


def _scenario_definition(scenario_id: str) -> ScenarioDefinition:
    template = _require_supported_scenario(scenario_id)
    return ScenarioDefinition(
        scenario_id=scenario_id,
        display_name=scenario_id.replace("_", " ").title(),
        trigger=template.trigger,
        root_cause_label=template.root_cause,
        symptom_propagation=list(template.symptom_propagation),
        noise_profile_defaults={"low": 0.05, "medium": 0.12, "high": 0.2},
        required_streams=list(ALL_STREAMS),
    )


def _stream_line(stream_name: str, at: datetime, scenario: str, randomizer: random.Random, is_incident_window: bool) -> str:
    correlation_id = f"corr-{scenario[:6]}-{randomizer.randint(1000, 9999)}"

    if scenario == "normal_load":
        is_incident_window = False

    if stream_name == "ui":
        if is_incident_window and scenario in {"db_connection_pool_exhaustion", "bad_api_rollout", "pod_oom_restart_loop"}:
            return (
                f"{at.isoformat()} level=ERROR stream=ui event=error_banner_shown error=backend_failure "
                f"correlation_id={correlation_id}"
            )
        return f"{at.isoformat()} level=INFO stream=ui event=user_action correlation_id={correlation_id}"

    if stream_name == "api":
        if is_incident_window and scenario == "db_connection_pool_exhaustion":
            return (
                f"{at.isoformat()} level=ERROR stream=api route=/orders status=503 latency_ms={850 + randomizer.randint(0, 400)} "
                f"error=db_pool_exhausted correlation_id={correlation_id}"
            )
        if is_incident_window and scenario == "slow_query_regression":
            return (
                f"{at.isoformat()} level=WARN stream=api route=/orders status=200 latency_ms={600 + randomizer.randint(0, 300)} "
                f"warning=downstream_query_slow correlation_id={correlation_id}"
            )
        if is_incident_window and scenario == "bad_api_rollout":
            return (
                f"{at.isoformat()} level=ERROR stream=api route=/orders status={500 + randomizer.randint(0, 2)} latency_ms={220 + randomizer.randint(0, 200)} "
                f"error=unhandled_null_path correlation_id={correlation_id}"
            )
        if is_incident_window and scenario == "pod_oom_restart_loop":
            return (
                f"{at.isoformat()} level=ERROR stream=api route=/orders status=503 latency_ms={500 + randomizer.randint(0, 250)} "
                f"error=pod_unavailable correlation_id={correlation_id}"
            )
        return (
            f"{at.isoformat()} level=INFO stream=api route=/orders status={200 + randomizer.randint(0, 1)} "
            f"latency_ms={120 + randomizer.randint(0, 20)} correlation_id={correlation_id}"
        )

    if stream_name == "db":
        if is_incident_window and scenario == "db_connection_pool_exhaustion":
            return (
                f"{at.isoformat()} level=ERROR stream=db event=pool_exhausted pool_in_use=100 pool_max=100 wait_ms={1200 + randomizer.randint(0, 1200)} "
                f"correlation_id={correlation_id}"
            )
        if is_incident_window and scenario == "slow_query_regression":
            return (
                f"{at.isoformat()} level=WARN stream=db query=SELECT/*regressed*/ latency_ms={450 + randomizer.randint(0, 900)} "
                f"rows_scanned={50000 + randomizer.randint(0, 20000)} correlation_id={correlation_id}"
            )
        if is_incident_window and scenario == "pod_oom_restart_loop":
            return (
                f"{at.isoformat()} level=WARN stream=db query=SELECT latency_ms={80 + randomizer.randint(0, 80)} "
                f"warning=upstream_connection_resets correlation_id={correlation_id}"
            )
        return (
            f"{at.isoformat()} level=INFO stream=db query=SELECT latency_ms={15 + randomizer.randint(0, 10)} "
            f"correlation_id={correlation_id}"
        )

    if stream_name == "k8s":
        if is_incident_window and scenario == "pod_oom_restart_loop":
            return (
                f"{at.isoformat()} level=ERROR stream=k8s pod=api-{randomizer.randint(1, 3)} event=oom_killed restart_count={1 + randomizer.randint(1, 6)} "
                f"correlation_id={correlation_id}"
            )
        if is_incident_window and scenario == "bad_api_rollout":
            return (
                f"{at.isoformat()} level=WARN stream=k8s pod=api-{randomizer.randint(1, 3)} event=rollout_regression correlation_id={correlation_id}"
            )
        if is_incident_window and scenario == "db_connection_pool_exhaustion":
            return (
                f"{at.isoformat()} level=WARN stream=k8s pod=api-{randomizer.randint(1, 3)} event=probe_timeout correlation_id={correlation_id}"
            )
        return (
            f"{at.isoformat()} level=INFO stream=k8s pod=api-{randomizer.randint(1, 3)} "
            f"event=healthcheck_ok correlation_id={correlation_id}"
        )

    if is_incident_window and scenario == "db_connection_pool_exhaustion":
        return json.dumps(
            {
                "ts": at.isoformat(),
                "stream": "mesh",
                "service": "api",
                "upstream": "db",
                "latency_ms": 300 + randomizer.randint(0, 300),
                "retry_count": 4 + randomizer.randint(0, 3),
                "response_code": 503,
                "policy": "default",
                "correlation_id": correlation_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    if is_incident_window and scenario == "bad_api_rollout":
        return json.dumps(
            {
                "ts": at.isoformat(),
                "stream": "mesh",
                "service": "api",
                "upstream": "db",
                "latency_ms": 180 + randomizer.randint(0, 180),
                "retry_count": 3 + randomizer.randint(0, 2),
                "response_code": 500,
                "policy": "canary",
                "correlation_id": correlation_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    if is_incident_window and scenario == "pod_oom_restart_loop":
        return json.dumps(
            {
                "ts": at.isoformat(),
                "stream": "mesh",
                "service": "api",
                "upstream": "db",
                "latency_ms": 220 + randomizer.randint(0, 220),
                "retry_count": 5 + randomizer.randint(0, 2),
                "response_code": 503,
                "policy": "default",
                "correlation_id": correlation_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    if is_incident_window and scenario == "slow_query_regression":
        return json.dumps(
            {
                "ts": at.isoformat(),
                "stream": "mesh",
                "service": "api",
                "upstream": "db",
                "latency_ms": 240 + randomizer.randint(0, 220),
                "retry_count": 2 + randomizer.randint(0, 1),
                "response_code": 200,
                "policy": "default",
                "correlation_id": correlation_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        )

    return json.dumps(
        {
            "ts": at.isoformat(),
            "stream": "mesh",
            "service": "api",
            "upstream": "db",
            "latency_ms": 90 + randomizer.randint(0, 30),
            "retry_count": randomizer.randint(0, 2),
            "response_code": 200,
            "policy": "default",
            "correlation_id": correlation_id,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _stream_records(scenario: str, seed: int, stream_name: str, time_anchor: datetime, duration_minutes: int, resolution_seconds: int) -> list[str]:
    randomizer = random.Random(f"{scenario}|{seed}|{stream_name}|{time_anchor.isoformat()}")
    steps = max(1, int(duration_minutes * 60 / resolution_seconds))
    incident_start = max(1, steps // 2)
    records: list[str] = []
    for offset in range(steps):
        at = time_anchor + timedelta(seconds=offset * resolution_seconds)
        records.append(
            _stream_line(
                stream_name=stream_name,
                at=at,
                scenario=scenario,
                randomizer=randomizer,
                is_incident_window=offset >= incident_start,
            )
        )
    return records


def _write_stream(bundle_dir: Path, bundle_id: str, scenario: str, seed: int, stream_name: str, time_anchor: datetime, duration_minutes: int, resolution_seconds: int) -> StreamArtifact:
    file_name = STREAM_FILE_NAMES[stream_name]
    file_path = bundle_dir / file_name
    records = _stream_records(
        scenario=scenario,
        seed=seed,
        stream_name=stream_name,
        time_anchor=time_anchor,
        duration_minutes=duration_minutes,
        resolution_seconds=resolution_seconds,
    )
    content = "\n".join(records) + "\n"
    file_path.write_text(content, encoding="utf-8", newline="\n")
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return StreamArtifact(
        bundle_id=bundle_id,
        stream_name=stream_name,
        format=STREAM_FORMATS[stream_name],
        file_name=file_name,
        record_count=len(records),
        checksum=checksum,
    )


def _ground_truth(bundle_id: str, scenario: str, threshold: float | None, definition: ScenarioDefinition) -> ExpectedOutputLabelSet:
    return ExpectedOutputLabelSet(
        bundle_id=bundle_id,
        scenario_id=scenario,
        root_cause=definition.root_cause_label,
        trigger=definition.trigger,
        blast_radius=DEFAULT_SCENARIOS[scenario].blast_radius,
        expected_first_signal=DEFAULT_SCENARIOS[scenario].expected_first_signal,
        confidence_target_min=0.70,
        confidence_target_max=0.95,
        threshold_default=0.70,
        threshold_override=threshold,
    )


def _manifest_payload(bundle: IncidentBundle, threshold: float | None) -> dict:
    return {
        "bundle_id": bundle.bundle_id,
        "scenario": bundle.scenario_id,
        "seed": bundle.seed,
        "time_anchor": bundle.time_anchor.isoformat(),
        "created_at": bundle.created_at.isoformat(),
        "duration_minutes": bundle.duration_minutes,
        "resolution_seconds": bundle.resolution_seconds,
        "threshold": threshold if threshold is not None else 0.70,
        "artifacts": [
            {
                "stream_name": artifact.stream_name,
                "file_name": artifact.file_name,
                "format": artifact.format,
                "record_count": artifact.record_count,
                "checksum": artifact.checksum,
            }
            for artifact in bundle.stream_artifacts
        ],
    }


def generate(
    scenario: str,
    seed: int,
    output_root: str | Path = "tests/fixtures/mock_incidents",
    *,
    duration_minutes: int = 30,
    resolution_seconds: int = 60,
    threshold: float | None = None,
    time_anchor: str | datetime | None = None,
) -> dict:
    _format_guardrails()
    if not isinstance(seed, int):
        raise ValueError("INVALID_PARAMETER")
    if threshold is not None and not (0.0 <= threshold <= 1.0):
        raise ValueError("INVALID_PARAMETER")

    definition = _scenario_definition(scenario)
    parsed_anchor = _parse_time_anchor(time_anchor)
    bundle_id = _bundle_id_for(scenario=scenario, seed=seed, time_anchor=parsed_anchor)

    bundle_dir = Path(output_root) / bundle_id
    bundle_dir.mkdir(parents=True, exist_ok=True)

    stream_artifacts = [
        _write_stream(
            bundle_dir=bundle_dir,
            bundle_id=bundle_id,
            scenario=scenario,
            seed=seed,
            stream_name=stream_name,
            time_anchor=parsed_anchor,
            duration_minutes=duration_minutes,
            resolution_seconds=resolution_seconds,
        )
        for stream_name in ALL_STREAMS
    ]

    bundle = IncidentBundle(
        bundle_id=bundle_id,
        scenario_id=scenario,
        seed=seed,
        time_anchor=parsed_anchor,
        duration_minutes=duration_minutes,
        resolution_seconds=resolution_seconds,
        created_at=datetime.now(tz=UTC).replace(microsecond=0),
        artifacts_path=str(bundle_dir),
        stream_artifacts=stream_artifacts,
    )

    manifest_path = bundle_dir / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest_payload(bundle=bundle, threshold=threshold), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ground_truth = _ground_truth(bundle_id=bundle_id, scenario=scenario, threshold=threshold, definition=definition)
    ground_truth_path = bundle_dir / "ground_truth.json"
    ground_truth_path.write_text(json.dumps(ground_truth.model_dump(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    artifacts = [str(manifest_path), str(ground_truth_path)] + [str(bundle_dir / STREAM_FILE_NAMES[stream]) for stream in ALL_STREAMS]
    return {
        "bundle_id": bundle_id,
        "scenario": scenario,
        "seed": seed,
        "artifacts": artifacts,
        "determinism": {
            "stream_artifacts_byte_identical": True,
            "allowed_metadata_variation": ["created_at", "run_timestamp"],
        },
    }


def generate_all_scenarios(
    seed: int,
    output_root: str | Path = "tests/fixtures/mock_incidents",
    *,
    time_anchor: str | datetime,
    duration_minutes: int = 30,
    resolution_seconds: int = 60,
    threshold: float | None = None,
) -> list[dict]:
    results: list[dict] = []
    for scenario in DEFAULT_SCENARIOS:
        results.append(
            generate(
                scenario=scenario,
                seed=seed,
                output_root=output_root,
                time_anchor=time_anchor,
                duration_minutes=duration_minutes,
                resolution_seconds=resolution_seconds,
                threshold=threshold,
            )
        )
    return results


def compare_deterministic_runs(first_bundle_dir: str | Path, second_bundle_dir: str | Path, metadata_exceptions: set[str] | None = None) -> dict:
    metadata_exceptions = metadata_exceptions or {"created_at", "run_timestamp"}
    first = Path(first_bundle_dir)
    second = Path(second_bundle_dir)

    stream_files = [
        "ui_events.log",
        "api_logs.log",
        "db_events.log",
        "k8s_events.log",
        "mesh_events.jsonl",
    ]
    stream_equal = True
    stream_diffs: list[str] = []
    for file_name in stream_files:
        first_bytes = (first / file_name).read_bytes()
        second_bytes = (second / file_name).read_bytes()
        if first_bytes != second_bytes:
            stream_equal = False
            stream_diffs.append(file_name)

    manifest_a = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    manifest_b = json.loads((second / "manifest.json").read_text(encoding="utf-8"))
    metadata_diffs = sorted(
        key
        for key in set(manifest_a).union(manifest_b)
        if manifest_a.get(key) != manifest_b.get(key) and key in metadata_exceptions
    )

    illegal_metadata_diffs = sorted(
        key
        for key in set(manifest_a).union(manifest_b)
        if manifest_a.get(key) != manifest_b.get(key) and key not in metadata_exceptions
    )

    return {
        "stream_artifacts_byte_identical": stream_equal,
        "stream_diffs": stream_diffs,
        "allowed_metadata_variation": metadata_diffs,
        "illegal_metadata_variation": illegal_metadata_diffs,
        "pass": stream_equal and not illegal_metadata_diffs,
    }


def validate_ground_truth_payload(payload: dict) -> bool:
    missing = REQUIRED_GROUND_TRUTH_KEYS.difference(payload)
    if missing:
        raise ValueError(f"missing_ground_truth_fields:{sorted(missing)}")

    threshold_override = payload.get("threshold_override")
    threshold = threshold_override if threshold_override is not None else payload.get("threshold_default", 0.70)
    if not isinstance(threshold, (int, float)) or not (0.0 <= float(threshold) <= 1.0):
        raise ValueError("INVALID_PARAMETER")
    return True
