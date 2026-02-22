# Root Cause Analysis System Constitution

## Core Principles

### I. Spec-Driven First (Non-Negotiable)

All behavior, contract, and schema changes MUST start with a spec update under `specs/` before implementation. Feature specs, interface contracts, data contracts, and ADRs are authoritative design artifacts and MUST remain in sync with code. Work that changes behavior without corresponding spec updates is incomplete.

### II. Evidence-Grounded RCA Outputs

RCA conclusions MUST be explicitly grounded in evidence artifacts (metrics, deployment events, git metadata, and related telemetry). The system MUST prefer uncertainty over fabricated certainty, and every report claim MUST be traceable to concrete evidence references.

### III. Determinism for Validation

Given the same fixture inputs and seed, investigation and mock-generation workflows MUST produce reproducible outputs in deterministic mode. Non-deterministic behavior is allowed only when explicitly configured and MUST be excluded from baseline regression assertions.

### IV. Quality Gates by Default

All production code MUST include type annotations and pass repository quality gates (`ruff`, `black --check`, `mypy`, and `pytest` for affected scope). New schemas MUST include validation tests; Brain-node logic MUST include unit tests with mocked LLM/store boundaries.

### V. Security and Secret Hygiene

Secrets MUST NOT be committed, logged, or persisted in plaintext. Local secret configuration MUST use `.env` (git-ignored) with `.env.example` kept current. Data ingestion, storage, and reporting flows MUST redact or avoid sensitive values by default.

## Engineering Constraints

- Primary runtime is Python 3.12+.
- Dependency and environment management MUST use `uv`.
- Pydantic schemas are required for cross-boundary data contracts.
- Naming conventions follow repository standards (`snake_case` files/functions, `PascalCase` classes, `UPPER_SNAKE_CASE` constants).
- Specs and docs use lowercase kebab-case naming, except ADRs (`ADR-####-title.md`).

## Workflow and Review Gates

- Canonical development flow is Spec Kit: `/speckit.constitution` → `/speckit.specify` → `/speckit.clarify` → `/speckit.plan` → `/speckit.tasks` → `/speckit.analyze` and `/speckit.checklist` → `/speckit.implement`.
- Pull requests MUST link relevant specs and include: what changed, how to test, and any env/schema updates.
- No direct pushes to `main`; reviewer approval is required before merge to integration branches.
- If implementation diverges from specs, specs MUST be updated in the same change set.

## Governance

This constitution supersedes local workflow preferences when conflicts arise.

- Amendment process: propose change via PR, include rationale, impact analysis, and required template/process updates.
- Versioning policy:
  - MAJOR: breaking governance or principle changes.
  - MINOR: new principle/section or materially expanded guidance.
  - PATCH: clarifications and wording fixes without semantic change.
- Compliance review: every feature PR MUST include an explicit constitution check against these principles.

**Version**: 1.0.0 | **Ratified**: 2026-02-22 | **Last Amended**: 2026-02-22
