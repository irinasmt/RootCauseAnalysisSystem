# Implementation Plan: Realistic Mock Incident Data Generation

**Branch**: `001-build-realistic-mock` | **Date**: 2026-02-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-build-realistic-mock/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Build a deterministic mock-incident generator for a simple app stack (UI/API/DB/K8s/mesh) that emits evaluation-ready bundle artifacts. v0 uses fixed scenarios, mixed output format (TXT for non-mesh, JSONL for mesh), and expected-output labels with a configurable threshold defaulted to 0.70; Brain runtime scoring is explicitly deferred.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: Pydantic v2, standard library (`json`, `pathlib`, `datetime`, `random`), pytest  
**Storage**: File artifacts only under `tests/fixtures/mock_incidents/` (no database persistence in v0)  
**Testing**: pytest (unit + fixture determinism checks + schema/contract validation)  
**Target Platform**: Local developer environment and CI on Linux/Windows/macOS
**Project Type**: Python library/CLI-oriented utility feature  
**Performance Goals**: Generate one 30-minute bundle in <5s on dev machine; deterministic rerun diff should be empty for stream artifacts  
**Constraints**: Non-mesh logs must be TXT, mesh must be JSONL; fixed v0 scenario set of five; only bundle-level metadata timestamps may vary across reruns  
**Scale/Scope**: v0 limited to five scenarios and single-app topology (UI/API/DB/K8s/mesh)

## Constitution Check

_GATE: Must pass before Phase 0 research. Re-check after Phase 1 design._

### Pre-Design Gate Review

- Spec-Driven First: **PASS** (`spec.md` exists and contains testable FR/SC + clarifications).
- Evidence-Grounded Outputs: **PASS** (expected-output label set and cross-layer evidence requirements captured).
- Determinism for Validation: **PASS** (scenario+seed determinism and timestamp tolerance explicitly defined).
- Quality Gates by Default: **PASS** (plan includes pytest and schema validation expectations).
- Security and Secret Hygiene: **PASS** (no secret-bearing inputs or persistence paths defined).

### Post-Design Gate Review

- Spec/Design alignment: **PASS** (`research.md`, `data-model.md`, `contracts/`, `quickstart.md` generated and aligned).
- Deterministic validation path: **PASS** (contracts and quickstart include reproducibility checks).
- No constitutional violations requiring exception: **PASS**.

## Project Structure

### Documentation (this feature)

```text
specs/001-build-realistic-mock/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
rca/
├── seed/
│   └── mock_incident_generator.py

tests/
├── fixtures/
│   └── mock_incidents/
├── unit/
│   └── test_mock_incident_generator.py
└── integration/
  └── test_mock_bundle_determinism.py

specs/
└── 001-build-realistic-mock/
  ├── contracts/
  ├── data-model.md
  ├── plan.md
  ├── quickstart.md
  ├── research.md
  └── spec.md
```

**Structure Decision**: Single Python project structure, implementing generator/evaluator logic in `rca/` and deterministic fixture validation in `tests/`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --------- | ---------- | ------------------------------------ |
| None      | N/A        | N/A                                  |
