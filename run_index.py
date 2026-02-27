#!/usr/bin/env python
"""Smoke-test the LlamaIndex Differential Indexer against mock diff bundles.

Exercises the full parse → project → upsert pipeline against realistic
multi-language commits (Python, C#, YAML, TOML, JSON, .env, INI) without
needing a real git repository or running the Brain.

Graph store auto-selection (factory decides):
  • NEO4J_PASSWORD is set  → Neo4jPropertyGraphStore (primary)
  • no NEO4J_PASSWORD      → KuzuPropertyGraphStore  (local fallback, needs --persist)

Neo4j env vars (.env file or shell exports)::

    NEO4J_URL       bolt://localhost:7687
    NEO4J_USERNAME  neo4j
    NEO4J_PASSWORD  password
    NEO4J_DATABASE  neo4j          # optional

Docker quick-start::

    docker run --rm -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5

Usage::

    # list available scenarios
    python run_index.py

    # run from in-memory scenario (by ID)
    python run_index.py timeout_cascade --no-embed

    # run from on-disk fixture directory
    python run_index.py tests/fixtures/mock_diffs/timeout_cascade --no-embed

    # run without Gemini AND without Neo4j (Kuzu local fallback)
    python run_index.py timeout_cascade --no-embed --persist ./rca_graph_timeout

    # run all scenarios
    python run_index.py --all --no-embed

Then visualise in Neo4j Browser:  http://localhost:7474
    MATCH (n) RETURN n LIMIT 50

Available scenarios
-------------------
    timeout_cascade              Python client + k8s YAML + .env timeout change
    db_pool_exhaustion           C# DbContext + appsettings.json + TOML pool size
    feature_flag_rollout         Python resolver + JSON + .env + INI flag flip
    rate_limit_misconfiguration  Python middleware + Helm YAML + TOML ordering bug
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import textwrap
from pathlib import Path

# Ensure Unicode output works on Windows (cp1252 consoles can't encode box-drawing chars).
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass  # Python < 3.7, ignore

from dotenv import load_dotenv

load_dotenv()

from rca.seed.mock_diff_generator import ALL_SCENARIOS, MockDiffBundle

# Language → tree-sitter name understood by CodeHierarchyNodeParser
# Files with languages not in this map will be indexed as plain text nodes.
_PARSEABLE_LANGUAGES: set[str] = {"python", "csharp", "javascript", "typescript", "go", "java"}

# File-extension → language heuristic used when CodeHierarchyNodeParser is unavailable
_EXT_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".cs": "csharp",
    ".js": "javascript",
    ".ts": "typescript",
    ".go": "go",
    ".java": "java",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".ini": "ini",
    ".env": "env",
}


# ---------------------------------------------------------------------------
# RepositoryAdapter shim — wraps MockDiffBundle
# ---------------------------------------------------------------------------

class BundleAdapter:
    """Implements the ``RepositoryAdapter`` protocol backed by a ``MockDiffBundle``."""

    def __init__(self, bundle: MockDiffBundle) -> None:
        self._bundle = bundle

    def get_file(self, path: str, commit_sha: str) -> str:  # noqa: ARG002
        return self._bundle.get_file(path, commit_sha)

    def get_diff(self, path: str, commit_sha: str) -> str:  # noqa: ARG002
        return self._bundle.get_diff(path, commit_sha)

    def list_changed_files(self, commit_sha: str) -> list[str]:  # noqa: ARG002
        return self._bundle.changed_files()

    def list_commits(self, branch: str, since_days: int) -> list[str]:  # noqa: ARG002
        return [self._bundle.commit_sha]


# ---------------------------------------------------------------------------
# Language detection per file
# ---------------------------------------------------------------------------

def _detect_language(path: str) -> str:
    """Best-effort language name from file extension."""
    ext = Path(path).suffix.lower()
    # .env.defaults, .env.features etc.
    if Path(path).name.startswith(".env"):
        return "env"
    return _EXT_LANGUAGE.get(ext, "text")


# ---------------------------------------------------------------------------
# Printing helpers
# ---------------------------------------------------------------------------

SEP = "─" * 72


def _print_header(title: str) -> None:
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


def _print_bundle_info(bundle: MockDiffBundle) -> None:
    _print_header(f"SCENARIO: {bundle.scenario_id}")
    print(f"  Service     : {bundle.service}")
    print(f"  Commit SHA  : {bundle.commit_sha}")
    print(f"  Description : ")
    for line in textwrap.wrap(bundle.description, width=64):
        print(f"    {line}")
    print()
    print(f"  {'FILE':<52}  LANGUAGE    OPERATION")
    print(f"  {'─'*52}  {'─'*10}  {'─'*12}")
    for path, entry in bundle.files.items():
        # Infer operation from diff
        if entry.diff.startswith("--- /dev/null"):
            op = "ADD"
        elif "+++ /dev/null" in entry.diff:
            op = "DELETE"
        else:
            op = "MODIFY"
        print(f"  {path:<52}  {entry.language:<10}  {op}")
    print()


def _print_diagnostics(diagnostics: list) -> None:
    if not diagnostics:
        return
    print(f"\n  DIAGNOSTICS ({len(diagnostics)})")
    for d in diagnostics:
        icon = "⚠" if d.severity == "warning" else "✗"
        loc = f"[{d.file_path}]" if d.file_path else ""
        print(f"    {icon} [{d.severity.upper()}] {d.stage}: {d.message} {loc}")


def _print_graph_summary(nodes_upserted: int, bundle: MockDiffBundle, diagnostics: list) -> None:
    warns = sum(1 for d in diagnostics if d.severity == "warning")
    errors = sum(1 for d in diagnostics if d.severity == "error")

    _print_header("INDEXING RESULT")
    print(f"  Nodes upserted : {nodes_upserted}")
    print(f"  Warnings       : {warns}")
    print(f"  Errors         : {errors}")
    total_files = len(bundle.files)
    parsed_files = total_files - warns - errors
    print(f"  Files parsed   : {max(parsed_files, 0)} / {total_files} "
          "(non-code files produce warnings — expected)")


def _print_node_table(nodes: list) -> None:
    if not nodes:
        print("\n  (no nodes returned by retriever)")
        return

    print(f"\n  {'SYMBOL':<35}  {'STATUS':<12}  {'LINES':<10}  FILE")
    print(f"  {'─'*35}  {'─'*12}  {'─'*10}  {'─'*40}")
    for node in nodes[:30]:  # cap display at 30
        m = node.metadata if hasattr(node, "metadata") else {}
        name = m.get("name") or m.get("symbol_name") or "(file-level)"
        status = m.get("status", "?")
        start = m.get("start_line", "?")
        end = m.get("end_line", "?")
        fpath = m.get("file_path", "?")
        lines = f"{start}–{end}" if start != "?" else "?"
        print(f"  {name[:35]:<35}  {status:<12}  {lines:<10}  {fpath}")

    if len(nodes) > 30:
        print(f"  ... and {len(nodes) - 30} more nodes")


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------

def run_scenario(
    bundle: MockDiffBundle,
    persist_dir: Path | None,
    embed: bool,
) -> int:
    """Index *bundle* and print results.  Returns exit code (0 = success)."""
    from rca.indexing.models import RepoEntry
    from rca.indexing.service_repo_map import InMemoryServiceRepoMap
    from rca.indexing.differential_indexer import DifferentialIndexer, STATUS_ADDED, STATUS_MODIFIED
    from rca.indexing.models import DifferentialIndexerRequest

    _print_bundle_info(bundle)

    # ------------------------------------------------------------------
    # 1. Embedding setup
    # ------------------------------------------------------------------
    if embed:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            print("  [WARN] GEMINI_API_KEY not set — falling back to --no-embed mode.\n"
                  "         Set it in .env or export GEMINI_API_KEY=... to enable vectors.\n")
            embed = False
        else:
            try:
                from rca.indexing.graph_store_factory import configure_gemini_embedding
                from llama_index.core import Settings
                configure_gemini_embedding(api_key=api_key)
                Settings.llm = None  # type: ignore[assignment]
                print(f"  Embedding : GeminiEmbedding (models/text-embedding-004)")
                print(f"  LLM       : disabled (indexer only)")
            except ImportError as exc:
                print(f"  [WARN] Could not configure Gemini embedding: {exc}")
                print(f"         Install llama-index-embeddings-gemini to enable vectors.")
                embed = False

    if not embed:
        # Disable embedding AND LLM entirely so index construction doesn't try
        # to reach OpenAI (llama-index's built-in defaults for both).
        try:
            from llama_index.core import Settings
            from llama_index.core.embeddings import MockEmbedding
            Settings.embed_model = MockEmbedding(embed_dim=8)
            Settings.llm = None  # type: ignore[assignment]
            print("  Embedding : MockEmbedding (no vectors — graph structure only)")
            print("  LLM       : disabled")
        except ImportError:
            print("  Embedding : not configured (llama-index-core not installed?)")

    # ------------------------------------------------------------------
    # 2. Graph store — Neo4j primary, Kuzu fallback
    # ------------------------------------------------------------------
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")
    use_neo4j = bool(neo4j_password)

    # For Kuzu fallback: need a persist dir (cannot use a temp dir — Kuzu dir
    # must not already exist).  If none given, create a named one.
    if not use_neo4j and persist_dir is None:
        persist_dir = Path(tempfile.mkdtemp(prefix="rca_index_"))
        _cleanup_persist = True
    else:
        _cleanup_persist = False

    try:
        from rca.indexing.graph_store_factory import create_property_graph_index
        if use_neo4j:
            from rca.indexing.graph_store_factory import create_neo4j_store
            try:
                graph_store = create_neo4j_store()
                neo4j_url = os.getenv("NEO4J_URL", "bolt://localhost:7687")
                neo4j_db  = os.getenv("NEO4J_DATABASE", "neo4j")
                print(f"  Graph store: Neo4j → {neo4j_url}  db={neo4j_db}")
                print(f"  Browse at  : http://localhost:7474  (MATCH (n) RETURN n LIMIT 50)")
            except Exception as exc:  # noqa: BLE001
                print(f"\n  [ERROR] Neo4j connection failed: {exc}")
                print(f"  Is Neo4j running?  docker run --rm -p 7474:7474 -p 7687:7687 \\")
                print(f"                       -e NEO4J_AUTH=neo4j/$NEO4J_PASSWORD neo4j:5")
                return 1
            index = create_property_graph_index(graph_store=graph_store)
        else:
            from rca.indexing.graph_store_factory import create_kuzu_store
            try:
                graph_store = create_kuzu_store(persist_dir=persist_dir)
                print(f"  Graph store: Kuzu (fallback) → {persist_dir}")
                print(f"  Tip: set NEO4J_PASSWORD in .env to use Neo4j instead")
            except ImportError as exc:
                print(f"\n  [ERROR] Could not create Kuzu store: {exc}")
                print(f"  Install: pip install kuzu llama-index-graph-stores-kuzu")
                return 1
            index = create_property_graph_index(graph_store=graph_store)

        # ------------------------------------------------------------------
        # 3. Wire up indexer
        # ------------------------------------------------------------------
        # Use the primary language of the first parseable file as the service language.
        # Files with unparseable languages (YAML, env, etc.) will produce warnings — expected.
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
            index=index,
            service_repo_map=service_map,
            repo_adapter=adapter,
        )

        # ------------------------------------------------------------------
        # 4. Index the commit
        # ------------------------------------------------------------------
        print(f"\n  Indexing commit {bundle.commit_sha} for '{bundle.service}'...\n")
        request = DifferentialIndexerRequest(
            service=bundle.service,
            commit_sha=bundle.commit_sha,
        )
        nodes_upserted, diagnostics = indexer.index_commit(request)

        # For Kuzu: persist the LlamaIndex storage context alongside the graph files.
        # For Neo4j: data is written to the server in real time — no local persist needed.
        if not use_neo4j and persist_dir is not None:
            store_dir = Path(persist_dir) / "store"
            try:
                index.storage_context.persist(str(store_dir))
            except Exception:  # noqa: BLE001
                pass

        _print_diagnostics(diagnostics)
        _print_graph_summary(nodes_upserted, bundle, diagnostics)

        # ------------------------------------------------------------------
        # 5. Query the graph
        # ------------------------------------------------------------------
        print(f"\n  Querying graph for modified/added nodes...")
        try:
            retriever = index.as_retriever(include_text=False)
            results = retriever.retrieve(f"service:{bundle.service} commit:{bundle.commit_sha}")
            nodes = [r.node for r in results]

            modified = [n for n in nodes if n.metadata.get("status") in (STATUS_MODIFIED, STATUS_ADDED)]
            print(f"\n  Total nodes returned : {len(nodes)}")
            print(f"  Modified/Added       : {len(modified)}")
            _print_node_table(nodes)

        except Exception as exc:  # noqa: BLE001
            print(f"\n  [WARN] Retriever query failed: {exc}")
            print(f"         This is expected when llama-index is not fully installed.")

        print(f"\n{SEP}\n")
        return 1 if any(d.severity == "error" for d in diagnostics) else 0

    finally:
        if _cleanup_persist and persist_dir and persist_dir.exists():
            import shutil
            shutil.rmtree(persist_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _list_scenarios() -> None:
    _print_header("AVAILABLE SCENARIOS")
    print(f"  {'ID':<35}  SERVICE              LANGUAGES")
    print(f"  {'─'*35}  {'─'*20}  {'─'*40}")
    for sid, bundle in ALL_SCENARIOS.items():
        langs = ", ".join(sorted({e.language for e in bundle.files.values()}))
        print(f"  {sid:<35}  {bundle.service:<20}  {langs}")
    print()
    print(f"  Usage: python run_index.py <scenario_id>")
    print(f"         python run_index.py --all\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke-test the LlamaIndex Differential Indexer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "scenario",
        nargs="?",
        help="Scenario ID to run (omit to list available scenarios)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all scenarios in sequence",
    )
    parser.add_argument(
        "--no-embed",
        dest="embed",
        action="store_false",
        default=True,
        help="Skip Gemini embedding (graph structure only, no vectors)",
    )
    parser.add_argument(
        "--persist",
        metavar="DIR",
        help="Kuzu fallback only: keep graph on disk at DIR (default: temp dir, deleted on exit)",
    )

    args = parser.parse_args()

    if not args.scenario and not args.all:
        _list_scenarios()
        sys.exit(0)

    persist_dir = Path(args.persist) if args.persist else None

    if args.all:
        codes = []
        for sid in ALL_SCENARIOS:
            bundle = ALL_SCENARIOS[sid]
            code = run_scenario(bundle, persist_dir, embed=args.embed)
            codes.append(code)
        sys.exit(1 if any(c != 0 for c in codes) else 0)

    from rca.seed.mock_diff_generator import get_scenario, load_from_dir
    scenario_arg = args.scenario
    # Detect fixture directory: path exists on disk, or contains a path separator
    is_path = Path(scenario_arg).exists() or any(c in scenario_arg for c in "/\\\\.")
    if is_path:
        fixture_path = Path(scenario_arg)
        if not fixture_path.is_dir():
            print(f"\nError: not a directory: {fixture_path}")
            sys.exit(1)
        try:
            bundle = load_from_dir(fixture_path)
        except (FileNotFoundError, KeyError) as exc:
            print(f"\nError loading fixture: {exc}\n")
            sys.exit(1)
    else:
        try:
            bundle = get_scenario(scenario_arg)
        except KeyError as exc:
            print(f"\nError: {exc}")
            print("Run `python run_index.py` with no arguments to list available scenarios.\n")
            sys.exit(1)

    code = run_scenario(bundle, persist_dir, embed=args.embed)
    sys.exit(code)


if __name__ == "__main__":
    main()
