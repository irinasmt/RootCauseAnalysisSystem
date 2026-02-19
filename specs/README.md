# Specs (Spec-Driven Development)

This repo uses **Spec-Driven Development (SDD)**:

- **Write or update the spec first** (before code changes).
- **Implement to the spec** (code + tests).
- **Keep spec and implementation in sync** (a PR is not “done” if behavior changed but the spec didn’t).

## Where things live

- `specs/features/` — end-to-end feature specs (user-facing behavior, acceptance criteria)
- `specs/interfaces/` — API/event/tool contracts (request/response shapes, invariants)
- `specs/data/` — data models and storage contracts (schemas, IDs, constraints)
- `specs/decisions/` — ADRs (Architecture Decision Records)
- `specs/templates/` — starting templates

## Naming conventions

Keep spec filenames boring and consistent:

- Use **lowercase kebab-case**: `some-spec-name.md`
- Prefer **descriptive names** over numbering (except ADRs)
- Avoid spaces and punctuation other than `-`
- If the spec is explicitly versioned, add a suffix: `-v0`, `-v1`

Recommended patterns by folder:

- `specs/features/`
	- `feature-<short-scope>.md`
	- Examples: `feature-incident-lifecycle-v0.md`, `feature-fixture-first-workflow.md`

- `specs/interfaces/`
	- `api-<surface>.md` for HTTP APIs
	- `event-<event-name>.md` for event payloads
	- `tool-<tool-name>.md` for agent/tool contracts
	- Examples: `api-incidents.md`, `event-deployment-event.md`, `tool-git-scout.md`

- `specs/data/`
	- `<store>-<topic>.md`
	- Examples: `postgres-incidents.md`, `clickhouse-metric-points.md`, `qdrant-collections.md`

- `specs/decisions/`
	- ADRs only: `ADR-####-<short-title>.md`
	- Example: `ADR-0001-sdd.md`

## Minimum bar for a change

For any change that affects behavior, data shapes, or contracts:

1. Update or add a spec in `specs/`
2. Add/adjust tests to reflect the acceptance criteria
3. Implement code so tests + spec agree

If the change is purely internal refactor with identical behavior, no spec update is required.
