# Feature Specification: LlamaIndex Differential Indexer

**Feature Branch**: `003-llamaindex-differential-indexer`  
**Created**: 2026-02-25  
**Status**: Draft  
**Input**: User description: "Implement a Differential Indexer using LlamaIndex (no custom parser stack), specifically using libraries like `CodeHierarchyNodeParser`, to map Git diffs onto hierarchical code nodes for Brain-ready RCA context."

## Clarifications

### Session 2026-02-25

- Q: Should the implementation rely on custom AST/parsing logic? → A: No. Use LlamaIndex-native components (`CodeHierarchyNodeParser`) for hierarchy extraction; no custom parser stacks.
- Q: What should be indexed: raw diff text or structured node deltas? → A: Structured node deltas with status and optional semantic annotations, derived from diff-to-node line overlap.
- Q: How should deleted/moved code be represented? → A: As persisted graph nodes with `status=DELETED|MOVED` metadata. No text body required. Deletions survive in the graph indefinitely.
- Q: How should diff hunks be projected onto node line ranges? → A: Use `unidiff` library (`PatchSet`) for structured hunk parsing. No hand-rolled unified diff string parsing.
- Q: Where is the graph stored? → A: `KuzuPropertyGraphStore` (embedded, file-based graph DB) for MVP. `Neo4jPropertyGraphStore` for production. Both implement LlamaIndex's `AbstractPropertyGraphStore` — injected as a constructor argument so the indexer is storage-agnostic.
- Q: Does the entire codebase need to be indexed on day one? → A: No. Indexing is incident-driven and lazy: only files touched by commits in the incident window are indexed on demand. A bounded backfill (configurable, default 90 days) is run once per service on first connection.
- Q: How does the indexer know which repo to query given an incident? → A: Via a `ServiceRepoMap` config that resolves `incident.service → (repo_url, language)`. This is provided at startup.

## User Scenarios & Testing _(mandatory)_

### User Story 1 - Build Node-Level Differential Context (Priority: P1)

As an RCA engineer, I want changed files converted into hierarchical LlamaIndex nodes annotated with change status and upserted into a persistent graph so the Brain can reason over functions/classes instead of raw diffs.

**Why this priority**: This is the core capability. Everything else depends on a populated, queryable graph.

**Independent Test**: Given file content + raw diff for a commit, run indexer and assert the graph contains nodes with correct `status` values (`MODIFIED`, `ADDED`, `UNCHANGED`) based on `unidiff` hunk line-range overlap.

**Acceptance Scenarios**:

1. **Given** a changed C# file and its raw diff, **When** Differential Indexer runs, **Then** it parses hierarchy via `CodeHierarchyNodeParser`, projects hunks via `unidiff PatchSet`, and upserts annotated `TextNode` objects into the `PropertyGraphIndex`.
2. **Given** node line ranges overlap a diff hunk, **When** status assignment executes, **Then** those nodes are marked `MODIFIED` in the graph.
3. **Given** nodes with no hunk overlap, **When** status assignment executes, **Then** nodes are marked `UNCHANGED`.
4. **Given** the same file content and diff are re-processed, **When** indexer runs again, **Then** upsert is idempotent — no duplicate nodes created.

---

### User Story 2 - Preserve Deleted/Relocated Context in the Graph (Priority: P2)

As an RCA engineer, I want deleted or moved code to remain queryable in the graph so the Brain can reason about missing code that is still causing incidents.

**Why this priority**: Investigations often fail because the Brain searches for code that no longer exists. Deleted nodes must survive.

**Independent Test**: Provide a file deletion diff; verify the graph retains the node with `status=DELETED` and no text body, queryable by the Brain's retriever.

**Acceptance Scenarios**:

1. **Given** a full-file deletion diff, **When** indexing runs, **Then** the graph retains all prior nodes for that file with `status=DELETED` and no text content.
2. **Given** a move/refactor diff where direct text mapping is incomplete, **Then** affected nodes are marked `status=MOVED` with the prior path preserved as metadata.
3. **Given** the Brain queries the graph for a deleted symbol, **Then** the retriever returns the node with its identity metadata intact, enabling hypothesis generation.

---

### User Story 3 - Service-Aware Onboarding with Bounded Backfill (Priority: P3)

As an operator, I want to connect a new service and have the indexer automatically backfill recent commit history so the Brain is not cold on day one.

**Why this priority**: Without backfill the graph is empty for the first real incident, defeating the purpose of the system.

**Independent Test**: Register a `ServiceRepoMap` entry and trigger backfill; verify the graph contains nodes for commits within the configured backfill window.

**Acceptance Scenarios**:

1. **Given** a new service is registered with a `ServiceRepoMap` entry, **When** backfill runs, **Then** commits within the `BackfillPolicy` window are processed and nodes are present in the graph.
2. **Given** a `BackfillPolicy` with `max_days=90`, **When** backfill executes, **Then** only commits within that window are indexed; older commits are skipped.

---

### User Story 4 - Brain-Queryable Graph via Retriever API (Priority: P4)

As the Brain runtime, I want to query the graph via LlamaIndex's retriever API so `git_scout` receives structured node context without touching raw diffs.

**Why this priority**: Eliminates the "raw diff string" antipattern from Brain nodes entirely.

**Independent Test**: Call `PropertyGraphIndex.as_retriever()` with a service/commit query; verify returned `NodeWithScore` objects contain status, symbol identity, and optional semantic delta — no raw diff text.

**Acceptance Scenarios**:

1. **Given** a populated graph, **When** Brain's `git_scout` queries via retriever, **Then** it receives `NodeWithScore` list with `status`, `file_path`, and `symbol` metadata.
2. **Given** a modified node with optional summarization enabled, **Then** returned node metadata includes `semantic_delta` scoped to that node's diff span.
3. **Given** a class-method hierarchy in the graph, **Then** parent-child relations are traversable via graph edges for blast-radius reasoning.

### Edge Cases

- Large commit with many hunks touching disjoint methods in one file.
- Full-file deletion where current repository content is absent.
- Rename/move with minimal textual changes but path-level relocation.
- Parser partial coverage for mixed-language or generated files.
- Diff hunks that touch comments or whitespace only (should not promote to `MODIFIED`).
- Backfill encountering merge commits with large, noisy diffs.
- `ServiceRepoMap` missing entry for an incident's service (must fail safely with diagnostic).

## Non-goals for this feature iteration

- Building a custom AST parser or replacing LlamaIndex hierarchy extraction.
- Implementing full semantic code understanding beyond optional node-scoped summarization.
- Multi-repo federated indexing and cross-repo lineage.
- Real-time streaming ingestion from VCS webhooks.
- `git blame` integration and latent change detection (deferred — see future development notes).
- Cross-incident hot-spot correlation and `implicated_in` graph edges (deferred).

## Requirements _(mandatory)_

### Functional Requirements

- **FR-001**: System MUST use LlamaIndex `Document` as the input abstraction for file content passed to the parser.
- **FR-002**: System MUST use LlamaIndex `CodeHierarchyNodeParser` for hierarchy extraction. Custom parser stacks for code hierarchy are explicitly out of scope.
- **FR-003**: System MUST use the `unidiff` library (`PatchSet`) to parse raw diff strings into typed hunks with integer line ranges. Hand-rolled unified diff parsing is prohibited.
- **FR-004**: System MUST project `unidiff` hunk line ranges onto `CodeHierarchyNodeParser` node ranges to assign node-level status (`ADDED`, `MODIFIED`, `DELETED`, `MOVED`, `UNCHANGED`).
- **FR-005**: System MUST persist annotated nodes as LlamaIndex `TextNode` objects (with status and identity in `metadata`) upserted into a `PropertyGraphIndex`. No separate custom node type hierarchy.
- **FR-006**: System MUST retain nodes for deleted/moved symbols in the graph with `status=DELETED|MOVED` and no text body. These nodes MUST remain queryable via the retriever.
- **FR-007**: System MUST include stable node identity metadata for Brain correlation: `file_path`, `symbol_name`, `symbol_kind` (class/method/field), `commit_sha`, `start_line`, `end_line` where available.
- **FR-008**: System MUST preserve parent-child hierarchy relationships from `CodeHierarchyNodeParser` output as graph edges in the `PropertyGraphIndex`.
- **FR-009**: System MUST support optional node-scoped semantic delta summarization, stored as `semantic_delta` in node metadata when enabled.
- **FR-010**: System MUST perform incremental upsert into the persistent graph per commit. Full graph rebuilds from scratch are prohibited.
- **FR-011**: System MUST be language-configurable via the `language` parameter supported by `CodeHierarchyNodeParser` (initial target: C#).
- **FR-012**: System MUST resolve `incident.service` to a `(repo_url, language)` pair via an injected `ServiceRepoMap` before any indexing or retrieval operation.
- **FR-013**: System MUST support a bounded backfill run per service on first registration, controlled by an injected `BackfillPolicy` (configurable window, default 90 days).
- **FR-014**: System MUST accept `PropertyGraphStore` as a constructor-injected dependency. `Neo4jPropertyGraphStore` (package: `llama-index-graph-stores-neo4j`) is the required primary implementation — it is used for both local development (Docker) and production (AuraDB). `KuzuPropertyGraphStore` is retained as a zero-infra CI fallback only.
- **FR-015**: System MUST fail safely with structured diagnostics when parsing, diff projection, graph upsert, or backfill cannot complete.
- **FR-016**: System MUST configure `llama_index.core.Settings.embed_model` to a `GeminiEmbedding` instance (package: `llama-index-embeddings-gemini`, default model: `models/text-embedding-004`) before constructing any `PropertyGraphIndex`. LlamaIndex's built-in default is `OpenAIEmbedding`; this MUST be overridden. The API key is sourced from `GEMINI_API_KEY` (same env var as the Brain LLM client).

### Integration Requirements

- **IR-001**: Brain's `git_scout` node MUST query the `PropertyGraphIndex` via its `.as_retriever()` API. It MUST NOT perform raw diff string parsing.
- **IR-002**: Repository adapter contracts MUST provide `get_file(path, commit_sha) -> str` and `get_diff(path, commit_sha) -> str` for indexer use.
- **IR-003**: The graph MUST represent both text-backed nodes (live code) and text-free nodes (deleted/moved) uniformly via `TextNode.metadata` — no separate schema branch required.
- **IR-004**: `ServiceRepoMap` MUST be an injectable adapter, not a hardcoded lookup, so integration tests can substitute test fixtures without real VCS access.

### Key Entities

- **DifferentialIndexerRequest**: Input containing service name, commit SHA, target file paths, and feature flags (e.g. `enable_semantic_delta`).
- **ServiceRepoMap**: Adapter that resolves `service_name → (repo_url, language)`. Injected at construction time.
- **BackfillPolicy**: Value object specifying the lookback window (`max_days`, default `90`) and commit batch size for the initial service onboarding backfill.
- **PropertyGraphIndex** _(LlamaIndex native)_: The persistent graph store. Nodes are `TextNode` objects with enriched metadata. Edges represent hierarchy (`parent_of`, `child_of`) and change provenance (`modified_in:<commit_sha>`).
- **KuzuPropertyGraphStore** _(LlamaIndex native, CI fallback)_: Embedded file-based graph database. Zero infrastructure required. Retained for offline CI only — not the primary runtime.
- **Neo4jPropertyGraphStore** _(LlamaIndex native, primary)_: Neo4j graph database. Used for all local development (Docker) and production (AuraDB). Enables Cypher traversal, Neo4j Browser visualization, and horizontal scale. Substituted via constructor injection. Connection config via `NEO4J_URL`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` env vars.
- **GeminiEmbedding** _(LlamaIndex native, `llama-index-embeddings-gemini`)_: Embedding model used by `PropertyGraphIndex` for vector similarity. MUST be set globally via `llama_index.core.Settings.embed_model` before index construction. Default model: `models/text-embedding-004`. LlamaIndex's own default (`OpenAIEmbedding`) is incompatible with this project's Gemini-first configuration.

## Storage Tiers

| Tier                   | Implementation                                  | When to Use                                                                |
| ---------------------- | ----------------------------------------------- | -------------------------------------------------------------------------- |
| Local dev + production | `Neo4jPropertyGraphStore` (Docker or AuraDB)    | Primary — Cypher traversal; Neo4j Browser; AuraDB free tier for production |
| CI / offline fallback  | `KuzuPropertyGraphStore` (embedded, file-based) | No infra required; when `NEO4J_PASSWORD` is not set                        |

Both implement `AbstractPropertyGraphStore`. The factory auto-selects: Neo4j when `NEO4J_PASSWORD` is set, Kuzu otherwise.

Docker quick-start for local Neo4j::

    docker run --rm -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5

Then browse: http://localhost:7474 (login: neo4j / password)

## Success Criteria _(mandatory)_

### Measurable Outcomes

- **SC-001**: For curated fixtures, 100% of expected touched methods/classes receive correct status labels in the graph.
- **SC-002**: For deletion/move fixtures, 100% of expected missing symbols are retained in the graph as text-free nodes with `status=DELETED|MOVED`.
- **SC-003**: Re-processing the same content and diff is idempotent — node count in graph does not increase on second run.
- **SC-004**: End-to-end differential indexing (parse → project → upsert) completes in < 3 seconds for a single medium file (< 2k LOC) on local dev runtime.
- **SC-005**: Brain's `git_scout` receives structured `NodeWithScore` objects from the retriever with zero raw-diff string content in the payload.
- **SC-006**: Backfill for a service with 90 days of commits completes without error and populates the graph with at least one node per changed file in the window.
