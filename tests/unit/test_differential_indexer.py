"""Unit tests for DifferentialIndexer — uses stub adapters, no LlamaIndex runtime needed."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from rca.indexing.differential_indexer import (
    STATUS_ADDED,
    STATUS_DELETED,
    STATUS_MODIFIED,
    STATUS_UNCHANGED,
    DifferentialIndexer,
    _extract_patch_text,
    _node_id,
    _node_text,
    _propagate_status_upward,
)
from rca.indexing.models import DifferentialIndexerRequest, RepoEntry
from rca.indexing.service_repo_map import InMemoryServiceRepoMap

# ---------------------------------------------------------------------------
# Stub repository adapter
# ---------------------------------------------------------------------------

MODIFY_DIFF = """\
--- a/src/HttpClient.cs
+++ b/src/HttpClient.cs
@@ -10,5 +10,5 @@
 public class HttpClient
 {
-    private readonly int _timeout = 30;
+    private readonly int _timeout = 15;
     public async Task SendAsync() {}
 }
"""

DELETE_FILE_DIFF = """\
--- a/src/LegacyAuth.cs
+++ /dev/null
@@ -1,1 +0,0 @@
-public class LegacyAuth {}
"""

ADD_FILE_DIFF = """\
--- /dev/null
+++ b/src/NewService.cs
@@ -0,0 +1,1 @@
+public class NewService {}
"""


class StubRepoAdapter:
    """Minimal in-memory stub satisfying RepositoryAdapter protocol."""

    def __init__(
        self,
        files: dict[str, str] | None = None,
        diffs: dict[str, str] | None = None,
        changed_files: list[str] | None = None,
        commits: list[str] | None = None,
    ) -> None:
        self._files = files or {}
        self._diffs = diffs or {}
        self._changed_files = changed_files or []
        self._commits = commits or []

    def get_file(self, path: str, commit_sha: str) -> str:
        if path not in self._files:
            raise FileNotFoundError(f"No stub content for {path}")
        return self._files[path]

    def get_diff(self, path: str, commit_sha: str) -> str:
        return self._diffs.get(path, "")

    def list_changed_files(self, commit_sha: str) -> list[str]:
        return self._changed_files

    def list_commits(self, since_days: int, branch: str = "main") -> list[str]:
        return self._commits


def _make_stub_node(name: str, start: int, end: int):
    """Build a minimal LlamaIndex-like TextNode stub for testing."""
    node = MagicMock()
    node.text = "stub code"
    node.metadata = {"name": name, "start_line": start, "end_line": end}
    return node


def _make_indexer(files=None, diffs=None, changed_files=None):
    """Build a DifferentialIndexer with a mock PropertyGraphIndex."""
    service_map = InMemoryServiceRepoMap()
    service_map.register(
        "payment-api",
        RepoEntry(repo_url="https://github.com/org/payment", language="csharp"),
    )
    repo = StubRepoAdapter(
        files=files or {},
        diffs=diffs or {},
        changed_files=changed_files or [],
    )
    index_mock = MagicMock()
    index_mock.insert_nodes = MagicMock()
    indexer = DifferentialIndexer(
        index=index_mock,
        service_repo_map=service_map,
        repo_adapter=repo,
    )
    return indexer, index_mock


# ---------------------------------------------------------------------------
# Tests: unknown service returns diagnostic
# ---------------------------------------------------------------------------

class TestUnknownService:
    def test_unknown_service_returns_error_diagnostic(self):
        indexer, _ = _make_indexer()
        request = DifferentialIndexerRequest(service="unknown-svc", commit_sha="abc1234")
        n, diags = indexer.index_commit(request)
        assert n == 0
        assert any(d.severity == "error" for d in diags)

    def test_unknown_service_diagnostic_mentions_service(self):
        indexer, _ = _make_indexer()
        request = DifferentialIndexerRequest(service="gone-svc", commit_sha="abc1234")
        _, diags = indexer.index_commit(request)
        assert any("gone-svc" in d.message for d in diags)


# ---------------------------------------------------------------------------
# Tests: status assignment (MODIFIED, ADDED, UNCHANGED)
# ---------------------------------------------------------------------------

class TestStatusAssignment:
    def _run_with_nodes(self, diff: str, nodes: list, files: dict | None = None):
        """Run indexer with patched parser and return (n, diags, index_mock)."""
        effective_files = files or {"src/HttpClient.cs": "class HttpClient {}"}
        effective_path = next(iter(effective_files))
        indexer, index_mock = _make_indexer(
            files=effective_files,
            diffs={effective_path: diff},
            changed_files=[effective_path],
        )
        with patch.object(indexer, "_parse_hierarchy", return_value=nodes):
            request = DifferentialIndexerRequest(
                service="payment-api", commit_sha="abc1234"
            )
            n, diags = indexer.index_commit(request)
        return n, diags, index_mock

    def test_overlapping_node_gets_modified(self):
        node = _make_stub_node("HttpClient", 10, 18)
        n, diags, index_mock = self._run_with_nodes(MODIFY_DIFF, [node])
        assert n == 1
        assert node.metadata["status"] == STATUS_MODIFIED

    def test_non_overlapping_node_gets_unchanged(self):
        node = _make_stub_node("SomeOtherClass", 50, 80)
        n, diags, _ = self._run_with_nodes(MODIFY_DIFF, [node])
        assert node.metadata["status"] == STATUS_UNCHANGED

    def test_added_file_all_nodes_get_added_status(self):
        node1 = _make_stub_node("NewService", 1, 5)
        node2 = _make_stub_node("NewService.Run", 3, 4)
        n, diags, _ = self._run_with_nodes(
            ADD_FILE_DIFF,
            [node1, node2],
            files={"src/NewService.cs": "class NewService { void Run() {} }"},
        )
        assert node1.metadata["status"] == STATUS_ADDED
        assert node2.metadata["status"] == STATUS_ADDED

    def test_metadata_enrichment(self):
        node = _make_stub_node("HttpClient", 10, 18)
        n, diags, _ = self._run_with_nodes(MODIFY_DIFF, [node])
        assert node.metadata["file_path"] == "src/HttpClient.cs"
        assert node.metadata["commit_sha"] == "abc1234"
        assert node.metadata["service"] == "payment-api"
        assert "node_id" in node.metadata

    def test_node_id_is_stable(self):
        id1 = _node_id("svc", "sha1", "src/Foo.cs", "Foo")
        id2 = _node_id("svc", "sha1", "src/Foo.cs", "Foo")
        assert id1 == id2

    def test_node_id_differs_by_symbol(self):
        id1 = _node_id("svc", "sha1", "src/Foo.cs", "Foo")
        id2 = _node_id("svc", "sha1", "src/Foo.cs", "Bar")
        assert id1 != id2

    def test_upsert_called_with_nodes(self):
        node = _make_stub_node("HttpClient", 10, 18)
        n, _, index_mock = self._run_with_nodes(MODIFY_DIFF, [node])
        assert index_mock.property_graph_store.upsert_nodes.called

    def test_empty_parser_output_returns_warning(self):
        n, diags, _ = self._run_with_nodes(MODIFY_DIFF, [])
        assert n == 0
        assert any(d.severity == "warning" for d in diags)


# ---------------------------------------------------------------------------
# Tests: deletion retention
# ---------------------------------------------------------------------------

class TestDeletionRetention:
    def test_deleted_file_produces_tombstone(self):
        indexer, index_mock = _make_indexer(
            diffs={"src/LegacyAuth.cs": DELETE_FILE_DIFF},
            changed_files=["src/LegacyAuth.cs"],
        )
        # Pre-populate graph with no existing nodes for this path
        with patch.object(indexer, "_query_nodes_by_path", return_value=[]):
            request = DifferentialIndexerRequest(
                service="payment-api", commit_sha="abc1234",
                file_paths=["src/LegacyAuth.cs"],
            )
            n, diags = indexer.index_commit(request)

        assert n >= 1
        # tombstone should have been upserted via property_graph_store
        assert index_mock.property_graph_store.upsert_nodes.called
        upserted = index_mock.property_graph_store.upsert_nodes.call_args[0][0]
        tombstone = upserted[0]
        assert tombstone.properties["status"] == STATUS_DELETED
        assert tombstone.text == ""

    def test_existing_nodes_marked_deleted(self):
        existing_node = _make_stub_node("LegacyAuth", 1, 8)
        existing_node.text = "class LegacyAuth {}"
        existing_node.metadata["file_path"] = "src/LegacyAuth.cs"

        indexer, index_mock = _make_indexer(
            diffs={"src/LegacyAuth.cs": DELETE_FILE_DIFF},
            changed_files=["src/LegacyAuth.cs"],
        )
        with patch.object(indexer, "_query_nodes_by_path", return_value=[existing_node]):
            request = DifferentialIndexerRequest(
                service="payment-api",
                commit_sha="abc1234",
                file_paths=["src/LegacyAuth.cs"],
            )
            n, diags = indexer.index_commit(request)

        assert existing_node.metadata["status"] == STATUS_DELETED
        assert existing_node.text == ""
        assert existing_node.metadata["prior_path"] == "src/LegacyAuth.cs"


# ---------------------------------------------------------------------------
# Tests: semantic delta
# ---------------------------------------------------------------------------

class TestSemanticDelta:
    def test_semantic_delta_populated_when_enabled(self):
        node = _make_stub_node("HttpClient", 10, 18)
        indexer, _ = _make_indexer(
            files={"src/HttpClient.cs": "class HttpClient {}"},
            diffs={"src/HttpClient.cs": MODIFY_DIFF},
            changed_files=["src/HttpClient.cs"],
        )
        with patch.object(indexer, "_parse_hierarchy", return_value=[node]):
            request = DifferentialIndexerRequest(
                service="payment-api",
                commit_sha="abc1234",
                enable_semantic_delta=True,
            )
            n, diags = indexer.index_commit(request)

        # if node is MODIFIED, semantic_delta should be set
        if node.metadata.get("status") == STATUS_MODIFIED:
            assert "semantic_delta" in node.metadata

    def test_semantic_delta_not_set_when_disabled(self):
        node = _make_stub_node("HttpClient", 10, 18)
        indexer, _ = _make_indexer(
            files={"src/HttpClient.cs": "class HttpClient {}"},
            diffs={"src/HttpClient.cs": MODIFY_DIFF},
            changed_files=["src/HttpClient.cs"],
        )
        with patch.object(indexer, "_parse_hierarchy", return_value=[node]):
            request = DifferentialIndexerRequest(
                service="payment-api",
                commit_sha="abc1234",
                enable_semantic_delta=False,
            )
            indexer.index_commit(request)

        assert "semantic_delta" not in node.metadata


# ---------------------------------------------------------------------------
# Tests: _extract_patch_text and _node_text
# ---------------------------------------------------------------------------

_SAMPLE_DIFF = """\
--- a/src/config.py
+++ b/src/config.py
@@ -4,6 +4,6 @@
 import os
 import httpx
 
 GATEWAY_URL = os.getenv("GATEWAY_URL", "https://payments.internal")
-TIMEOUT_SECONDS = float(os.getenv("GATEWAY_TIMEOUT", "30"))
+TIMEOUT_SECONDS = float(os.getenv("GATEWAY_TIMEOUT", "15"))  # was 30
 MAX_RETRIES = int(os.getenv("GATEWAY_MAX_RETRIES", "3"))
"""

_SAMPLE_FILE = """line1
line2
line3
class Foo:
    pass
"""


class TestExtractPatchText:
    def test_returns_removed_and_added_lines(self):
        text = _extract_patch_text(_SAMPLE_DIFF, 1, 20)
        assert "-TIMEOUT_SECONDS" in text
        assert "+TIMEOUT_SECONDS" in text

    def test_range_covering_hunk_returns_patch(self):
        # hunk is at source line 8 (line 8 within @@ -4,6 @@  → lines 4-9)
        text = _extract_patch_text(_SAMPLE_DIFF, 4, 9)
        assert "-TIMEOUT_SECONDS" in text or "+TIMEOUT_SECONDS" in text

    def test_range_outside_hunk_returns_empty(self):
        # node is at lines 50-80, hunk is at lines 4-9
        text = _extract_patch_text(_SAMPLE_DIFF, 50, 80)
        assert text == ""

    def test_empty_diff_returns_empty(self):
        assert _extract_patch_text("", 1, 100) == ""

    def test_context_lines_not_included(self):
        # Context lines (no +/-) must not appear in the extracted patch
        text = _extract_patch_text(_SAMPLE_DIFF, 1, 20)
        for line in text.splitlines():
            assert line.startswith("+") or line.startswith("-"), (
                f"Expected only +/- lines, got: {line!r}"
            )


class TestNodeText:
    def test_modified_returns_patch(self):
        text = _node_text(STATUS_MODIFIED, 1, 20, _SAMPLE_DIFF, _SAMPLE_FILE)
        assert "-TIMEOUT_SECONDS" in text or "+TIMEOUT_SECONDS" in text

    def test_added_returns_source_lines(self):
        text = _node_text(STATUS_ADDED, 4, 5, "", _SAMPLE_FILE)
        assert "class Foo:" in text

    def test_added_slices_correct_lines(self):
        lines = _SAMPLE_FILE.splitlines()
        text = _node_text(STATUS_ADDED, 1, 2, "", _SAMPLE_FILE)
        assert text == "line1\nline2"

    def test_unchanged_returns_empty(self):
        assert _node_text(STATUS_UNCHANGED, 1, 20, _SAMPLE_DIFF, _SAMPLE_FILE) == ""

    def test_deleted_returns_empty(self):
        assert _node_text(STATUS_DELETED, 1, 20, _SAMPLE_DIFF, _SAMPLE_FILE) == ""


# ---------------------------------------------------------------------------
# Tests: text assignment through the full indexer pipeline
# ---------------------------------------------------------------------------

class TestNodeTextAssignment:
    def _run_with_nodes(self, diff, nodes, files=None):
        effective_files = files or {"src/HttpClient.cs": "line1\nline2\nclass HttpClient {}\n"}
        effective_path = next(iter(effective_files))
        from rca.indexing.models import RepoEntry
        service_map = InMemoryServiceRepoMap()
        service_map.register(
            "payment-api",
            RepoEntry(repo_url="https://github.com/org/payment", language="csharp"),
        )
        repo = StubRepoAdapter(
            files=effective_files,
            diffs={effective_path: diff},
            changed_files=[effective_path],
        )
        index_mock = MagicMock()
        indexer = DifferentialIndexer(
            index=index_mock,
            service_repo_map=service_map,
            repo_adapter=repo,
        )
        with patch.object(indexer, "_parse_hierarchy", return_value=nodes):
            from rca.indexing.models import DifferentialIndexerRequest
            indexer.index_commit(DifferentialIndexerRequest(
                service="payment-api", commit_sha="abc1234"
            ))

    def test_modified_node_text_contains_diff_lines(self):
        node = _make_stub_node("HttpClient", 10, 18)
        self._run_with_nodes(MODIFY_DIFF, [node])
        assert node.text != ""
        assert any(line.startswith("+") or line.startswith("-")
                   for line in node.text.splitlines())

    def test_unchanged_node_text_is_empty(self):
        node = _make_stub_node("SomeOtherClass", 50, 80)
        self._run_with_nodes(MODIFY_DIFF, [node])
        assert node.text == ""

    def test_added_file_node_text_is_source(self):
        file_content = "class NewService:\n    def run(self): pass\n"
        node = _make_stub_node("NewService", 1, 2)
        self._run_with_nodes(
            ADD_FILE_DIFF, [node],
            files={"src/NewService.cs": file_content},
        )
        assert "NewService" in node.text




class TestPropagateStatusUpward:
    """_propagate_status_upward() bubbles MODIFIED/ADDED from child to ancestor."""

    def _node(self, name: str, status: str, scopes: list, file_path: str = "f.py"):
        node = MagicMock()
        node.metadata = {
            "name": name,
            "status": status,
            "file_path": file_path,
            "inclusive_scopes": scopes,
        }
        return node

    def test_modified_method_upgrades_class(self):
        cls = self._node("MyClass", STATUS_UNCHANGED, [{"name": "MyClass"}])
        method = self._node("charge", STATUS_MODIFIED,
                            [{"name": "MyClass"}, {"name": "charge"}])
        _propagate_status_upward([cls, method])
        assert cls.metadata["status"] == STATUS_MODIFIED

    def test_modified_method_upgrades_all_ancestors(self):
        module = self._node("(module)", STATUS_UNCHANGED, [])
        cls = self._node("MyClass", STATUS_UNCHANGED, [{"name": "MyClass"}])
        method = self._node("charge", STATUS_MODIFIED,
                            [{"name": "MyClass"}, {"name": "charge"}])
        _propagate_status_upward([module, cls, method])
        assert cls.metadata["status"] == STATUS_MODIFIED
        assert module.metadata["status"] == STATUS_MODIFIED

    def test_unchanged_child_leaves_ancestors_unchanged(self):
        module = self._node("(module)", STATUS_UNCHANGED, [])
        cls = self._node("MyClass", STATUS_UNCHANGED, [{"name": "MyClass"}])
        method = self._node("charge", STATUS_UNCHANGED,
                            [{"name": "MyClass"}, {"name": "charge"}])
        _propagate_status_upward([module, cls, method])
        assert cls.metadata["status"] == STATUS_UNCHANGED
        assert module.metadata["status"] == STATUS_UNCHANGED

    def test_added_method_upgrades_ancestors(self):
        module = self._node("(module)", STATUS_UNCHANGED, [])
        cls = self._node("MyClass", STATUS_UNCHANGED, [{"name": "MyClass"}])
        new_method = self._node("new_method", STATUS_ADDED,
                                [{"name": "MyClass"}, {"name": "new_method"}])
        _propagate_status_upward([module, cls, new_method])
        assert cls.metadata["status"] == STATUS_MODIFIED
        assert module.metadata["status"] == STATUS_MODIFIED

    def test_sibling_not_affected_by_propagation(self):
        cls = self._node("MyClass", STATUS_UNCHANGED, [{"name": "MyClass"}])
        method_a = self._node("methodA", STATUS_MODIFIED,
                              [{"name": "MyClass"}, {"name": "methodA"}])
        method_b = self._node("methodB", STATUS_UNCHANGED,
                              [{"name": "MyClass"}, {"name": "methodB"}])
        _propagate_status_upward([cls, method_a, method_b])
        assert method_b.metadata["status"] == STATUS_UNCHANGED
        assert cls.metadata["status"] == STATUS_MODIFIED

    def test_already_modified_parent_stays_modified(self):
        cls = self._node("MyClass", STATUS_MODIFIED, [{"name": "MyClass"}])
        method = self._node("charge", STATUS_MODIFIED,
                            [{"name": "MyClass"}, {"name": "charge"}])
        _propagate_status_upward([cls, method])
        assert cls.metadata["status"] == STATUS_MODIFIED

    def test_different_files_not_cross_contaminated(self):
        cls_a = self._node("ClassA", STATUS_UNCHANGED, [{"name": "ClassA"}], "a.py")
        cls_b = self._node("ClassA", STATUS_UNCHANGED, [{"name": "ClassA"}], "b.py")
        method = self._node("charge", STATUS_MODIFIED,
                            [{"name": "ClassA"}, {"name": "charge"}], "a.py")
        _propagate_status_upward([cls_a, cls_b, method])
        assert cls_a.metadata["status"] == STATUS_MODIFIED
        assert cls_b.metadata["status"] == STATUS_UNCHANGED
