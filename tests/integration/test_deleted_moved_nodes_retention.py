"""Integration tests for deletion and move node retention in the graph.

Requires: kuzu, llama-index-core, llama-index-graph-stores-kuzu, unidiff
Skipped automatically if dependencies are not installed.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("llama_index.core", reason="llama-index-core not installed")
pytest.importorskip("kuzu", reason="kuzu not installed")
pytest.importorskip("llama_index.graph_stores.kuzu", reason="llama-index-graph-stores-kuzu not installed")
pytest.importorskip("unidiff", reason="unidiff not installed")

from rca.indexing.differential_indexer import (
    STATUS_DELETED,
    STATUS_MOVED,
    DifferentialIndexer,
)
from rca.indexing.graph_store_factory import create_property_graph_index
from rca.indexing.models import DifferentialIndexerRequest, RepoEntry
from rca.indexing.service_repo_map import InMemoryServiceRepoMap

DELETE_FILE_DIFF = """\
--- a/src/LegacyAuth.cs
+++ /dev/null
@@ -1,8 +0,0 @@
-public class LegacyAuth
-{
-    public void Authenticate() {}
-}
"""


class StubRepo:
    def __init__(self, diffs=None, changed_files=None):
        self._diffs = diffs or {}
        self._changed_files = changed_files or []

    def get_file(self, path, commit_sha):
        raise FileNotFoundError(f"File deleted: {path}")

    def get_diff(self, path, commit_sha):
        return self._diffs.get(path, "")

    def list_changed_files(self, commit_sha):
        return self._changed_files

    def list_commits(self, since_days, branch="main"):
        return []


@pytest.fixture()
def kuzu_index(tmp_path):
    return create_property_graph_index(persist_dir=str(tmp_path / "graph"))


@pytest.fixture()
def service_map():
    m = InMemoryServiceRepoMap()
    m.register("auth-svc", RepoEntry(repo_url="https://github.com/org/auth", language="csharp"))
    return m


class TestDeletedNodeRetention:
    def test_file_deletion_creates_tombstone_node(self, kuzu_index, service_map):
        """Deleting a file should produce a DELETED node in the graph."""
        repo = StubRepo(
            diffs={"src/LegacyAuth.cs": DELETE_FILE_DIFF},
            changed_files=["src/LegacyAuth.cs"],
        )
        indexer = DifferentialIndexer(
            index=kuzu_index, service_repo_map=service_map, repo_adapter=repo
        )

        with patch.object(indexer, "_query_nodes_by_path", return_value=[]):
            request = DifferentialIndexerRequest(
                service="auth-svc",
                commit_sha="del001",
                file_paths=["src/LegacyAuth.cs"],
            )
            n, diags = indexer.index_commit(request)

        errors = [d for d in diags if d.severity == "error"]
        assert not errors, f"Unexpected errors: {errors}"
        assert n >= 1

    def test_deleted_node_has_no_text_content(self, kuzu_index, service_map):
        """Tombstone node must have empty text (not the source code)."""
        from unittest.mock import MagicMock
        existing_node = MagicMock()
        existing_node.text = "class LegacyAuth {}"
        existing_node.metadata = {
            "file_path": "src/LegacyAuth.cs",
            "symbol_name": "LegacyAuth",
            "symbol_kind": "class",
        }

        repo = StubRepo(
            diffs={"src/LegacyAuth.cs": DELETE_FILE_DIFF},
        )
        indexer = DifferentialIndexer(
            index=kuzu_index, service_repo_map=service_map, repo_adapter=repo
        )

        with patch.object(indexer, "_query_nodes_by_path", return_value=[existing_node]):
            request = DifferentialIndexerRequest(
                service="auth-svc",
                commit_sha="del001",
                file_paths=["src/LegacyAuth.cs"],
            )
            indexer.index_commit(request)

        assert existing_node.text == ""
        assert existing_node.metadata["status"] == STATUS_DELETED

    def test_deleted_node_preserves_prior_path(self, kuzu_index, service_map):
        """The original file path must be retained in prior_path metadata."""
        from unittest.mock import MagicMock
        existing_node = MagicMock()
        existing_node.text = "class LegacyAuth {}"
        existing_node.metadata = {"file_path": "src/LegacyAuth.cs"}

        repo = StubRepo(diffs={"src/LegacyAuth.cs": DELETE_FILE_DIFF})
        indexer = DifferentialIndexer(
            index=kuzu_index, service_repo_map=service_map, repo_adapter=repo
        )

        with patch.object(indexer, "_query_nodes_by_path", return_value=[existing_node]):
            request = DifferentialIndexerRequest(
                service="auth-svc",
                commit_sha="del001",
                file_paths=["src/LegacyAuth.cs"],
            )
            indexer.index_commit(request)

        assert existing_node.metadata["prior_path"] == "src/LegacyAuth.cs"

    def test_error_diagnostic_on_upsert_failure(self, kuzu_index, service_map):
        """A failing upsert should produce an error diagnostic, not an exception."""
        repo = StubRepo(diffs={"src/LegacyAuth.cs": DELETE_FILE_DIFF})
        indexer = DifferentialIndexer(
            index=kuzu_index, service_repo_map=service_map, repo_adapter=repo
        )

        with (
            patch.object(indexer, "_query_nodes_by_path", return_value=[]),
            patch.object(indexer, "_upsert", side_effect=RuntimeError("DB down")),
        ):
            request = DifferentialIndexerRequest(
                service="auth-svc",
                commit_sha="del001",
                file_paths=["src/LegacyAuth.cs"],
            )
            n, diags = indexer.index_commit(request)

        assert n == 0
        assert any(d.severity == "error" for d in diags)
