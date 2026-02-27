# Implementation Plan: LlamaIndex Differential Indexer

**Branch**: `003-llamaindex-differential-indexer` | **Date**: 2026-02-25 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-llamaindex-differential-indexer/spec.md`

## Summary

Implement an incident-driven Differential Indexer using LlamaIndex-native components only. The pipeline parses file hierarchy via `CodeHierarchyNodeParser`, projects Git hunks via `unidiff PatchSet`, and incrementally upserts enriched `TextNode` metadata into a persistent `PropertyGraphIndex`. MVP storage is `KuzuPropertyGraphStore` (embedded); production target is `Neo4jPropertyGraphStore` via dependency injection. Brain `git_scout` consumes graph context through `.as_retriever()` with no raw-diff parsing.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: `llama-index-core`, `llama-index-packs-code-hierarchy`, `llama-index-graph-stores-kuzu`, `kuzu`, `unidiff`, `pydantic`, `pytest`  
**Storage**: `KuzuPropertyGraphStore` for MVP (local embedded graph DB); adapter path for `Neo4jPropertyGraphStore` in production  
**Testing**: pytest (unit + integration with fixture diffs and graph assertions)  
**Target Platform**: Linux/Windows local runtime and CI  
**Project Type**: Python package feature integrated into existing RCA pipeline  
**Performance Goals**: single medium-file differential pass (<2k LOC) in <3s local runtime; idempotent re-run should not increase node count  
**Constraints**: no custom code hierarchy parser; no hand-rolled diff parser; incremental upsert only (no full rebuild per commit)  
**Scale/Scope**: service-aware, lazy indexing for changed files in incident windows + bounded service onboarding backfill (default 90 days)

## Constitution Check

_GATE: Must pass before implementation starts and be re-checked after design completion._

### Pre-Design Gate Review

- Spec-driven implementation: **PASS** (`spec.md` exists with FR/IR/SC and acceptance scenarios).
- Deterministic, testable behavior: **PASS** (idempotent upsert and deterministic status outcomes defined).
- Incremental and safe integration: **PASS** (Brain retrieval contract and fail-safe diagnostics required).
- Minimal MVP infra burden: **PASS** (Kuzu embedded store for MVP).

### Post-Design Gate Review

- LlamaIndex-native architecture maintained end-to-end: **PASS**.
- Storage abstraction preserved via injected `PropertyGraphStore`: **PASS**.
- No constitutional exceptions identified: **PASS**.

## Project Structure

### Documentation (this feature)

```text
specs/003-llamaindex-differential-indexer/
├── plan.md
├── spec.md
└── tasks.md
```

### Source Code (repository root)

```text
rca/
├── brain/
│   └── nodes.py                      # git_scout retrieval integration point
└── indexing/
    ├── __init__.py
    ├── differential_indexer.py       # orchestration: parse -> project -> upsert
    ├── service_repo_map.py           # service -> repo/language adapter contract
    ├── backfill.py                   # bounded onboarding backfill runner
    └── graph_store_factory.py        # Kuzu (MVP) / Neo4j (prod) store wiring

tests/
├── unit/
│   ├── test_differential_indexer.py
│   ├── test_diff_projection.py
│   ├── test_service_repo_map.py
│   └── test_backfill_policy.py
└── integration/
    ├── test_differential_indexer_kuzu.py
    ├── test_deleted_moved_nodes_retention.py
    └── test_brain_git_scout_retriever.py
```

**Structure Decision**: Introduce a focused `rca/indexing` package for indexer logic and graph/storage abstractions, while wiring Brain consumption at `rca/brain/nodes.py` to keep retrieval concerns localized.

## Implementation Phases

1. **Foundations**: Add models/contracts for index requests, service map, backfill policy, and graph store wiring.
2. **Differential Core**: Implement LlamaIndex parse + `unidiff` projection + status assignment + metadata enrichment.
3. **Persistence**: Implement incremental graph upsert and idempotency checks with Kuzu-backed store.
4. **Onboarding**: Implement bounded backfill flow using service map + repository adapter.
5. **Brain Integration**: Update `git_scout` to query `PropertyGraphIndex.as_retriever()` and consume structured nodes.
6. **Validation**: Add unit/integration tests for status correctness, deletion retention, idempotency, and retrieval contract.

## Risks & Mitigations

- **Risk**: LlamaIndex parser coverage can vary by language/file style.  
  **Mitigation**: enforce parser diagnostics and safe fallback status on parse gaps.
- **Risk**: Large merge diffs can add noisy hunks.  
  **Mitigation**: hunk filtering + bounded processing + structured warnings.
- **Risk**: Graph growth over time affects local performance.  
  **Mitigation**: bounded backfill window, incremental-only updates, production Neo4j adapter path.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | N/A | N/A |
