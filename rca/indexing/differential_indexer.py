"""Core Differential Indexer — parse → project → upsert."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from .models import (
    DifferentialIndexerRequest,
    IndexingDiagnostic,
    RepositoryAdapter,
)
from .service_repo_map import ServiceRepoMap

if TYPE_CHECKING:
    pass

# Node status constants — stored in TextNode.metadata["status"]
STATUS_ADDED = "ADDED"
STATUS_MODIFIED = "MODIFIED"
STATUS_UNCHANGED = "UNCHANGED"
STATUS_DELETED = "DELETED"
STATUS_MOVED = "MOVED"


class _SimpleNode:
    """Duck-typed node used when llama-index is not installed (unit tests).

    Provides the same ``.text`` / ``.metadata`` interface as ``TextNode``
    so the rest of the indexer pipeline works without a full LlamaIndex
    installation.
    """

    def __init__(self, text: str = "", metadata: dict | None = None) -> None:
        self.text = text
        self.metadata = metadata or {}


def _make_node(text: str = "", metadata: dict | None = None):
    """Return a TextNode if llama-index is installed, else a _SimpleNode."""
    try:
        from llama_index.core.schema import TextNode  # type: ignore[import]
        return TextNode(text=text, metadata=metadata or {})
    except ImportError:
        return _SimpleNode(text=text, metadata=metadata or {})


def _node_id(service: str, commit_sha: str, file_path: str, symbol_name: str) -> str:
    """Stable deterministic node identity across upserts."""
    raw = f"{service}:{file_path}:{symbol_name}"
    return hashlib.sha1(raw.encode()).hexdigest()  # noqa: S324 — not used for security


_PRIMITIVE = (str, int, float, bool)


def _enrich_node_positions(nodes: list, file_content: str) -> None:
    """Add ``name``, ``start_line``, ``end_line`` to each node's metadata in-place.

    CodeHierarchyNodeParser emits ``start_byte`` / ``end_byte`` and buries the
    symbol name inside ``inclusive_scopes``.  This helper converts byte offsets
    to 1-based line numbers and surfaces the innermost scope name so that:

    * diff-hunk overlap checks work (they compare line numbers)
    * every node gets a distinct ``name`` → distinct ``node_id``
    * Neo4j Browser can label nodes meaningfully
    """
    for node in nodes:
        meta = node.metadata

        # --- symbol name from innermost scope --------------------------------
        scopes = meta.get("inclusive_scopes", [])
        if isinstance(scopes, list) and scopes:
            # scopes is a list of dicts: [{name, type, signature}, ...]
            innermost = scopes[-1]
            if isinstance(innermost, dict):
                meta.setdefault("name", innermost.get("name", ""))
                meta.setdefault("symbol_kind", innermost.get("type", ""))
        if not meta.get("name"):
            meta["name"] = "(module)"

        # --- byte → line conversion ------------------------------------------
        if "start_line" not in meta and "start_byte" in meta:
            sb = int(meta["start_byte"])
            eb = int(meta.get("end_byte", len(file_content)))
            meta["start_line"] = file_content[:sb].count("\n") + 1
            meta["end_line"]   = file_content[:eb].count("\n") + 1


def _build_contains_relations(nodes: list) -> list:
    """Derive CONTAINS edges from ``inclusive_scopes`` nesting.

    ``CodeHierarchyNodeParser`` stores the enclosing scope chain in each
    node's ``inclusive_scopes`` metadata field::

        module      → inclusive_scopes = []
        class Foo   → inclusive_scopes = [{'name': 'Foo', 'type': 'class_definition'}]
        def bar     → inclusive_scopes = [{'name': 'Foo', ...}, {'name': 'bar', ...}]

    A parent→child CONTAINS relation exists whenever one node's scope chain
    is exactly one entry shorter than another's (same prefix).
    """
    try:
        from llama_index.core.graph_stores.types import Relation  # type: ignore[import]
    except ImportError:
        return []

    # Group by file so lookups stay O(nodes_per_file)
    from collections import defaultdict
    by_file: dict[str, list] = defaultdict(list)
    for n in nodes:
        by_file[n.metadata.get("file_path", "")].append(n)

    relations = []
    for file_nodes in by_file.values():
        # Build scope-tuple → node_id map
        scope_to_id: dict[tuple, str] = {}
        for n in file_nodes:
            scopes = _raw_scopes(n)
            key = tuple(s.get("name", "") for s in scopes if isinstance(s, dict))
            scope_to_id[key] = n.metadata.get("node_id", "")

        for n in file_nodes:
            scopes = _raw_scopes(n)
            if not scopes:
                continue  # module-level node — no parent
            my_key = tuple(s.get("name", "") for s in scopes if isinstance(s, dict))
            parent_key = my_key[:-1]
            parent_id = scope_to_id.get(parent_key, "")
            child_id = n.metadata.get("node_id", "")
            if parent_id and child_id and parent_id != child_id:
                relations.append(Relation(
                    source_id=parent_id,
                    target_id=child_id,
                    label="CONTAINS",
                ))

    return relations


def _propagate_status_upward(nodes: list) -> None:
    """Bubble MODIFIED/ADDED status from child nodes up to their ancestors in-place.

    If a method inside a class is MODIFIED, the enclosing class (and the module
    above it) should also be MODIFIED — a change inside a child is by definition
    a change within the parent's source range.

    Only UNCHANGED ancestors are upgraded; ADDED/DELETED/MOVED are not touched.
    Propagation is bounded to nodes in the same file.
    """
    from collections import defaultdict

    by_file: dict[str, list] = defaultdict(list)
    for n in nodes:
        by_file[n.metadata.get("file_path", "")].append(n)

    for file_nodes in by_file.values():
        # Map scope-key tuple → node for O(1) ancestor lookup
        scope_to_node: dict[tuple, object] = {}
        for n in file_nodes:
            scopes = _raw_scopes(n)
            key = tuple(s.get("name", "") for s in scopes if isinstance(s, dict))
            scope_to_node[key] = n

        for n in file_nodes:
            if n.metadata.get("status") not in (STATUS_MODIFIED, STATUS_ADDED):
                continue
            scopes = _raw_scopes(n)
            key = tuple(s.get("name", "") for s in scopes if isinstance(s, dict))
            # Walk every ancestor (shorter prefix) and upgrade UNCHANGED → MODIFIED
            for depth in range(len(key) - 1, -1, -1):
                ancestor = scope_to_node.get(key[:depth])
                if ancestor is None:
                    continue
                if ancestor.metadata.get("status") == STATUS_UNCHANGED:
                    ancestor.metadata["status"] = STATUS_MODIFIED


def _raw_scopes(node) -> list:
    """Return ``inclusive_scopes`` as a list of dicts, before JSON serialisation."""
    import json
    scopes = node.metadata.get("inclusive_scopes", [])
    if isinstance(scopes, str):
        try:
            scopes = json.loads(scopes)
        except Exception:  # noqa: BLE001
            return []
    return scopes if isinstance(scopes, list) else []


def _sanitize_properties(props: dict) -> dict:
    """Return a copy of *props* safe for Neo4j / Kuzu property storage.

    Graph stores only accept primitive values (str, int, float, bool) or
    homogeneous lists of primitives.  Any nested dicts or mixed-type lists
    (e.g. ``inclusive_scopes`` from CodeHierarchyNodeParser) are serialised
    to JSON strings so no metadata is silently lost.
    """
    import json

    clean: dict = {}
    for k, v in props.items():
        if v is None:
            continue  # skip nulls — graph stores vary in how they handle them
        if isinstance(v, _PRIMITIVE):
            clean[k] = v
        elif isinstance(v, list):
            # Keep list only if every element is a primitive
            if all(isinstance(el, _PRIMITIVE) for el in v):
                clean[k] = v
            else:
                clean[k] = json.dumps(v)
        elif isinstance(v, dict):
            clean[k] = json.dumps(v)
        else:
            clean[k] = str(v)
    return clean


_HUNK_HEADER_RE = __import__("re").compile(
    r"^@@ -(?P<start>\d+)(?:,(?P<length>\d+))? \+", __import__("re").MULTILINE
)


def _parse_hunks(raw_diff: str) -> list[tuple[int, int]]:
    """Parse a unified diff into (source_start, source_end) line ranges.

    Primary path: ``unidiff.PatchSet`` for accurate parsing.
    Fallback: regex over ``@@ -start,length +...  @@`` headers when PatchSet
    raises (e.g. mock diffs with imprecise context-line counts).  The fallback
    is intentionally permissive — it trusts the header numbers rather than
    re-validating the hunk body.

    Returns 1-based inclusive ``(start, end)`` tuples.
    """
    try:
        from unidiff import PatchSet  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "unidiff is required for diff projection. Install with: pip install unidiff"
        ) from exc

    try:
        patch = PatchSet.from_string(raw_diff)
        ranges: list[tuple[int, int]] = []
        for patched_file in patch:
            for hunk in patched_file:
                start = hunk.source_start
                length = max(hunk.source_length, 1)
                ranges.append((start, start + length - 1))
        return ranges
    except Exception:  # noqa: BLE001 — fall through to regex fallback
        pass

    # Regex fallback: parse @@ -start,length headers directly.
    ranges = []
    for m in _HUNK_HEADER_RE.finditer(raw_diff):
        start = int(m.group("start"))
        length = int(m.group("length")) if m.group("length") is not None else 1
        ranges.append((start, start + max(length, 1) - 1))
    return ranges


def _overlaps(node_start: int, node_end: int, hunk_ranges: list[tuple[int, int]]) -> bool:
    """Return True if the node's line range overlaps any hunk range."""
    for h_start, h_end in hunk_ranges:
        if node_start <= h_end and node_end >= h_start:
            return True
    return False


def _extract_patch_text(raw_diff: str, node_start: int, node_end: int) -> str:
    """Return the ±lines from *raw_diff* whose source position falls within
    [node_start, node_end] (1-based, inclusive).

    Primary path uses ``unidiff`` for accurate line tracking.  Falls back to a
    manual parser when PatchSet raises (e.g. imprecise mock diffs).
    """
    try:
        from unidiff import PatchSet  # type: ignore[import]
        patch = PatchSet.from_string(raw_diff)
        lines: list[str] = []
        for patched_file in patch:
            for hunk in patched_file:
                h_start = hunk.source_start
                h_end = h_start + max(hunk.source_length, 1) - 1
                if not (node_start <= h_end and node_end >= h_start):
                    continue
                source_line = hunk.source_start
                for line in hunk:
                    if line.is_removed:
                        if node_start <= source_line <= node_end:
                            lines.append(f"-{line.value.rstrip()}")  
                        source_line += 1
                    elif line.is_added:
                        # +lines don't advance source counter but belong to the same hunk
                        lines.append(f"+{line.value.rstrip()}")
                    else:  # context
                        source_line += 1
        return "\n".join(lines)
    except Exception:  # noqa: BLE001 — fall through to manual parser
        pass

    # Manual fallback — track source line counter through hunk body
    result: list[str] = []
    in_hunk = False
    source_line = 0
    for raw_line in raw_diff.splitlines():
        m = _HUNK_HEADER_RE.match(raw_line)
        if m:
            source_line = int(m.group("start"))
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if raw_line.startswith("-") and not raw_line.startswith("---"):
            if node_start <= source_line <= node_end:
                result.append(raw_line)
            source_line += 1
        elif raw_line.startswith("+") and not raw_line.startswith("+++"):
            result.append(raw_line)
        elif not raw_line.startswith("\\\\"):
            source_line += 1
    return "\n".join(result)


def _node_text(
    status: str,
    node_start: int,
    node_end: int,
    raw_diff: str,
    file_content: str,
) -> str:
    """Return the text to store on a graph node based on its status.

    * MODIFIED  → diff patch lines (±) overlapping the node's line range.
                  Gives the Brain the old *and* new values without full source.
    * ADDED     → full source lines for the node range (everything is new).
    * UNCHANGED → empty string — no change, structural context only.
    * DELETED   → empty string — handled upstream; included here for completeness.
    """
    if status == STATUS_MODIFIED:
        return _extract_patch_text(raw_diff, node_start, node_end)
    if status == STATUS_ADDED:
        source_lines = file_content.splitlines()
        # node lines are 1-based inclusive
        return "\n".join(source_lines[node_start - 1 : node_end])
    return ""


def _is_file_deleted(raw_diff: str) -> bool:
    """Return True when the diff represents a complete file deletion."""
    try:
        from unidiff import PatchSet  # type: ignore[import]
    except ImportError:  # pragma: no cover
        return False

    try:
        patch = PatchSet.from_string(raw_diff)
    except Exception:  # noqa: BLE001
        return False

    for f in patch:
        if f.is_removed_file:
            return True
    return False


def _is_file_added(raw_diff: str) -> bool:
    """Return True when the diff represents a newly added file."""
    try:
        from unidiff import PatchSet  # type: ignore[import]
    except ImportError:  # pragma: no cover
        return False

    try:
        patch = PatchSet.from_string(raw_diff)
    except Exception:  # noqa: BLE001
        return False

    for f in patch:
        if f.is_added_file:
            return True
    return False


class DifferentialIndexer:
    """Orchestrates: parse hierarchy → project diff → upsert into PropertyGraphIndex.

    Parameters
    ----------
    index:
        A LlamaIndex ``PropertyGraphIndex`` instance. Injected — caller controls
        which ``PropertyGraphStore`` backend is wired (Kuzu, Neo4j, etc.).
    service_repo_map:
        ``ServiceRepoMap`` implementation that resolves service → repo/language.
    repo_adapter:
        ``RepositoryAdapter`` implementation that fetches file content and diffs.
    """

    def __init__(
        self,
        index,
        service_repo_map: ServiceRepoMap,
        repo_adapter: RepositoryAdapter,
    ) -> None:
        self._index = index
        self._service_repo_map = service_repo_map
        self._repo = repo_adapter

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_commit(
        self, request: DifferentialIndexerRequest
    ) -> tuple[int, list[IndexingDiagnostic]]:
        """Index all changed files for a single commit.

        Returns
        -------
        (nodes_upserted, diagnostics)
            *nodes_upserted* — how many nodes were written to the graph.
            *diagnostics* — list of warnings/errors raised during processing.
        """
        diagnostics: list[IndexingDiagnostic] = []

        # Resolve service → repo entry (fail fast with diagnostic if missing)
        try:
            repo_entry = self._service_repo_map.get(request.service)
        except KeyError as exc:
            diagnostics.append(IndexingDiagnostic(
                severity="error",
                stage="resolve",
                message=str(exc),
                commit_sha=request.commit_sha,
            ))
            return 0, diagnostics

        # Determine target files
        file_paths = request.file_paths
        if not file_paths:
            try:
                file_paths = self._repo.list_changed_files(request.commit_sha)
            except Exception as exc:  # noqa: BLE001
                diagnostics.append(IndexingDiagnostic(
                    severity="error",
                    stage="list_files",
                    message=f"Could not list changed files: {exc}",
                    commit_sha=request.commit_sha,
                ))
                return 0, diagnostics

        total_upserted = 0
        for path in file_paths:
            upserted, file_diags = self._index_file(
                path=path,
                service=request.service,
                commit_sha=request.commit_sha,
                language=repo_entry.language,
                enable_semantic_delta=request.enable_semantic_delta,
            )
            total_upserted += upserted
            diagnostics.extend(file_diags)

        return total_upserted, diagnostics

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _index_file(
        self,
        path: str,
        service: str,
        commit_sha: str,
        language: str,
        enable_semantic_delta: bool,
    ) -> tuple[int, list[IndexingDiagnostic]]:
        diagnostics: list[IndexingDiagnostic] = []

        # Fetch diff first — always available even for deletions
        try:
            raw_diff = self._repo.get_diff(path, commit_sha)
        except Exception as exc:  # noqa: BLE001
            diagnostics.append(IndexingDiagnostic(
                severity="error", stage="diff",
                message=f"get_diff failed: {exc}",
                file_path=path, commit_sha=commit_sha,
            ))
            return 0, diagnostics

        file_deleted = _is_file_deleted(raw_diff)
        file_added = _is_file_added(raw_diff)

        # For deletions we cannot fetch current file content —
        # emit retention nodes directly from graph state.
        if file_deleted:
            return self._retain_deleted_nodes(
                path=path, service=service, commit_sha=commit_sha,
                diagnostics=diagnostics,
            )

        # Fetch current file content
        try:
            file_content = self._repo.get_file(path, commit_sha)
        except Exception as exc:  # noqa: BLE001
            diagnostics.append(IndexingDiagnostic(
                severity="error", stage="parse",
                message=f"get_file failed: {exc}",
                file_path=path, commit_sha=commit_sha,
            ))
            return 0, diagnostics

        # Parse hierarchy via LlamaIndex CodeHierarchyNodeParser
        try:
            nodes = self._parse_hierarchy(
                file_content=file_content,
                language=language,
                path=path,
            )
        except Exception as exc:  # noqa: BLE001
            diagnostics.append(IndexingDiagnostic(
                severity="warning", stage="parse",
                message=f"Parser produced no nodes: {exc}",
                file_path=path, commit_sha=commit_sha,
            ))
            return 0, diagnostics

        if not nodes:
            diagnostics.append(IndexingDiagnostic(
                severity="warning", stage="parse",
                message="CodeHierarchyNodeParser returned 0 nodes — file may be unsupported.",
                file_path=path, commit_sha=commit_sha,
            ))
            return 0, diagnostics

        # Enrich nodes with name + line numbers before any hunk projection
        _enrich_node_positions(nodes, file_content)

        # Project diff hunk ranges onto node line ranges
        hunk_ranges = _parse_hunks(raw_diff)

        upsert_nodes = []
        for node in nodes:
            start = int(node.metadata.get("start_line", 0))
            end = int(node.metadata.get("end_line", 0))

            if file_added:
                status = STATUS_ADDED
            elif hunk_ranges and _overlaps(start, end, hunk_ranges):
                status = STATUS_MODIFIED
            else:
                status = STATUS_UNCHANGED

            # Enrich metadata — stable identity + change provenance
            name = node.metadata.get("name", "")
            node.metadata.update({
                "status": status,
                "file_path": path,
                "commit_sha": commit_sha,
                "service": service,
                "node_id": _node_id(service, commit_sha, path, f"{name}:{start}"),
            })

            if enable_semantic_delta and status == STATUS_MODIFIED:
                node.metadata["semantic_delta"] = self._summarize_delta(node, raw_diff)

            upsert_nodes.append(node)

        # Bubble MODIFIED/ADDED status up through the containment hierarchy:
        # a MODIFIED method makes its enclosing class (and module) MODIFIED too.
        _propagate_status_upward(upsert_nodes)

        # Set node.text according to final status (after propagation):
        #   MODIFIED  → diff patch lines (old/new values, not full source)
        #   ADDED     → full source for the node range
        #   UNCHANGED → "" (structure only, no embedding needed)
        for node in upsert_nodes:
            final_status = node.metadata.get("status", STATUS_UNCHANGED)
            start = int(node.metadata.get("start_line", 0))
            end = int(node.metadata.get("end_line", 0))
            node.text = _node_text(final_status, start, end, raw_diff, file_content)

        # Upsert into persistent graph (idempotent by node_id)
        try:
            self._upsert(upsert_nodes)
        except Exception as exc:  # noqa: BLE001
            diagnostics.append(IndexingDiagnostic(
                severity="error", stage="upsert",
                message=f"Graph upsert failed: {exc}",
                file_path=path, commit_sha=commit_sha,
            ))
            return 0, diagnostics

        # Upsert CONTAINS relationships derived from scope nesting
        # (best-effort — failure does not affect node count)
        try:
            relations = _build_contains_relations(upsert_nodes)
            self._upsert_relations(relations)
        except Exception:  # noqa: BLE001
            pass

        return len(upsert_nodes), diagnostics

    def _parse_hierarchy(self, file_content: str, language: str, path: str):
        """Parse code hierarchy using LlamaIndex CodeHierarchyNodeParser."""
        try:
            from llama_index.core import Document  # type: ignore[import]
            from llama_index.packs.code_hierarchy import CodeHierarchyNodeParser  # type: ignore[import]
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "llama-index-core and llama-index-packs-code-hierarchy are required. "
                "Install with: pip install llama-index-core llama-index-packs-code-hierarchy"
            ) from exc

        parser = CodeHierarchyNodeParser(language=language)
        doc = Document(text=file_content, metadata={"file_path": path})
        return parser.get_nodes_from_documents([doc])

    def _retain_deleted_nodes(
        self,
        path: str,
        service: str,
        commit_sha: str,
        diagnostics: list[IndexingDiagnostic],
    ) -> tuple[int, list[IndexingDiagnostic]]:
        """Mark all existing graph nodes for *path* as DELETED.

        Nodes are updated in-place — text content is cleared, status is set to
        DELETED, and prior path + commit provenance are preserved as metadata.
        This ensures the Brain's retriever can still find and reason over symbols
        that no longer exist in the repository.
        """

        # Retrieve existing nodes for this path from the graph
        existing = self._query_nodes_by_path(path)

        if not existing:
            # Nothing to retain — emit a single file-level tombstone
            tombstone = _make_node(
                text="",
                metadata={
                    "status": STATUS_DELETED,
                    "file_path": path,
                    "prior_path": path,
                    "commit_sha": commit_sha,
                    "service": service,
                    "symbol_name": path,
                    "symbol_kind": "file",
                    "node_id": _node_id(service, commit_sha, path, path),
                },
            )
            try:
                self._upsert([tombstone])
                return 1, diagnostics
            except Exception as exc:  # noqa: BLE001
                diagnostics.append(IndexingDiagnostic(
                    severity="error", stage="upsert",
                    message=f"Tombstone upsert failed: {exc}",
                    file_path=path, commit_sha=commit_sha,
                ))
                return 0, diagnostics

        updated = []
        for node in existing:
            node.text = ""
            node.metadata["status"] = STATUS_DELETED
            node.metadata["prior_path"] = node.metadata.get("file_path", path)
            node.metadata["commit_sha"] = commit_sha
            updated.append(node)

        try:
            self._upsert(updated)
        except Exception as exc:  # noqa: BLE001
            diagnostics.append(IndexingDiagnostic(
                severity="error", stage="upsert",
                message=f"Deletion retention upsert failed: {exc}",
                file_path=path, commit_sha=commit_sha,
            ))
            return 0, diagnostics

        return len(updated), diagnostics

    def _upsert_relations(self, relations: list) -> None:
        """Upsert *relations* into the persistent graph store."""
        if not relations:
            return
        self._index.property_graph_store.upsert_relations(relations)

    def _upsert(self, nodes: list) -> None:
        """Upsert *nodes* into the persistent PropertyGraphIndex.

        We write directly to the underlying ``property_graph_store`` as
        ``ChunkNode`` objects.  ``PropertyGraphIndex.insert_nodes()`` runs the
        full KG-extraction pipeline and emits nothing to the graph store when
        no extractors are configured; bypassing it ensures nodes land in Neo4j
        (or Kuzu) regardless of LLM / extractor availability.
        """
        if not nodes:
            return

        try:
            from llama_index.core.graph_stores.types import ChunkNode  # type: ignore[import]
        except ImportError:
            # Older llama-index-core — fall back to insert_nodes
            self._index.insert_nodes(nodes)
            return

        graph_store = self._index.property_graph_store
        chunk_nodes = []
        for n in nodes:
            # Neo4j only accepts primitive property values (str, int, float, bool)
            # or homogeneous lists of primitives.  Strip any nested dicts/objects
            # (e.g. CodeHierarchyNodeParser's `inclusive_scopes` list-of-dicts).
            safe_props = _sanitize_properties(dict(n.metadata))
            cn = ChunkNode(
                text=n.text,
                id_=n.metadata.get("node_id", None),
                properties=safe_props,
            )
            chunk_nodes.append(cn)

        graph_store.upsert_nodes(chunk_nodes)

    def _query_nodes_by_path(self, file_path: str) -> list:
        """Retrieve all nodes currently in the graph for *file_path*."""
        try:
            retriever = self._index.as_retriever(include_text=False)
            results = retriever.retrieve(f"file:{file_path}")
            return [r.node for r in results if r.node.metadata.get("file_path") == file_path]
        except Exception:  # noqa: BLE001
            return []

    def _summarize_delta(self, node, raw_diff: str) -> str:
        """Produce a short human-readable summary of what changed in *node*.

        This is a lightweight string extraction — no LLM call at this layer.
        The diff lines that overlap the node's range are returned as the delta.
        Callers may pass the result to an LLM summarizer upstream if desired.
        """
        start = int(node.metadata.get("start_line", 0))
        end = int(node.metadata.get("end_line", 0))
        relevant: list[str] = []

        for line in raw_diff.splitlines():
            if line.startswith("@@"):
                # Extract hunk header line number
                try:
                    # e.g. @@ -12,7 +12,7 @@
                    part = line.split(" ")[1]  # "-12,7"
                    hunk_start = abs(int(part.split(",")[0]))
                    if start <= hunk_start <= end:
                        relevant.append(line)
                except (IndexError, ValueError):
                    pass
            elif line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                relevant.append(line)

        if not relevant:
            return ""
        return "\n".join(relevant[:40])  # cap at 40 lines to avoid noise
