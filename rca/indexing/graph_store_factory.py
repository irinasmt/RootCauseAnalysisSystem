"""Graph store factory — wires Neo4j (default) or Kuzu (local fallback).

Neo4j is the primary store.  It can be a local Docker instance or a free
Neo4j AuraDB cloud instance.  Connection details are read from environment
variables so nothing is hard-coded:

    NEO4J_URL       bolt://localhost:7687   (or neo4j+s://xxx.databases.neo4j.io)
    NEO4J_USERNAME  neo4j
    NEO4J_PASSWORD  your-password
    NEO4J_DATABASE  neo4j                  (optional, defaults to "neo4j")

Kuzu is kept as a zero-infra local fallback for CI / offline use.

Embedding model:
    LlamaIndex defaults to ``OpenAIEmbedding``.  This project is Gemini-first;
    call ``configure_gemini_embedding()`` before ``create_property_graph_index``.
    Use ``Settings.embed_model = MockEmbedding(embed_dim=8)`` for no-embed runs.

Example (Neo4j)::

    from rca.indexing.graph_store_factory import (
        configure_gemini_embedding, create_neo4j_store, create_property_graph_index
    )
    configure_gemini_embedding()          # reads GEMINI_API_KEY
    store = create_neo4j_store()          # reads NEO4J_* env vars
    index = create_property_graph_index(graph_store=store)

Example (Kuzu local fallback)::

    store = create_kuzu_store(persist_dir=".rca_graph")
    index = create_property_graph_index(graph_store=store)
"""

from __future__ import annotations

import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Embedding configuration
# ---------------------------------------------------------------------------

def configure_gemini_embedding(
    model_name: str = "models/text-embedding-004",
    api_key: str | None = None,
) -> None:
    """Override LlamaIndex's default OpenAI embedding with GeminiEmbedding.

    Must be called once at application startup, before any
    ``PropertyGraphIndex`` is constructed.

    Parameters
    ----------
    model_name:
        Gemini embedding model.  Defaults to ``models/text-embedding-004``.
    api_key:
        Gemini API key.  Defaults to the ``GEMINI_API_KEY`` environment
        variable (same key used by the Brain LLM client).
    """
    try:
        from llama_index.core import Settings  # type: ignore[import]
        from llama_index.embeddings.gemini import GeminiEmbedding  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "llama-index-embeddings-gemini is required. "
            "Install with: pip install llama-index-embeddings-gemini"
        ) from exc

    resolved_key = api_key or os.environ.get("GEMINI_API_KEY", "")
    Settings.embed_model = GeminiEmbedding(
        model_name=model_name,
        api_key=resolved_key,
    )


# ---------------------------------------------------------------------------
# Neo4j store  (primary)
# ---------------------------------------------------------------------------

def create_neo4j_store(
    url: str | None = None,
    username: str | None = None,
    password: str | None = None,
    database: str | None = None,
):
    """Return a ``Neo4jPropertyGraphStore`` using the supplied credentials.

    All parameters fall back to environment variables so nothing needs to be
    hard-coded:

    .. code-block:: text

        NEO4J_URL       bolt://localhost:7687
        NEO4J_USERNAME  neo4j
        NEO4J_PASSWORD  your-password
        NEO4J_DATABASE  neo4j   (optional)

    Local Docker quick-start::

        docker run --rm -p 7474:7474 -p 7687:7687 \\
            -e NEO4J_AUTH=neo4j/password neo4j:5

    Free cloud:  https://neo4j.com/cloud/platform/aura-graph-database/
    """
    try:
        from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "llama-index-graph-stores-neo4j is required. "
            "Install with: pip install llama-index-graph-stores-neo4j"
        ) from exc

    resolved_url      = url      or os.environ.get("NEO4J_URL",      "bolt://localhost:7687")
    resolved_username = username or os.environ.get("NEO4J_USERNAME", "neo4j")
    resolved_password = password or os.environ.get("NEO4J_PASSWORD", "")
    resolved_database = database or os.environ.get("NEO4J_DATABASE", "neo4j")

    if not resolved_password:
        raise ValueError(
            "Neo4j password is required.  Set NEO4J_PASSWORD in your .env file "
            "or pass password= explicitly to create_neo4j_store()."
        )

    return Neo4jPropertyGraphStore(
        url=resolved_url,
        username=resolved_username,
        password=resolved_password,
        database=resolved_database,
    )


# ---------------------------------------------------------------------------
# Kuzu store  (local / CI fallback)
# ---------------------------------------------------------------------------

def create_kuzu_store(persist_dir: str | Path = "./rca_graph"):
    """Return a ``KuzuPropertyGraphStore`` backed by a local Kuzu embedded DB.

    Use this when Neo4j is not available (offline CI, quick local experiments).
    Zero infrastructure required — the graph is stored in files under
    *persist_dir*.

    Parameters
    ----------
    persist_dir:
        Directory path for Kuzu database files.  Kuzu creates this itself;
        the parent directory is created if necessary.
    """
    try:
        import kuzu  # type: ignore[import]
        from llama_index.graph_stores.kuzu import KuzuPropertyGraphStore  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Kuzu and llama-index-graph-stores-kuzu are required. "
            "Install with: pip install kuzu llama-index-graph-stores-kuzu"
        ) from exc

    # Ensure parent exists but do NOT pre-create the target dir —
    # Kuzu initialises its own directory structure and rejects an empty pre-made dir.
    p = Path(persist_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    db = kuzu.Database(str(p))
    return KuzuPropertyGraphStore(db)


# ---------------------------------------------------------------------------
# Index factory
# ---------------------------------------------------------------------------

def create_property_graph_index(graph_store=None, persist_dir: str | Path = "./rca_graph"):
    """Return a ``PropertyGraphIndex`` wired to *graph_store*.

    If *graph_store* is ``None`` the factory attempts to create a
    ``Neo4jPropertyGraphStore`` from environment variables (``NEO4J_*``).
    Falls back to ``KuzuPropertyGraphStore`` under *persist_dir* if
    ``NEO4J_PASSWORD`` is not set.

    Inject any ``AbstractPropertyGraphStore`` explicitly to skip auto-detect.
    """
    try:
        from llama_index.core import StorageContext  # type: ignore[import]
        from llama_index.core.indices import PropertyGraphIndex  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "llama-index-core is required. Install with: pip install llama-index-core"
        ) from exc

    if graph_store is None:
        if os.environ.get("NEO4J_PASSWORD"):
            graph_store = create_neo4j_store()
        else:
            graph_store = create_kuzu_store(persist_dir)

    storage_context = StorageContext.from_defaults(property_graph_store=graph_store)
    return PropertyGraphIndex(
        nodes=[],
        storage_context=storage_context,
    )
