---
description: "Task list for LlamaIndex Differential Indexer"
---

# Tasks: LlamaIndex Differential Indexer

**Input**: Design documents from `/specs/003-llamaindex-differential-indexer/`  
**Prerequisites**: `plan.md`, `spec.md`

**Organization**: Tasks are grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no blocking dependency)
- **[Story]**: User story label (`US1`, `US2`, `US3`, `US4`)
- Every task includes an exact file path

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create indexing package scaffolding and storage wiring entrypoints.

- [ ] T001 Create indexing package scaffold in `rca/indexing/` (`__init__.py`, `differential_indexer.py`, `service_repo_map.py`, `backfill.py`, `graph_store_factory.py`, `models.py`)
- [ ] T002 [P] Add dependency notes for LlamaIndex + Kuzu + unidiff in `docs/setup/SETUP.md`
- [ ] T003 [P] Add feature implementation overview section in `docs/architecture/ARCHITECTURE.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish strict contracts and primitives all stories depend on.

**⚠️ CRITICAL**: User story work starts only after this phase is complete.

- [ ] T004 Define typed request/config models (`DifferentialIndexerRequest`, `BackfillPolicy`) in `rca/indexing/models.py`
- [ ] T005 Define `ServiceRepoMap` adapter contract and default in-memory implementation in `rca/indexing/service_repo_map.py`
- [ ] T006 Implement graph store factory with injected `AbstractPropertyGraphStore` and MVP `KuzuPropertyGraphStore` path in `rca/indexing/graph_store_factory.py`
- [ ] T007 Implement repository adapter protocol for `get_file(path, commit_sha)` and `get_diff(path, commit_sha)` in `rca/indexing/models.py`
- [ ] T008 [P] Add unit tests for config/model validation in `tests/unit/test_backfill_policy.py`
- [ ] T009 [P] Add unit tests for service-to-repo mapping behavior in `tests/unit/test_service_repo_map.py`
- [ ] T010 [P] Add unit tests for graph store factory wiring (Kuzu + injected store) in `tests/unit/test_graph_store_factory.py`

**Checkpoint**: Contracts, adapter boundaries, and storage wiring are stable.

---

## Phase 3: User Story 1 - Build Node-Level Differential Context (Priority: P1) 🎯 MVP

**Goal**: Parse hierarchy with LlamaIndex, project structured hunks with `unidiff`, assign statuses, and upsert to graph idempotently.

**Independent Test**: For fixture diffs, status assignments are correct and repeated runs do not create duplicate nodes.

### Tests for User Story 1

- [ ] T011 [P] [US1] Add diff hunk projection unit tests (`PatchSet` → line ranges) in `tests/unit/test_diff_projection.py`
- [ ] T012 [P] [US1] Add status assignment tests for `ADDED/MODIFIED/UNCHANGED` in `tests/unit/test_differential_indexer.py`
- [ ] T013 [US1] Add idempotent upsert integration test with Kuzu store in `tests/integration/test_differential_indexer_kuzu.py`

### Implementation for User Story 1

- [ ] T014 [US1] Implement hierarchy extraction using `Document` + `CodeHierarchyNodeParser` in `rca/indexing/differential_indexer.py`
- [ ] T015 [US1] Implement diff parsing via `unidiff.PatchSet` (no custom diff parsing) in `rca/indexing/differential_indexer.py`
- [ ] T016 [US1] Implement node status projection (`ADDED`, `MODIFIED`, `UNCHANGED`) from hunk overlap in `rca/indexing/differential_indexer.py`
- [ ] T017 [US1] Implement metadata enrichment (`file_path`, `symbol_name`, `symbol_kind`, `commit_sha`, `start_line`, `end_line`) in `rca/indexing/differential_indexer.py`
- [ ] T018 [US1] Implement incremental graph upsert into `PropertyGraphIndex` and idempotency guard in `rca/indexing/differential_indexer.py`

**Checkpoint**: P1 differential indexing works end-to-end for changed files.

---

## Phase 4: User Story 2 - Preserve Deleted/Relocated Context in Graph (Priority: P2)

**Goal**: Keep deleted/moved symbols queryable by retaining text-free graph nodes with status metadata.

**Independent Test**: Deletion and move fixtures retain queryable nodes with `status=DELETED|MOVED`.

### Tests for User Story 2

- [ ] T019 [P] [US2] Add deletion retention integration tests in `tests/integration/test_deleted_moved_nodes_retention.py`
- [ ] T020 [P] [US2] Add move/refactor metadata preservation tests in `tests/unit/test_differential_indexer.py`

### Implementation for User Story 2

- [ ] T021 [US2] Implement deleted node retention with text-free `TextNode` metadata in `rca/indexing/differential_indexer.py`
- [ ] T022 [US2] Implement moved-node handling with prior path metadata in `rca/indexing/differential_indexer.py`
- [ ] T023 [US2] Add retriever filters/helpers for deleted/moved status lookup in `rca/indexing/differential_indexer.py`

**Checkpoint**: Missing code remains visible to the Brain via graph retrieval.

---

## Phase 5: User Story 3 - Service-Aware Onboarding with Bounded Backfill (Priority: P3)

**Goal**: Support first-time service onboarding with configurable bounded backfill (default 90 days).

**Independent Test**: Register service map + run backfill; graph is populated for commits inside policy window only.

### Tests for User Story 3

- [ ] T024 [P] [US3] Add backfill window enforcement tests (`max_days`) in `tests/unit/test_backfill_policy.py`
- [ ] T025 [P] [US3] Add service onboarding backfill integration test in `tests/integration/test_differential_indexer_kuzu.py`

### Implementation for User Story 3

- [ ] T026 [US3] Implement backfill orchestration (`service -> repo -> commit walk -> index`) in `rca/indexing/backfill.py`
- [ ] T027 [US3] Implement bounded commit filtering and batching in `rca/indexing/backfill.py`
- [ ] T028 [US3] Wire default `BackfillPolicy(max_days=90)` and override support in `rca/indexing/models.py`

**Checkpoint**: Service onboarding produces a warm graph without full codebase scans.

---

## Phase 6: User Story 4 - Brain-Queryable Graph via Retriever API (Priority: P4)

**Goal**: Make `git_scout` consume structured graph retrieval output, not raw diffs.

**Independent Test**: Brain node queries retriever and consumes metadata-bearing nodes with no raw diff parsing path.

### Tests for User Story 4

- [ ] T029 [P] [US4] Add integration test for Brain retriever contract in `tests/integration/test_brain_git_scout_retriever.py`
- [ ] T030 [P] [US4] Add unit tests for `git_scout` fallback/error behavior when graph query fails in `tests/unit/test_brain_nodes.py`

### Implementation for User Story 4

- [ ] T031 [US4] Update `git_scout` to query `PropertyGraphIndex.as_retriever()` and summarize returned node metadata in `rca/brain/nodes.py`
- [ ] T032 [US4] Remove/guard any raw diff parsing logic from Brain path in `rca/brain/nodes.py`
- [ ] T033 [US4] Add indexer-to-brain interface adapter for retrieval query parameters in `rca/indexing/models.py`

**Checkpoint**: Brain consumes graph-native context for deployment-change reasoning.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T034 [P] Add structured diagnostics for parser/projection/upsert/backfill failures in `rca/indexing/differential_indexer.py` and `rca/indexing/backfill.py`
- [ ] T035 [P] Add language configuration tests for `CodeHierarchyNodeParser(language=...)` in `tests/unit/test_differential_indexer.py`
- [ ] T036 [P] Add performance smoke test for <3s medium-file indexing target in `tests/integration/test_differential_indexer_kuzu.py`
- [ ] T037 Update `docs/brain/BRAIN.md` with retriever-based `git_scout` data flow
- [ ] T038 Run targeted test suite and capture commands in `specs/003-llamaindex-differential-indexer/plan.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 → Phase 2 → Phase 3/4/5/6 → Phase 7
- User stories execute in priority order for MVP value.

### Story Dependencies

- **US1 (P1)** depends on foundational contracts and storage wiring.
- **US2 (P2)** depends on US1 projection and upsert paths.
- **US3 (P3)** depends on US1 index execution and `ServiceRepoMap` contract.
- **US4 (P4)** depends on US1 graph population and retriever availability.

### Within-Story Order

- Write tests before implementation in each story where practical.
- Land idempotent upsert before deletion/move handling.
- Land backfill orchestration before Brain retrieval integration.

## Parallel Execution Examples

```bash
# US1 tests in parallel
Task: "T011 [US1] in tests/unit/test_diff_projection.py"
Task: "T012 [US1] in tests/unit/test_differential_indexer.py"

# US2 tests in parallel
Task: "T019 [US2] in tests/integration/test_deleted_moved_nodes_retention.py"
Task: "T020 [US2] in tests/unit/test_differential_indexer.py"

# US4 tests in parallel
Task: "T029 [US4] in tests/integration/test_brain_git_scout_retriever.py"
Task: "T030 [US4] in tests/unit/test_brain_nodes.py"
```

## Implementation Strategy

### MVP First

1. Complete Phase 1 + Phase 2.
2. Deliver US1 (parse → project → upsert) with Kuzu persistence and idempotency.
3. Deliver US2 deletion/move retention for missing-code investigations.
4. Deliver US3 onboarding backfill (default 90 days).
5. Deliver US4 Brain retriever integration.

### Incremental Delivery

- After US1: working differential graph indexing for changed files.
- After US2: deleted/moved symbols become queryable evidence.
- After US3: service onboarding avoids cold-start incidents.
- After US4: Brain consumes structured graph context without raw-diff parsing.
