"""Unit tests for graph_store_factory wiring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestGraphStoreFactory:
    def test_create_kuzu_store_raises_import_error_when_kuzu_missing(self):
        """Without the kuzu package installed, factory should raise ImportError."""
        import sys
        # Temporarily hide kuzu if installed
        kuzu_mod = sys.modules.pop("kuzu", None)
        llama_kuzu_mod = sys.modules.pop("llama_index.graph_stores.kuzu", None)
        try:
            # Re-import factory with patched imports
            with patch.dict("sys.modules", {"kuzu": None, "llama_index.graph_stores.kuzu": None}):
                from rca.indexing import graph_store_factory
                import importlib
                importlib.reload(graph_store_factory)
                with pytest.raises(ImportError, match="kuzu"):
                    graph_store_factory.create_kuzu_store("./tmp_test_graph")
        finally:
            if kuzu_mod is not None:
                sys.modules["kuzu"] = kuzu_mod
            if llama_kuzu_mod is not None:
                sys.modules["llama_index.graph_stores.kuzu"] = llama_kuzu_mod

    def test_create_property_graph_index_uses_injected_store(self):
        """factory should wire a provided store without creating Kuzu."""
        mock_store = MagicMock()
        mock_index = MagicMock()

        with (
            patch("rca.indexing.graph_store_factory.create_kuzu_store") as mock_kuzu,
            patch("rca.indexing.graph_store_factory.create_property_graph_index",
                  return_value=mock_index) as mock_factory,
        ):
            from rca.indexing.graph_store_factory import create_property_graph_index
            result = create_property_graph_index(graph_store=mock_store)

        # When injected store is provided, kuzu factory should not be called
        mock_kuzu.assert_not_called()
