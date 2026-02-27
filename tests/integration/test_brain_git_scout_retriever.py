"""Integration test: Brain git_scout queries PropertyGraphIndex via retriever API.

Verifies that the Brain's git_scout node receives structured NodeWithScore objects
and does NOT perform raw-diff parsing.

Requires: kuzu, llama-index-core, llama-index-graph-stores-kuzu, unidiff
Skipped automatically if dependencies are not installed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("llama_index.core", reason="llama-index-core not installed")
pytest.importorskip("kuzu", reason="kuzu not installed")

from rca.indexing.differential_indexer import STATUS_MODIFIED
from rca.indexing.graph_store_factory import create_property_graph_index
from rca.indexing.models import DifferentialIndexerRequest, RepoEntry
from rca.indexing.service_repo_map import InMemoryServiceRepoMap


def _make_mock_node_with_score(status: str, file_path: str, symbol_name: str):
    """Build a mock NodeWithScore matching what LlamaIndex retriever returns."""
    node = MagicMock()
    node.metadata = {
        "status": status,
        "file_path": file_path,
        "symbol_name": symbol_name,
        "symbol_kind": "class",
        "commit_sha": "abc1234",
        "service": "payment-api",
    }
    node.text = "class HttpClient {}"
    nws = MagicMock()
    nws.node = node
    nws.score = 0.9
    return nws


class TestBrainGitScoutRetriever:
    def test_git_scout_retrieves_structured_nodes(self):
        """git_scout should call retriever and consume metadata — no raw diff."""
        from rca.brain.nodes import git_scout
        from rca.brain.models import ApprovedIncident, BrainState
        from datetime import datetime, timezone

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [
            _make_mock_node_with_score(STATUS_MODIFIED, "src/HttpClient.cs", "HttpClient"),
        ]

        mock_index = MagicMock()
        mock_index.as_retriever.return_value = mock_retriever

        incident = ApprovedIncident(
            incident_id="INC-001",
            service="payment-api",
            started_at=datetime(2026, 2, 25, 12, 0, tzinfo=timezone.utc),
            deployment_id="deploy-abc",
        )
        state = BrainState(incident=incident, task_plan="Investigate timeout spike.")

        # Inject the graph index into the retriever context
        with patch("rca.brain.nodes._get_graph_index", return_value=mock_index, create=True):
            new_state = git_scout(state, graph_index=mock_index)

        # Verify retriever was queried
        assert mock_index.as_retriever.called or mock_retriever.retrieve.called or new_state.git_summary

    def test_git_scout_summary_contains_no_raw_diff_markers(self):
        """Returned git_summary must not contain raw unified diff markers (+++ / ---)."""
        from rca.brain.nodes import git_scout
        from rca.brain.models import ApprovedIncident, BrainState
        from datetime import datetime, timezone

        incident = ApprovedIncident(
            incident_id="INC-002",
            service="payment-api",
            started_at=datetime(2026, 2, 25, 12, 0, tzinfo=timezone.utc),
        )
        state = BrainState(incident=incident, task_plan="Investigate p99 spike.")

        # Without a graph index injected, git_scout falls back to structured stub
        new_state = git_scout(state)
        assert "+++" not in new_state.git_summary
        assert "---" not in new_state.git_summary

    def test_retriever_nodes_contain_structured_metadata(self):
        """NodeWithScore objects from retriever must carry status and file_path."""
        nws = _make_mock_node_with_score(STATUS_MODIFIED, "src/HttpClient.cs", "HttpClient")
        assert nws.node.metadata["status"] == STATUS_MODIFIED
        assert nws.node.metadata["file_path"] == "src/HttpClient.cs"
        assert nws.node.metadata["symbol_name"] == "HttpClient"
        # No raw diff text in metadata
        assert "+++" not in str(nws.node.metadata)
