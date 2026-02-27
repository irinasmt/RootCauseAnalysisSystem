"""Unit tests for the Differential Indexer against the timeout_cascade fixture.

Loads the on-disk fixture from tests/fixtures/mock_diffs/timeout_cascade
and runs the full parse → project → upsert pipeline against a capturing
in-memory store — no Neo4j, no Kuzu, no network needed.

Expected behaviour
------------------

  src/payment_gateway_client.py  (Python — 5 nodes)
    (module)              lines  1-32   MODIFIED  ← hunk @@ -5 touches line 5
    PaymentGatewayClient  lines 12-32   UNCHANGED ← hunk @@ -5 does not touch class body
    __init__              lines 13-17   UNCHANGED
    charge                lines 17-25   UNCHANGED
    refund                lines 25-32   UNCHANGED

  k8s/payment-service-configmap.yaml  (1 node)
    (module)              lines  1-12   MODIFIED  ← hunk @@ -7

  .env.defaults  (1 node)
    (module)              lines  1-7    MODIFIED  ← hunk @@ -2

  CONTAINS relationships (parent → child):
    (module) → PaymentGatewayClient
    PaymentGatewayClient → __init__
    PaymentGatewayClient → charge
    PaymentGatewayClient → refund
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixture path
# ---------------------------------------------------------------------------

FIXTURE_DIR = (
    Path(__file__).parent.parent / "fixtures" / "mock_diffs" / "timeout_cascade"
)


def pytest_configure(config):
    pass


def _require_fixture():
    if not (FIXTURE_DIR / "manifest.json").exists():
        pytest.skip(
            "Fixture not found — run: python -m rca.seed.mock_diff_generator"
        )


# ---------------------------------------------------------------------------
# Helpers — load bundle + run indexer with capturing store
# ---------------------------------------------------------------------------

class _CapturedNode(NamedTuple):
    node_id: str
    name: str
    file_path: str
    status: str
    start_line: int
    end_line: int
    service: str
    commit_sha: str
    text: str


class _CapturedRelation(NamedTuple):
    source_id: str
    target_id: str
    relation_type: str


class _FakeGraphStore:
    """In-memory graph store that records every upserted node and relation."""

    def __init__(self):
        self.nodes: list[_CapturedNode] = []
        self.relations: list[_CapturedRelation] = []

    def upsert_nodes(self, nodes):
        for n in nodes:
            p = n.properties if hasattr(n, "properties") else {}
            self.nodes.append(_CapturedNode(
                node_id=getattr(n, "id_", None) or p.get("node_id", ""),
                name=p.get("name", ""),
                file_path=p.get("file_path", ""),
                status=p.get("status", ""),
                start_line=int(p.get("start_line", 0)),
                end_line=int(p.get("end_line", 0)),
                service=p.get("service", ""),
                commit_sha=p.get("commit_sha", ""),
                text=getattr(n, "text", "") or "",
            ))

    def upsert_relations(self, relations):
        for r in relations:
            self.relations.append(_CapturedRelation(
                source_id=r.source_id,
                target_id=r.target_id,
                relation_type=r.label,
            ))


def _run_indexer(store: _FakeGraphStore):
    """Load the timeout_cascade fixture and run the indexer, returning the store."""
    _require_fixture()

    from llama_index.core import Settings
    from llama_index.core.embeddings import MockEmbedding
    Settings.embed_model = MockEmbedding(embed_dim=8)
    Settings.llm = None  # type: ignore[assignment]

    from rca.seed.mock_diff_generator import load_from_dir
    from rca.indexing.models import RepoEntry, DifferentialIndexerRequest
    from rca.indexing.service_repo_map import InMemoryServiceRepoMap
    from rca.indexing.differential_indexer import DifferentialIndexer

    bundle = load_from_dir(FIXTURE_DIR)

    # Build a fake index whose property_graph_store is our capturing store
    fake_index = MagicMock()
    fake_index.property_graph_store = store

    service_map = InMemoryServiceRepoMap({
        bundle.service: RepoEntry(
            repo_url="https://github.com/example/payment-service",
            language="python",
            default_branch="main",
        )
    })

    indexer = DifferentialIndexer(
        index=fake_index,
        service_repo_map=service_map,
        repo_adapter=bundle,
    )

    request = DifferentialIndexerRequest(
        service=bundle.service,
        commit_sha=bundle.commit_sha,
    )
    count, diagnostics = indexer.index_commit(request)
    return count, diagnostics


# ---------------------------------------------------------------------------
# Fixtures (pytest) — run the indexer once, share results across tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def indexed():
    """Run the indexer once and return (store, count, diagnostics)."""
    store = _FakeGraphStore()
    count, diagnostics = _run_indexer(store)
    return store, count, diagnostics


# ---------------------------------------------------------------------------
# Basic sanity
# ---------------------------------------------------------------------------

def test_no_errors(indexed):
    """Indexer must complete without error-level diagnostics."""
    store, count, diagnostics = indexed
    errors = [d for d in diagnostics if d.severity == "error"]
    assert errors == [], f"Unexpected errors: {errors}"


def test_total_node_count(indexed):
    """timeout_cascade should produce exactly 7 nodes across 3 files."""
    store, count, _ = indexed
    assert count == 7
    assert len(store.nodes) == 7


def test_all_nodes_have_service(indexed):
    store, _, _ = indexed
    for n in store.nodes:
        assert n.service == "payment-service", f"Missing service on node {n.name}"


def test_all_nodes_have_commit_sha(indexed):
    store, _, _ = indexed
    for n in store.nodes:
        assert n.commit_sha, f"Missing commit_sha on node {n.name}"


def test_all_nodes_unique_ids(indexed):
    store, _, _ = indexed
    ids = [n.node_id for n in store.nodes]
    assert len(ids) == len(set(ids)), f"Duplicate node_ids: {ids}"


# ---------------------------------------------------------------------------
# Per-file node counts
# ---------------------------------------------------------------------------

def _nodes_for(store: _FakeGraphStore, file_path: str) -> list[_CapturedNode]:
    return [n for n in store.nodes if n.file_path == file_path]


def test_python_file_node_count(indexed):
    """Python file should produce 5 nodes: module + class + 3 methods."""
    store, _, _ = indexed
    nodes = _nodes_for(store, "src/payment_gateway_client.py")
    assert len(nodes) == 5, f"Expected 5, got {len(nodes)}: {[n.name for n in nodes]}"


def test_yaml_file_node_count(indexed):
    """YAML configmap should produce 1 (module-level) node."""
    store, _, _ = indexed
    nodes = _nodes_for(store, "k8s/payment-service-configmap.yaml")
    assert len(nodes) == 1, f"Expected 1, got {len(nodes)}: {[n.name for n in nodes]}"


def test_env_file_node_count(indexed):
    """.env.defaults should produce 1 (module-level) node."""
    store, _, _ = indexed
    nodes = _nodes_for(store, ".env.defaults")
    assert len(nodes) == 1, f"Expected 1, got {len(nodes)}: {[n.name for n in nodes]}"


# ---------------------------------------------------------------------------
# Symbol names
# ---------------------------------------------------------------------------

def test_python_symbol_names(indexed):
    store, _, _ = indexed
    names = {n.name for n in _nodes_for(store, "src/payment_gateway_client.py")}
    assert "(module)" in names
    assert "PaymentGatewayClient" in names
    assert "__init__" in names
    assert "charge" in names
    assert "refund" in names


# ---------------------------------------------------------------------------
# Status assignment  (these tests define the CORRECT expected behaviour)
# ---------------------------------------------------------------------------

def _node(store, file_path, name) -> _CapturedNode | None:
    matches = [n for n in store.nodes if n.file_path == file_path and n.name == name]
    return matches[0] if matches else None


def test_python_module_status_is_modified(indexed):
    """The module-level Python node spans lines 1-32; hunk @@ -5,7 touches 5-11.
    Overlap → status must be MODIFIED, not UNCHANGED.
    """
    store, _, _ = indexed
    n = _node(store, "src/payment_gateway_client.py", "(module)")
    assert n is not None, "Missing (module) node for Python file"
    assert n.status == "MODIFIED", (
        f"Expected MODIFIED (hunk at lines 5-11 overlaps module 1-32), got {n.status}"
    )


def test_python_class_status_is_unchanged(indexed):
    """PaymentGatewayClient class starts at line 12; hunk @@ -5 covers lines 5-11.
    No overlap → status must be UNCHANGED.
    """
    store, _, _ = indexed
    n = _node(store, "src/payment_gateway_client.py", "PaymentGatewayClient")
    assert n is not None
    assert n.status == "UNCHANGED", (
        f"Expected UNCHANGED (class at 12-32 does not overlap hunk 5-11), got {n.status}"
    )


def test_yaml_module_status_is_modified(indexed):
    """YAML node spans lines 1-12; hunk @@ -7,7 touches lines 7-13.
    Overlap → status must be MODIFIED.
    """
    store, _, _ = indexed
    n = _node(store, "k8s/payment-service-configmap.yaml", "(module)")
    assert n is not None, "Missing (module) node for YAML file"
    assert n.status == "MODIFIED", (
        f"Expected MODIFIED (hunk at lines 7-13 overlaps module 1-12), got {n.status}"
    )


def test_env_module_status_is_modified(indexed):
    """.env.defaults node spans lines 1-7; hunk @@ -2,6 touches lines 2-7.
    Overlap → status must be MODIFIED.
    """
    store, _, _ = indexed
    n = _node(store, ".env.defaults", "(module)")
    assert n is not None
    assert n.status == "MODIFIED", f"Expected MODIFIED, got {n.status}"


# ---------------------------------------------------------------------------
# Line-number sanity
# ---------------------------------------------------------------------------

def test_python_nodes_have_line_numbers(indexed):
    """All Python nodes must have start_line > 0 after byte→line enrichment."""
    store, _, _ = indexed
    py_nodes = _nodes_for(store, "src/payment_gateway_client.py")
    for n in py_nodes:
        assert n.start_line > 0, f"Node {n.name} missing start_line"
        assert n.end_line >= n.start_line, f"Node {n.name} end_line < start_line"


def test_module_node_starts_at_line_1(indexed):
    store, _, _ = indexed
    for fpath in (
        "src/payment_gateway_client.py",
        "k8s/payment-service-configmap.yaml",
        ".env.defaults",
    ):
        n = _node(store, fpath, "(module)")
        if n:
            assert n.start_line == 1, f"Module node for {fpath} start_line={n.start_line}, want 1"


# ---------------------------------------------------------------------------
# CONTAINS relationships (parent → child hierarchy)
# Currently FAILING — relationships are not yet upserted.
# These tests define the required behaviour for the graph hierarchy feature.
# ---------------------------------------------------------------------------

def test_contains_relations_exist(indexed):
    """The graph must contain CONTAINS edges linking parent to child scopes."""
    store, _, _ = indexed
    assert len(store.relations) > 0, (
        "No CONTAINS relations upserted. "
        "The indexer must call graph_store.upsert_relations() to wire the code hierarchy."
    )


def _relation(store, source_name, target_name, file_path="src/payment_gateway_client.py"):
    """Find a CONTAINS relation by source/target node name."""
    # Build a name→id map
    name_to_id = {n.name: n.node_id for n in store.nodes if n.file_path == file_path}
    src_id = name_to_id.get(source_name)
    tgt_id = name_to_id.get(target_name)
    if not src_id or not tgt_id:
        return None
    return next(
        (r for r in store.relations if r.source_id == src_id and r.target_id == tgt_id),
        None,
    )


def test_module_contains_class(indexed):
    """(module) -[CONTAINS]-> PaymentGatewayClient"""
    store, _, _ = indexed
    r = _relation(store, "(module)", "PaymentGatewayClient")
    assert r is not None, "(module) → PaymentGatewayClient CONTAINS relation missing"
    assert r.relation_type == "CONTAINS"


def test_class_contains_init(indexed):
    """PaymentGatewayClient -[CONTAINS]-> __init__"""
    store, _, _ = indexed
    r = _relation(store, "PaymentGatewayClient", "__init__")
    assert r is not None, "PaymentGatewayClient → __init__ CONTAINS relation missing"
    assert r.relation_type == "CONTAINS"


def test_class_contains_charge(indexed):
    """PaymentGatewayClient -[CONTAINS]-> charge"""
    store, _, _ = indexed
    r = _relation(store, "PaymentGatewayClient", "charge")
    assert r is not None, "PaymentGatewayClient → charge CONTAINS relation missing"
    assert r.relation_type == "CONTAINS"


def test_class_contains_refund(indexed):
    """PaymentGatewayClient -[CONTAINS]-> refund"""
    store, _, _ = indexed
    r = _relation(store, "PaymentGatewayClient", "refund")
    assert r is not None, "PaymentGatewayClient → refund CONTAINS relation missing"
    assert r.relation_type == "CONTAINS"


def test_no_self_relations(indexed):
    """No node should have a relation pointing to itself."""
    store, _, _ = indexed
    self_rels = [r for r in store.relations if r.source_id == r.target_id]
    assert self_rels == [], f"Self-relations found: {self_rels}"


# ---------------------------------------------------------------------------
# Node text — MODIFIED nodes carry patch evidence; UNCHANGED carry nothing
# ---------------------------------------------------------------------------

def test_modified_python_module_text_contains_patch(indexed):
    """(module) is MODIFIED — text must be the ±diff lines, not full source."""
    store, _, _ = indexed
    n = _node(store, "src/payment_gateway_client.py", "(module)")
    assert n is not None
    assert n.status == "MODIFIED"
    assert n.text != "", "MODIFIED node should have non-empty text (patch lines)"
    lines = n.text.splitlines()
    assert any(l.startswith("+") or l.startswith("-") for l in lines), (
        f"Expected +/- patch lines, got: {n.text!r}"
    )


def test_modified_python_module_text_shows_timeout_change(indexed):
    """The patch text should reveal the old (30) and new (15) timeout values."""
    store, _, _ = indexed
    n = _node(store, "src/payment_gateway_client.py", "(module)")
    assert n is not None
    assert "TIMEOUT_SECONDS" in n.text, (
        f"Expected TIMEOUT_SECONDS in patch text, got: {n.text!r}"
    )


def test_unchanged_class_text_is_empty(indexed):
    """PaymentGatewayClient is UNCHANGED — text must be empty."""
    store, _, _ = indexed
    n = _node(store, "src/payment_gateway_client.py", "PaymentGatewayClient")
    assert n is not None
    assert n.text == "", f"UNCHANGED node should have empty text, got: {n.text!r}"


def test_unchanged_methods_text_is_empty(indexed):
    """charge and refund are UNCHANGED — text must be empty."""
    store, _, _ = indexed
    for method in ("__init__", "charge", "refund"):
        n = _node(store, "src/payment_gateway_client.py", method)
        assert n is not None, f"Node '{method}' not found"
        assert n.text == "", f"UNCHANGED '{method}' should have empty text, got: {n.text!r}"


def test_modified_yaml_module_text_contains_patch(indexed):
    """k8s configmap (module) is MODIFIED — text must be patch lines."""
    store, _, _ = indexed
    n = _node(store, "k8s/payment-service-configmap.yaml", "(module)")
    assert n is not None
    assert n.status == "MODIFIED"
    assert n.text != "", "MODIFIED YAML node should have non-empty patch text"


def test_modified_env_module_text_contains_patch(indexed):
    """.env.defaults (module) is MODIFIED — text must be patch lines."""
    store, _, _ = indexed
    n = _node(store, ".env.defaults", "(module)")
    assert n is not None
    assert n.status == "MODIFIED"
    assert n.text != "", "MODIFIED .env node should have non-empty patch text"
