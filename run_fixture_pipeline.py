#!/usr/bin/env python
"""Load a fixture, populate Neo4j, and run the Brain end-to-end.

Usage:
    python run_fixture_pipeline.py tests/fixtures/shoe_store/order_slow_due_to_payment

What this does:
1) Optional Neo4j reset in two DBs: service mesh + repo history
2) Ingests service mesh events into the service mesh DB
3) Indexes mock-diff bundles into the repo history DB
4) Reads logs from files and runs BrainEngine with repo-history graph index
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

from rca.brain import ApprovedIncident, BrainEngine, BrainEngineConfig, LLMConfig
from rca.indexing.differential_indexer import DifferentialIndexer
from rca.indexing.models import DifferentialIndexerRequest, RepoEntry
from rca.indexing.service_repo_map import InMemoryServiceRepoMap
from rca.indexing.graph_store_factory import create_neo4j_store, create_property_graph_index
from rca.seed.mock_diff_generator import load_from_dir

_PARSEABLE_LANGUAGES: set[str] = {"python", "csharp", "javascript", "typescript", "go", "java"}


def _print_brain_report(report) -> None:
    sep = "-" * 72
    print(f"\n{sep}")
    print("BRAIN OUTPUT")
    print(sep)
    print(f"Status          : {report.status}")
    print(f"Critic score    : {report.critic_score:.2f}")
    print(f"Fix confidence  : {report.fix_confidence:.2f}")
    print(f"Hypotheses      : {len(report.hypotheses)}")
    print(f"Iteration       : {report.metadata.get('iteration', '?')}")
    print(f"LLM enabled     : {report.metadata.get('llm_enabled', False)}")

    fix_summary = report.metadata.get("fix_summary", "")
    fix_reasoning = report.metadata.get("fix_reasoning", "")
    if fix_summary:
        print("\nSuggested fix")
        for line in textwrap.wrap(fix_summary, width=66):
            print(f"  {line}")
        if fix_reasoning:
            print("  Reasoning:")
            for line in textwrap.wrap(fix_reasoning, width=64):
                print(f"    {line}")

    if report.hypotheses:
        print("\nRanked hypotheses")
        for idx, hypothesis in enumerate(report.hypotheses, start=1):
            print(
                f"  [{idx}] {hypothesis.title} "
                f"(confidence={hypothesis.confidence:.2f})"
            )
            for line in textwrap.wrap(hypothesis.summary, width=66):
                print(f"      {line}")
            if hypothesis.evidence_refs:
                print(f"      Evidence: {', '.join(hypothesis.evidence_refs)}")
            else:
                print("      Evidence: (none)")
            print()

    if report.errors:
        print("Errors")
        for err in report.errors:
            print(f"  - {err}")
    print(sep)


class BundleAdapter:
    def __init__(self, bundle):
        self._bundle = bundle

    def get_file(self, path: str, commit_sha: str) -> str:  # noqa: ARG002
        return self._bundle.get_file(path, commit_sha)

    def get_diff(self, path: str, commit_sha: str) -> str:  # noqa: ARG002
        return self._bundle.get_diff(path, commit_sha)

    def list_changed_files(self, commit_sha: str) -> list[str]:  # noqa: ARG002
        return self._bundle.changed_files()

    def list_commits(self, branch: str, since_days: int) -> list[str]:  # noqa: ARG002
        return [self._bundle.commit_sha]


def _require_neo4j_env() -> tuple[str, str, str, str, str, str, str]:
    default_url = os.environ.get("NEO4J_URL", "bolt://localhost:7687")
    default_username = os.environ.get("NEO4J_USERNAME", "neo4j")
    default_password = os.environ.get("NEO4J_PASSWORD", "")

    mesh_url = os.environ.get("NEO4J_MESH_URL", default_url)
    mesh_username = os.environ.get("NEO4J_MESH_USERNAME", default_username)
    mesh_password = os.environ.get("NEO4J_MESH_PASSWORD", default_password)

    repo_url = os.environ.get("NEO4J_REPO_URL", default_url)
    repo_username = os.environ.get("NEO4J_REPO_USERNAME", default_username)
    repo_password = os.environ.get("NEO4J_REPO_PASSWORD", default_password)

    mesh_database = os.environ.get("NEO4J_MESH_DATABASE", "service_mesh")
    repo_database = os.environ.get("NEO4J_REPO_DATABASE", "repo_history")
    if not mesh_password or not repo_password:
        raise ValueError(
            "Neo4j credentials required. Set NEO4J_MESH_PASSWORD/NEO4J_REPO_PASSWORD "
            "or fallback NEO4J_PASSWORD."
        )

    return (
        mesh_url,
        mesh_username,
        mesh_password,
        repo_url,
        repo_username,
        repo_password,
        mesh_database,
        repo_database,
    )


def _ensure_database(url: str, username: str, password: str, database: str) -> bool:
    """Ensure a Neo4j database exists and is online.

    Attempts CREATE DATABASE IF NOT EXISTS via the system DB when needed.
    """
    from neo4j import GraphDatabase

    with GraphDatabase.driver(url, auth=(username, password)) as driver:
        # Quick happy-path check
        try:
            with driver.session(database=database) as session:
                session.run("RETURN 1")
            return True
        except Exception:
            pass

        # Try creating it from system DB (requires supported edition/permissions)
        try:
            with driver.session(database="system") as session:
                session.run(f"CREATE DATABASE {database} IF NOT EXISTS")
        except Exception as exc:  # noqa: BLE001
            # Neo4j Community doesn't support CREATE DATABASE.
            message = str(exc).lower()
            if "unsupported administration command" in message or "not allowed" in message:
                return False
            raise

        # Re-check availability
        try:
            with driver.session(database=database) as session:
                session.run("RETURN 1")
            return True
        except Exception:
            return False


def _reset_graph(url: str, username: str, password: str, database: str) -> None:
    from neo4j import GraphDatabase

    with GraphDatabase.driver(url, auth=(username, password)) as driver:
        with driver.session(database=database) as session:
            session.run("MATCH (n) DETACH DELETE n")


def _load_incident_files(incident_dir: Path) -> tuple[dict, dict, list[dict], dict[str, str]]:
    manifest = json.loads((incident_dir / "manifest.json").read_text(encoding="utf-8"))
    ground_truth = json.loads((incident_dir / "ground_truth.json").read_text(encoding="utf-8"))

    mesh_path = incident_dir / "mesh_events.jsonl"
    mesh_events = [
        json.loads(line)
        for line in mesh_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    logs: dict[str, str] = {}
    for log_name in ("ui_events.log", "order_logs.log", "payment_logs.log", "shipping_logs.log"):
        p = incident_dir / log_name
        if p.exists():
            logs[log_name] = p.read_text(encoding="utf-8")

    return manifest, ground_truth, mesh_events, logs


def _ingest_architecture(url: str, username: str, password: str, database: str, arch_path: Path) -> tuple[int, int]:
    """Create MeshService nodes and CALLS edges from architecture.json."""
    if not arch_path.exists():
        return 0, 0

    arch = json.loads(arch_path.read_text(encoding="utf-8"))
    services: list[str] = arch.get("services", [])
    externals: set[str] = set(arch.get("external_dependencies", []))
    edges: list[dict] = arch.get("edges", [])

    all_service_names = set(services) | externals

    node_query = """
    MERGE (s:MeshService {name: $name})
    SET s.is_external = $is_external, s.system = $system
    """
    edge_query = """
    MERGE (src:MeshService {name: $from_svc})
    MERGE (dst:MeshService {name: $to_svc})
    MERGE (src)-[:DEPENDS_ON {type: $edge_type}]->(dst)
    """

    system = arch.get("system", "unknown")
    from neo4j import GraphDatabase

    with GraphDatabase.driver(url, auth=(username, password)) as driver:
        with driver.session(database=database) as session:
            for name in all_service_names:
                session.run(node_query, name=name, is_external=(name in externals), system=system)
            for edge in edges:
                session.run(
                    edge_query,
                    from_svc=edge["from"],
                    to_svc=edge["to"],
                    edge_type=edge.get("type", "sync_http"),
                )

    return len(all_service_names), len(edges)


def _ingest_mesh_events(url: str, username: str, password: str, database: str, scenario_id: str, mesh_events: list[dict]) -> int:
    """Aggregate mesh events into a single MESH_CALL edge per (service, upstream) pair.

    Each edge stores summary stats: call_count, error_count, avg_latency_ms,
    max_latency_ms, p99_latency_ms.  This avoids creating N parallel edges for
    the same service pair, which clutters graph visualisation.
    """
    from collections import defaultdict

    # Group events by (service, upstream)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in mesh_events:
        service = str(row.get("service", "")).strip()
        upstream = str(row.get("upstream", "")).strip()
        if service and upstream:
            groups[(service, upstream)].append(row)

    merge_query = """
    MERGE (src:MeshService {name: $service})
    MERGE (dst:MeshService {name: $upstream})
    MERGE (src)-[r:OBSERVED_CALL {scenario_id: $scenario_id}]->(dst)
    SET r.call_count     = $call_count,
        r.error_count    = $error_count,
        r.avg_latency_ms = $avg_latency_ms,
        r.max_latency_ms = $max_latency_ms,
        r.p99_latency_ms = $p99_latency_ms,
        r.policy         = $policy
    """

    from neo4j import GraphDatabase

    with GraphDatabase.driver(url, auth=(username, password)) as driver:
        with driver.session(database=database) as session:
            for (service, upstream), rows in groups.items():
                latencies = sorted(int(r.get("latency_ms", 0) or 0) for r in rows)
                error_count = sum(
                    1 for r in rows if int(r.get("response_code", 200) or 200) >= 500
                )
                p99_idx = max(0, int(len(latencies) * 0.99) - 1)
                session.run(
                    merge_query,
                    service=service,
                    upstream=upstream,
                    scenario_id=scenario_id,
                    call_count=len(rows),
                    error_count=error_count,
                    avg_latency_ms=round(sum(latencies) / len(latencies), 1),
                    max_latency_ms=latencies[-1],
                    p99_latency_ms=latencies[p99_idx],
                    policy=str(rows[0].get("policy", "default")),
                )

    return sum(len(v) for v in groups.values())


def _index_diff_bundle(graph_index, bundle_dir: Path) -> tuple[int, int]:
    bundle = load_from_dir(bundle_dir)

    primary_language = next(
        (e.language for e in bundle.files.values() if e.language in _PARSEABLE_LANGUAGES),
        "python",
    )

    service_map = InMemoryServiceRepoMap({
        bundle.service: RepoEntry(
            repo_url=f"https://github.com/example/{bundle.service}",
            language=primary_language,
            default_branch="main",
        )
    })

    adapter = BundleAdapter(bundle)
    indexer = DifferentialIndexer(
        index=graph_index,
        service_repo_map=service_map,
        repo_adapter=adapter,
    )

    request = DifferentialIndexerRequest(
        service=bundle.service,
        commit_sha=bundle.commit_sha,
        file_paths=bundle.changed_files(),
        enable_semantic_delta=False,
    )
    upserted, diags = indexer.index_commit(request)
    errors = sum(1 for d in diags if d.severity == "error")
    return upserted, errors


def _build_incident(
    scenario_id: str,
    manifest: dict,
    ground_truth: dict,
    mesh_events: list[dict],
    logs: dict[str, str],
) -> ApprovedIncident:
    started_at_raw = manifest.get("incident_window_start") or manifest.get("time_anchor")
    started_at = datetime.fromisoformat(str(started_at_raw)).astimezone(timezone.utc)

    extra_context: dict[str, str] = {
        "scenario": scenario_id,
        "trigger": str(ground_truth.get("trigger", "unknown")),
        "expected_root_cause": str(ground_truth.get("root_cause", "unknown")),
        "mesh_events_jsonl": "\n".join(json.dumps(r, separators=(",", ":"), sort_keys=True) for r in mesh_events),
    }

    for stream_name, text in logs.items():
        extra_context[stream_name] = "\n".join(text.splitlines()[-40:])

    return ApprovedIncident(
        incident_id=f"{scenario_id}-fixture",
        service=str(manifest.get("triggered_service", "order-service")),
        started_at=started_at,
        deployment_id=str(ground_truth.get("changed_service", "payment-service")),
        extra_context=extra_context,
    )


def run_pipeline(
    fixture_root: Path,
    reset_graph: bool = True,
    brain_report_log_path: Path | None = None,
) -> int:
    incident_dir = fixture_root / "incident"
    diffs_root = fixture_root / "diffs"

    if not incident_dir.exists() or not diffs_root.exists():
        print(f"Fixture does not look valid: {fixture_root}")
        print("Expected subdirectories: incident/ and diffs/")
        return 1

    (
        mesh_url,
        mesh_username,
        mesh_password,
        repo_url,
        repo_username,
        repo_password,
        mesh_database,
        repo_database,
    ) = _require_neo4j_env()
    default_database = os.environ.get("NEO4J_DATABASE", "neo4j")

    same_instance = (
        mesh_url == repo_url
        and mesh_username == repo_username
        and mesh_password == repo_password
    )

    mesh_supported = _ensure_database(mesh_url, mesh_username, mesh_password, mesh_database)
    repo_supported = _ensure_database(repo_url, repo_username, repo_password, repo_database)

    strict_split_enabled = mesh_supported and repo_supported and not (
        same_instance and mesh_database == repo_database
    )
    multi_db_enabled = mesh_supported and repo_supported and same_instance
    if not multi_db_enabled:
        if same_instance:
            print(
                "[WARN] This Neo4j deployment does not support creating multiple databases.\n"
                f"       Falling back to single DB '{default_database}' with logical separation."
            )
            mesh_database = default_database
            repo_database = default_database
            _ensure_database(mesh_url, mesh_username, mesh_password, default_database)
        else:
            print(
                "[INFO] Using two separate Neo4j instances (mesh/repo), each with its own DB."
            )

    if reset_graph:
        _reset_graph(mesh_url, mesh_username, mesh_password, mesh_database)
        if same_instance and mesh_database == repo_database:
            print(f"Neo4j graph reset completed: {mesh_database}.")
        else:
            _reset_graph(repo_url, repo_username, repo_password, repo_database)
            print(
                "Neo4j graph reset completed: "
                f"mesh={mesh_database}@{mesh_url}, repo={repo_database}@{repo_url}."
            )

    scenario_id = fixture_root.name
    if brain_report_log_path is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        brain_report_log_path = fixture_root / "brain_runs" / f"brain_run_{stamp}.json"

    manifest, ground_truth, mesh_events, logs = _load_incident_files(incident_dir)

    arch_nodes, arch_edges = _ingest_architecture(
        mesh_url, mesh_username, mesh_password, mesh_database,
        fixture_root / "architecture.json",
    )
    print(f"Ingested architecture topology: {arch_nodes} services, {arch_edges} edges")

    mesh_count = _ingest_mesh_events(
        mesh_url,
        mesh_username,
        mesh_password,
        mesh_database,
        scenario_id,
        mesh_events,
    )
    print(f"Ingested mesh events into {mesh_database}: {mesh_count}")
    print(f"Loaded logs from files only (not persisted to DB): {sum(len(v.splitlines()) for v in logs.values())}")

    # Force no-embed mode for deterministic local runs without extra providers.
    from llama_index.core import Settings
    from llama_index.core.embeddings import MockEmbedding
    Settings.embed_model = MockEmbedding(embed_dim=8)
    Settings.llm = None  # type: ignore[assignment]

    graph_store = create_neo4j_store(
        url=repo_url,
        username=repo_username,
        password=repo_password,
        database=repo_database,
    )
    graph_index = create_property_graph_index(graph_store=graph_store)

    total_nodes = 0
    total_errors = 0
    bundle_dirs = sorted([p for p in diffs_root.iterdir() if p.is_dir()])
    for bundle_dir in bundle_dirs:
        upserted, errors = _index_diff_bundle(graph_index, bundle_dir)
        total_nodes += upserted
        total_errors += errors
        print(f"Indexed diff bundle {bundle_dir.name}: nodes={upserted}, errors={errors}")

    incident = _build_incident(scenario_id, manifest, ground_truth, mesh_events, logs)

    from neo4j import GraphDatabase
    mesh_driver = GraphDatabase.driver(
        mesh_url, auth=(mesh_username, mesh_password)
    )
    try:
        llm_config = LLMConfig.from_env()
        engine = BrainEngine(
            config=BrainEngineConfig(
                llm_config=llm_config if llm_config.is_configured else None,
                critic_threshold=0.80,
                max_iterations=3,
                graph_index=graph_index,
                mesh_driver=mesh_driver,
                report_log_path=str(brain_report_log_path) if brain_report_log_path else None,
            )
        )
        report = engine.run(incident)
    finally:
        mesh_driver.close()

    print("\nBrain run completed")
    print(f"Status         : {report.status}")
    print(f"Critic score   : {report.critic_score:.2f}")
    print(f"Fix confidence : {report.fix_confidence:.2f}")
    print(f"Hypotheses     : {len(report.hypotheses)}")
    if report.hypotheses:
        top = max(report.hypotheses, key=lambda h: h.confidence)
        print(f"Top cause      : {top.title} ({top.confidence:.2f})")

    _print_brain_report(report)

    log_lines = sum(len(v.splitlines()) for v in logs.values())
    if brain_report_log_path:
        print(f"Brain report log : {brain_report_log_path}")

    print("\nSummary")
    print(f"Scenario         : {scenario_id}")
    print(f"Strict split     : {strict_split_enabled}")
    print(f"Multi-DB enabled : {multi_db_enabled}")
    print(f"Mesh URL         : {mesh_url}")
    print(f"Repo URL         : {repo_url}")
    print(f"Mesh DB          : {mesh_database}")
    print(f"Repo DB          : {repo_database}")
    print(f"Arch services    : {arch_nodes}")
    print(f"Arch edges       : {arch_edges}")
    print(f"Mesh events      : {mesh_count}")
    print(f"Diff nodes       : {total_nodes}")
    print(f"Diff errors      : {total_errors}")
    print(f"Log lines (files): {log_lines}")

    return 0 if total_errors == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate DB from fixture and run Brain")
    parser.add_argument(
        "fixture_root",
        nargs="?",
        default="tests/fixtures/shoe_store/order_slow_due_to_payment",
        help="Path to fixture scenario root (expects incident/ and diffs/)",
    )
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Do not clear Neo4j before ingest",
    )
    parser.add_argument(
        "--brain-log",
        default=None,
        help="Optional output path for BrainEngine JSON report log (defaults to fixture_root/brain_runs/).",
    )
    args = parser.parse_args()

    exit_code = run_pipeline(
        Path(args.fixture_root),
        reset_graph=not args.no_reset,
        brain_report_log_path=Path(args.brain_log) if args.brain_log else None,
    )
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
