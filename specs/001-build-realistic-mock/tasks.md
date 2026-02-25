---
description: "Task list for realistic mock incident data generation"
---

# Tasks: Realistic Mock Incident Data Generation

**Input**: Design documents from `/specs/001-build-realistic-mock/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Organization**: Tasks are grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no blocking dependency)
- **[Story]**: User story label (`US1`, `US2`, `US3`)
- Every task includes an exact file path

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare project structure and baseline module scaffolding.

- [x] T001 Create generator module scaffold in `rca/seed/mock_incident_generator.py`
- [x] T002 Add evaluation-readiness notes and future hook placeholders in `specs/001-build-realistic-mock/quickstart.md`
- [x] T003 [P] Create fixtures root folder and README in `tests/fixtures/mock_incidents/README.md`
- [x] T004 [P] Create shared test utilities for fixture pathing and file hashing in `tests/unit/test_mock_fixture_utils.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement core schema/contracts required by all stories.

**⚠️ CRITICAL**: User story tasks start only after this phase is complete.

- [x] T005 Define Pydantic models for `ScenarioDefinition`, `IncidentBundle`, `StreamArtifact`, `ExpectedOutputLabelSet` in `rca/seed/mock_incident_generator.py`
- [x] T006 Implement fixed v0 scenario registry (`normal_load`, `db_connection_pool_exhaustion`, `slow_query_regression`, `bad_api_rollout`, `pod_oom_restart_loop`) in `rca/seed/mock_incident_generator.py`
- [x] T007 Implement output path + bundle_id generation and artifact manifest assembly in `rca/seed/mock_incident_generator.py`
- [x] T008 Implement stream format policy guardrails (TXT for `ui/api/db/k8s`, JSONL for `mesh`) in `rca/seed/mock_incident_generator.py`
- [x] T009 Implement deterministic seed/time-anchor control and metadata timestamp handling in `rca/seed/mock_incident_generator.py`
- [x] T010 [P] Add foundational schema validation tests in `tests/unit/test_mock_incident_generator.py`
- [x] T011 [P] Add foundational contract invariants tests in `tests/unit/test_mock_incident_generator.py`

**Checkpoint**: Foundational schema, scenario registry, and format policy are in place.

---

## Phase 3: User Story 1 - Generate a Basic Incident Bundle (Priority: P1) 🎯 MVP

**Goal**: Generate one complete deterministic bundle with required artifacts and expected-output metadata.

**Independent Test**: Generate one bundle with known scenario+seed and verify complete artifacts are produced.

### Tests for User Story 1

- [x] T012 [P] [US1] Add unit test for complete artifact set generation in `tests/unit/test_mock_incident_generator.py`
- [x] T013 [P] [US1] Add unit test that enforces one `ground_truth.json` per bundle in `tests/unit/test_mock_incident_generator.py`

### Implementation for User Story 1

- [x] T014 [US1] Implement stream record generation for `ui_events.log` in `rca/seed/mock_incident_generator.py`
- [x] T015 [US1] Implement stream record generation for `api_logs.log` in `rca/seed/mock_incident_generator.py`
- [x] T016 [US1] Implement stream record generation for `db_events.log` in `rca/seed/mock_incident_generator.py`
- [x] T017 [US1] Implement stream record generation for `k8s_events.log` in `rca/seed/mock_incident_generator.py`
- [x] T018 [US1] Implement stream record generation for `mesh_events.jsonl` in `rca/seed/mock_incident_generator.py`
- [x] T019 [US1] Implement `manifest.json` writing in `rca/seed/mock_incident_generator.py`
- [x] T020 [US1] Implement `ground_truth.json` writing in `rca/seed/mock_incident_generator.py`
- [x] T021 [US1] Implement public generate entrypoint for one scenario bundle in `rca/seed/mock_incident_generator.py`

**Checkpoint**: P1 bundle generation works end-to-end for a single scenario.

---

## Phase 4: User Story 2 - Evaluation Readiness Only (Priority: P2, Deferred Runtime Integration)

**Goal**: Keep bundles evaluation-ready while deferring Brain-dependent runtime scoring.

**Independent Test**: Validate expected-output metadata presence and threshold policy in generated bundles.

### Implementation for User Story 2 (Current Scope)

- [x] T022 [P] [US2] Add metadata validation test for `ground_truth.json` required fields in `tests/unit/test_mock_incident_generator.py`
- [x] T023 [P] [US2] Add threshold policy validation test (configurable, default `0.70`) in `tests/unit/test_mock_incident_generator.py`
- [x] T024 [US2] Document deferred Brain runtime integration contract in `specs/001-build-realistic-mock/contracts/mock-incident-generator-contract.md`

**Checkpoint**: Evaluation metadata contracts are stable; Brain scoring implementation is deferred.

---

## Phase 5: User Story 3 - Cover Basic v0 Scenarios (Priority: P3)

**Goal**: Generate valid bundles for all five required v0 scenarios.

**Independent Test**: Run scenario sweep and verify one complete bundle per required scenario.

### Tests for User Story 3

- [x] T025 [P] [US3] Add scenario coverage test for exact five-scenario set in `tests/integration/test_mock_bundle_determinism.py`
- [x] T026 [P] [US3] Add integration test for deterministic artifact byte equality across reruns in `tests/integration/test_mock_bundle_determinism.py`
- [x] T027 [P] [US3] Add integration test for allowed metadata timestamp variance only in `tests/integration/test_mock_bundle_determinism.py`

### Implementation for User Story 3

- [x] T028 [US3] Implement scenario sweep generation helper in `rca/seed/mock_incident_generator.py`
- [x] T029 [US3] Implement deterministic rerun comparison helper (stream checksum + metadata exception list) in `rca/seed/mock_incident_generator.py`
- [x] T030 [US3] Add fixture generation command examples to `specs/001-build-realistic-mock/quickstart.md`

**Checkpoint**: All five scenarios are generated and deterministic checks pass.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T031 [P] Add contract-alignment assertions for output paths/naming in `tests/unit/test_mock_incident_generator.py`
- [x] T032 [P] Add edge-case tests (clock skew, partial outage, retry storms, mesh policy change) in `tests/integration/test_mock_bundle_determinism.py`
- [x] T033 Run full targeted test suite and capture expected commands in `specs/001-build-realistic-mock/quickstart.md`
- [x] T034 Update feature docs with final implementation notes in `specs/001-build-realistic-mock/plan.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 → Phase 2 → Phase 3/4/5 → Phase 6
- User stories can be built sequentially by priority for MVP delivery.

### Story Dependencies

- **US1 (P1)** depends on foundational schema/registry tasks.
- **US2 (P2)** currently covers metadata readiness only; Brain runtime scoring is deferred.
- **US3 (P3)** depends on US1 generation completion and deterministic controls from Phase 2.

### Within-Story Order

- Tests should be written before implementation in each story.
- Artifact generation before future evaluator integration.
- Scenario sweep after single-bundle generation is stable.

## Parallel Execution Examples

```bash
# US1 tests in parallel
Task: "T012 [US1] in tests/unit/test_mock_incident_generator.py"
Task: "T013 [US1] in tests/unit/test_mock_incident_generator.py"

# US3 integration tests in parallel
Task: "T025 [US3] in tests/integration/test_mock_bundle_determinism.py"
Task: "T026 [US3] in tests/integration/test_mock_bundle_determinism.py"
Task: "T027 [US3] in tests/integration/test_mock_bundle_determinism.py"
```

## Implementation Strategy

### MVP First

1. Complete Phase 1 + Phase 2.
2. Deliver US1 (Phase 3) and validate end-to-end bundle generation.
3. Add US2 evaluation-readiness metadata checks and contract documentation.
4. Add US3 scenario sweep + determinism integration checks.

### Incremental Delivery

- After Phase 3: usable deterministic fixture generator.
- After Phase 4: evaluation-ready metadata contracts for future Brain scoring.
- After Phase 5: full v0 scenario coverage.
