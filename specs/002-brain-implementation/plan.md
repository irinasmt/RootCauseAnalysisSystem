# Implementation Plan: Brain Investigator MVP

**Branch**: `002-brain-implementation` | **Date**: 2026-02-22 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-brain-implementation/spec.md`

## Summary

Implement a deterministic Brain investigation pipeline in Python for `ApprovedIncident` inputs. MVP includes typed entities, node execution flow (`supervisor -> workers -> synthesizer -> critic`), bounded retries, report persistence, and tests for pass/retry/fail paths.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: Pydantic v2, standard library (MVP), pytest  
**Storage**: In-memory repository for MVP report persistence (adapter-ready for PostgreSQL)  
**Testing**: pytest  
**Target Platform**: Linux/Windows dev runtime  
**Project Type**: Python package  
**Performance Goals**: single incident execution < 2s local test runtime  
**Constraints**: deterministic outputs for fixed input; bounded retries (`max_iterations=3`)  
**Scale/Scope**: MVP for one incident at a time with synchronous execution

## Constitution Check

- Keep implementation incremental and test-first.
- Keep interfaces stable and typed.
- Avoid introducing external runtime services for MVP.

## Project Structure

### Documentation (this feature)

```text
specs/002-brain-implementation/
├── plan.md
├── spec.md
└── tasks.md
```

### Source Code (repository root)

```text
rca/
├── brain/
│   ├── __init__.py
│   ├── models.py
│   ├── repository.py
│   ├── nodes.py
│   └── engine.py

tests/
├── unit/
│   ├── test_brain_models.py
│   ├── test_brain_nodes.py
│   └── test_brain_engine.py
└── integration/
    └── test_brain_report_persistence.py
```

**Structure Decision**: Add a dedicated `rca/brain` package with pure-Python deterministic orchestration and unit/integration tests under existing `tests/` layout.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | N/A | N/A |
