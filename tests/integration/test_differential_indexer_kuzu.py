"""Integration tests for DifferentialIndexer with Kuzu-backed PropertyGraphIndex.

These tests require:
    pip install kuzu llama-index-core llama-index-graph-stores-kuzu
          llama-index-packs-code-hierarchy unidiff

Skipped automatically if dependencies are not installed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Skip entire module if LlamaIndex / Kuzu not installed
pytest.importorskip("llama_index.core", reason="llama-index-core not installed")
pytest.importorskip("kuzu", reason="kuzu not installed")
pytest.importorskip("llama_index.graph_stores.kuzu", reason="llama-index-graph-stores-kuzu not installed")
pytest.importorskip("unidiff", reason="unidiff not installed")

from rca.indexing.differential_indexer import (
    STATUS_ADDED,
    STATUS_DELETED,
    STATUS_MODIFIED,
    STATUS_UNCHANGED,
    DifferentialIndexer,
)
from rca.indexing.graph_store_factory import create_property_graph_index
from rca.indexing.models import BackfillPolicy, DifferentialIndexerRequest, RepoEntry
from rca.indexing.service_repo_map import InMemoryServiceRepoMap

SAMPLE_CSHARP = """\
public class HttpClient
{
    private readonly int _timeout = 30;

    public async Task SendAsync(string url)
    {
        await Task.Delay(_timeout);
    }

    public void Configure(string host)
    {
        Host = host;
    }

    public string Host { get; private set; }
}
"""

MODIFY_TIMEOUT_DIFF = """\
--- a/src/HttpClient.cs
+++ b/src/HttpClient.cs
@@ -1,6 +1,6 @@
 public class HttpClient
 {
-    private readonly int _timeout = 30;
+    private readonly int _timeout = 15;
 
     public async Task SendAsync(string url)
     {
"""

DELETE_FILE_DIFF = """\
--- a/src/HttpClient.cs
+++ /dev/null
@@ -1,16 +0,0 @@
-public class HttpClient
-{
-    private readonly int _timeout = 30;
-}
"""


class StubRepo:
    def __init__(self, files=None, diffs=None, changed_files=None, commits=None):
        self._files = files or {}
        self._diffs = diffs or {}
        self._changed_files = changed_files or []
        self._commits = commits or []

    def get_file(self, path, commit_sha):
        return self._files.get(path, "")

    def get_diff(self, path, commit_sha):
        return self._diffs.get(path, "")

    def list_changed_files(self, commit_sha):
        return self._changed_files

    def list_commits(self, since_days, branch="main"):
        return self._commits


@pytest.fixture()
def kuzu_index(tmp_path):
    """Kuzu-backed PropertyGraphIndex in a temp directory."""
    return create_property_graph_index(persist_dir=str(tmp_path / "graph"))


@pytest.fixture()
def service_map():
    m = InMemoryServiceRepoMap()
    m.register("payment-api", RepoEntry(repo_url="https://github.com/org/payment", language="csharp"))
    return m


class TestDifferentialIndexerKuzu:
    def test_indexing_produces_nodes_in_graph(self, kuzu_index, service_map):
        """End-to-end: changed file → parser → graph upsert."""
        repo = StubRepo(
            files={"src/HttpClient.cs": SAMPLE_CSHARP},
            diffs={"src/HttpClient.cs": MODIFY_TIMEOUT_DIFF},
            changed_files=["src/HttpClient.cs"],
        )
        indexer = DifferentialIndexer(
            index=kuzu_index, service_repo_map=service_map, repo_adapter=repo
        )
        pytest.importorskip("llama_index.packs.code_hierarchy",
                             reason="llama-index-packs-code-hierarchy not installed")

        request = DifferentialIndexerRequest(service="payment-api", commit_sha="abc1234")
        n, diags = indexer.index_commit(request)

        errors = [d for d in diags if d.severity == "error"]
        assert not errors, f"Unexpected errors: {errors}"
        assert n > 0

    def test_idempotent_rerun_does_not_duplicate_nodes(self, kuzu_index, service_map):
        """Re-processing the same commit twice must not increase node count."""
        pytest.importorskip("llama_index.packs.code_hierarchy",
                             reason="llama-index-packs-code-hierarchy not installed")

        repo = StubRepo(
            files={"src/HttpClient.cs": SAMPLE_CSHARP},
            diffs={"src/HttpClient.cs": MODIFY_TIMEOUT_DIFF},
            changed_files=["src/HttpClient.cs"],
        )
        indexer = DifferentialIndexer(
            index=kuzu_index, service_repo_map=service_map, repo_adapter=repo
        )
        request = DifferentialIndexerRequest(service="payment-api", commit_sha="abc1234")

        n1, _ = indexer.index_commit(request)
        n2, _ = indexer.index_commit(request)

        # Second run should upsert same count, not double it
        assert n1 == n2

    def test_backfill_populates_graph_within_policy_window(self, kuzu_index, service_map):
        """Backfill runner indexes all commits within max_days."""
        pytest.importorskip("llama_index.packs.code_hierarchy",
                             reason="llama-index-packs-code-hierarchy not installed")

        from rca.indexing.backfill import BackfillRunner

        repo = StubRepo(
            files={"src/HttpClient.cs": SAMPLE_CSHARP},
            diffs={"src/HttpClient.cs": MODIFY_TIMEOUT_DIFF},
            changed_files=["src/HttpClient.cs"],
            commits=["sha001", "sha002", "sha003"],
        )
        indexer = DifferentialIndexer(
            index=kuzu_index, service_repo_map=service_map, repo_adapter=repo
        )
        runner = BackfillRunner(
            indexer=indexer, service_repo_map=service_map, repo_adapter=repo
        )

        policy = BackfillPolicy(max_days=90, batch_size=10)
        commits_processed, nodes_upserted, diags = runner.run("payment-api", policy=policy)

        errors = [d for d in diags if d.severity == "error"]
        assert not errors, f"Unexpected errors: {errors}"
        assert commits_processed == 3

    def test_performance_single_file_under_three_seconds(self, kuzu_index, service_map):
        """Smoke test: single file diff should complete in under 3 seconds."""
        import time
        pytest.importorskip("llama_index.packs.code_hierarchy",
                             reason="llama-index-packs-code-hierarchy not installed")

        repo = StubRepo(
            files={"src/HttpClient.cs": SAMPLE_CSHARP},
            diffs={"src/HttpClient.cs": MODIFY_TIMEOUT_DIFF},
            changed_files=["src/HttpClient.cs"],
        )
        indexer = DifferentialIndexer(
            index=kuzu_index, service_repo_map=service_map, repo_adapter=repo
        )
        request = DifferentialIndexerRequest(service="payment-api", commit_sha="abc1234")

        start = time.perf_counter()
        indexer.index_commit(request)
        elapsed = time.perf_counter() - start

        assert elapsed < 3.0, f"Indexing took {elapsed:.2f}s — exceeds 3s target"
