# Tasks: Brain Investigator MVP

**Input**: Design documents from `/specs/002-brain-implementation/`
**Prerequisites**: plan.md, spec.md

## Phase 1: Setup

- [X] T001 Create Brain package skeleton in `rca/brain/` (`__init__.py`, `models.py`, `nodes.py`, `engine.py`, `repository.py`)
- [X] T002 Add public exports for Brain API in `rca/brain/__init__.py`

## Phase 2: Tests First (TDD)

- [X] T003 [P] [US1] Add model validation tests in `tests/unit/test_brain_models.py`
- [X] T004 [P] [US1] Add node behavior tests in `tests/unit/test_brain_nodes.py`
- [X] T005 [US1] Add engine flow tests (pass/retry/escalate/fail) in `tests/unit/test_brain_engine.py`
- [X] T006 [US2] Add integration test for report persistence in `tests/integration/test_brain_report_persistence.py`

## Phase 3: Core Implementation

- [X] T007 [US1] Implement entities (`ApprovedIncident`, `BrainState`, `Hypothesis`, `RcaReport`) in `rca/brain/models.py`
- [X] T008 [US1] Implement deterministic nodes (`supervisor`, `git_scout`, `metric_analyst`, `rca_synthesizer`, `critic`) in `rca/brain/nodes.py`
- [X] T009 [US1] Implement Brain orchestrator with bounded retry loop in `rca/brain/engine.py`
- [X] T010 [US2] Implement in-memory report repository with get/save by incident id in `rca/brain/repository.py`
- [X] T011 [US2] Wire repository integration into engine output path

## Phase 4: Polish

- [X] T012 [US3] Add structured error handling and failure report path in `rca/brain/engine.py`
- [X] T013 [US3] Add minimal docs in `docs/brain/BRAIN.md` with execution example
- [X] T014 Run test suite for Brain modules and ensure deterministic behavior

## Dependencies & Execution Order

- T001-T002 before all other work
- T003-T006 before T007-T012 (tests first)
- T007 before T008-T009
- T010 before T011
- T009 and T011 before T012
- T014 after all implementation tasks

## Parallel Opportunities

- T003 and T004 can run in parallel
- T007 and T010 can run in parallel (different files)
