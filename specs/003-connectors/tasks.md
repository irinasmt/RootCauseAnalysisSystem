# Tasks: Connectors (K8s + GitHub + DB) Plug-and-Play

**Input**: Design documents from `/specs/003-connectors/`
**Prerequisites**: plan.md, spec.md

## Phase 1: Connector Core

- [ ] T001 Create `rca/connectors/` package skeleton
- [ ] T002 Define `Connector` base interface and capability model
- [ ] T003 Implement connector registry + config loader/validator
- [ ] T004 Implement evidence manifest model and persistence hook (adapter-ready)
- [ ] T005 Implement redaction policy engine (allowlist + hash + truncate)

## Phase 2: PostgreSQL Connector (Safety First)

- [ ] T006 Implement Postgres connector config with explicit access levels (`metadata`, `views`, `templates`)
- [ ] T007 Enforce strict guards: no arbitrary SQL, statement timeout, row limits
- [ ] T008 Implement metadata-only evidence collection (system stats) and normalization
- [ ] T009 Add tests proving: default mode never touches user tables and rejects free-form SQL

## Phase 3: Kubernetes + GitHub Connectors

- [ ] T010 Implement Kubernetes connector (in-cluster auth) for deploy/config-change evidence
- [ ] T011 Implement GitHub connector auth (GitHub App first, PAT fallback) and commit sync contract
- [ ] T012 Add tests for config toggles and connector selection

## Phase 4: Integration + Hardening

- [ ] T013 Wire connector outputs into Brain input path (evidence repository or snapshot bundle)
- [ ] T014 Add failure isolation: per-connector timeouts, retries, partial manifests
- [ ] T015 Add docs: minimal configuration examples and least-privilege RBAC snippets

## Dependencies & Execution Order

- T001-T005 before any connector implementations
- T006-T009 before enabling DB connector in any runtime mode
- T010 and T011 can proceed in parallel after T001-T005
- T013-T015 after connectors have passing unit tests
