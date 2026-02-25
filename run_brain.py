#!/usr/bin/env python
"""Run the Brain against a real mock incident fixture and print the full report.

Usage:
    python run_brain.py [path/to/fixture/dir]

Default fixture: tests/fixtures/mock_incidents/mock-14f0be6ccd38
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from rca.brain import ApprovedIncident, BrainEngine, BrainEngineConfig, LLMConfig


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def load_fixture(fixture_dir: Path) -> dict:
    """Return a dict with ground_truth, manifest, and last-N lines of each log."""
    data: dict = {}

    gt_path = fixture_dir / "ground_truth.json"
    if gt_path.exists():
        data["ground_truth"] = json.loads(gt_path.read_text())

    manifest_path = fixture_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        data["manifest"] = manifest

        for artifact in manifest.get("artifacts", []):
            fname = artifact["file_name"]
            fpath = fixture_dir / fname
            if fpath.exists() and fpath.suffix == ".log":
                lines = fpath.read_text(encoding="utf-8").splitlines()
                # Take last 15 lines (incident window)
                data[fname] = "\n".join(lines[-15:])

    return data


def build_incident(fixture_dir: Path, fixture_data: dict) -> ApprovedIncident:
    gt = fixture_data.get("ground_truth", {})
    manifest = fixture_data.get("manifest", {})

    # Prefer ground_truth.started_at → manifest.time_anchor (the actual log start time)
    started_at_str = gt.get("started_at") or manifest.get("time_anchor")
    try:
        started_at = datetime.fromisoformat(started_at_str.replace("Z", "+00:00")) if started_at_str else None
    except (ValueError, TypeError):
        started_at = None
    if started_at is None:
        started_at = datetime.now(tz=timezone.utc).replace(microsecond=0)

    # Build extra_context: ground_truth summary + log snippets
    extra: dict[str, str] = {
        "scenario": gt.get("scenario_id", "unknown"),
        "trigger": gt.get("trigger", "unknown"),
        "expected_root_cause": gt.get("root_cause", "unknown"),
        "blast_radius": gt.get("blast_radius", "unknown"),
    }
    # Add truncated log excerpts
    for key, value in fixture_data.items():
        if key.endswith(".log"):
            extra[key] = value

    return ApprovedIncident(
        incident_id=fixture_dir.name,
        service=gt.get("scenario_id", fixture_dir.name).replace("_", "-"),
        started_at=started_at,
        deployment_id=gt.get("deployment_id") or None,
        extra_context=extra,
    )


def print_report(report) -> None:
    sep = "─" * 72

    print(f"\n{sep}")
    print(f"  BRAIN RCA REPORT")
    print(sep)
    print(f"  Incident ID : {report.incident_id}")
    print(f"  Status      : {report.status.upper()}")
    print(f"  Critic score: {report.critic_score:.2f}")
    print(f"  Iterations  : {report.metadata.get('iteration', '?')}")
    print(f"  LLM enabled : {report.metadata.get('llm_enabled', False)}")
    print(sep)

    if report.hypotheses:
        print("\n  RANKED HYPOTHESES\n")
        for i, h in enumerate(report.hypotheses, 1):
            print(f"  [{i}] {h.title}  (confidence: {h.confidence:.2f})")
            for line in textwrap.wrap(h.summary, width=66):
                print(f"      {line}")
            print(f"      Evidence: {', '.join(h.evidence_refs)}")
            print()

    if report.errors:
        print(f"\n  ERRORS: {report.errors}")

    print(sep + "\n")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    fixture_dir = Path(
        sys.argv[1]
        if len(sys.argv) > 1
        else "tests/fixtures/mock_incidents/mock-14f0be6ccd38"
    )

    if not fixture_dir.exists():
        print(f"Fixture not found: {fixture_dir}")
        sys.exit(1)

    print(f"\nLoading fixture: {fixture_dir}")
    fixture_data = load_fixture(fixture_dir)

    incident = build_incident(fixture_dir, fixture_data)
    print(f"Service  : {incident.service}")
    print(f"Started  : {incident.started_at.isoformat()}")
    print(f"Scenario : {incident.extra_context.get('scenario')}")
    print(f"Cause    : {incident.extra_context.get('expected_root_cause')}")

    llm_config = LLMConfig.from_env()
    if llm_config.is_configured:
        print(f"\nLLM      : {llm_config.provider} / {llm_config.model}")
    else:
        print("\nLLM      : not configured — running in stub mode")
        print("           set GEMINI_API_KEY in .env to enable full analysis")

    print("\nRunning Brain...\n")

    config = BrainEngineConfig(
        llm_config=llm_config if llm_config.is_configured else None,
        critic_threshold=0.80,
        max_iterations=3,
    )
    engine = BrainEngine(config=config)
    report = engine.run(incident)

    print_report(report)


if __name__ == "__main__":
    main()
