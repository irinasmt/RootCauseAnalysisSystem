# GitHub & Development Instructions

This document is the single source of truth for how code is written, reviewed, and merged in this project.

---

## Language + runtime

- **Python 3.12+** — required minimum version
- Why Python and not TypeScript:
  - LangGraph, LangChain, Pydantic, Qdrant client, ClickHouse driver, and the K8s Python client are all first-class
  - Pydantic v2 is the guardrail layer throughout the Brain (schema validation on every node output)
  - The TypeScript LangGraph SDK exists but lags significantly behind the Python version

---

## Package management

- Use **`uv`** for dependency management and virtual environments
  - Fast, reproducible, replaces pip + venv + pip-tools in one tool
  - Lock file (`uv.lock`) must be committed
- Do not use bare `pip install` in scripts; always go through `uv`
- Group dependencies explicitly:
  - `[project.dependencies]` — runtime
  - `[project.optional-dependencies] dev` — dev/test tools only

---

## Project structure (proposed)

```
rca/
  brain/
    graph.py          # LangGraph graph definition
    nodes/
      supervisor.py
      git_scout.py
      metric_analyst.py
      synthesizer.py
      critic.py
    schemas.py        # Pydantic models for all node inputs/outputs
    prompts/          # Prompt templates (plain text or Jinja2)
  collectors/
    k8s_collector.py
    git_collector.py
    prometheus_collector.py
    db_collector.py
  stores/
    postgres.py       # DB access layer
    clickhouse.py
    neo4j.py
    qdrant.py
  api/
    main.py           # FastAPI app
    routes/
  seed/
    mock_data.py      # Mock data generators / seed scripts
tests/
  fixtures/           # JSON fixture scenarios
  unit/
  integration/
docs/
specs/
  features/           # Feature specs + acceptance criteria
  interfaces/         # API/event/tool contracts
  data/               # Data model + storage contracts
  decisions/          # ADRs
  templates/          # Spec templates
scripts/
  seed_dbs.py         # Entry point: populate all 4 DBs with mock data
```

---

## Code style

| Tool     | Purpose                     | Config           |
| -------- | --------------------------- | ---------------- |
| `ruff`   | Linting + import sorting    | `pyproject.toml` |
| `black`  | Formatting                  | `pyproject.toml` |
| `mypy`   | Type checking (strict mode) | `pyproject.toml` |
| `pytest` | Testing                     | `pyproject.toml` |

- All new code must pass `ruff`, `black --check`, and `mypy` before merging.
- Type annotations are **required** on all function signatures.
- Pydantic models are required for all data structures crossing node or layer boundaries.

---

## Naming conventions

- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions / variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Pydantic models for node outputs: suffix with the node name (e.g., `GitScoutOutput`, `CriticReview`)
- Database table access functions: prefix with the table name (e.g., `incidents_create`, `incidents_get_by_id`)

---

## Git workflow

### Branches

- `main` — always deployable; protected branch
- `dev` — integration branch; PRs merge here first
- Feature branches: `feat/<short-description>`
- Fix branches: `fix/<short-description>`
- Docs branches: `docs/<short-description>`

### Commit messages

Use conventional commits:

```
<type>(<scope>): <short summary>

type:  feat | fix | docs | refactor | test | chore
scope: brain | collectors | stores | api | seed | infra
```

Examples:

- `feat(brain): add Critic node with evidence gap checks`
- `fix(stores): handle null previous_revision in deployment range query`
- `docs(brain): clarify Git_Scout query contract`

### Pull requests

- Every PR must reference the phase it belongs to (e.g., `Phase 1 — Brain skeleton`)
- This repo uses **Spec-Driven Development (SDD)**:
  - If behavior/contracts change, update/add the spec in `specs/` in the same PR.
  - PR descriptions should link the relevant spec(s) (e.g., `specs/features/...`).
- PR description must include:
  - What changed
  - How to test it
  - Any new environment variables or schema changes
- Minimum 1 reviewer approval before merge to `dev`
- No direct pushes to `main`

---

## Spec-Driven Development (SDD)

SDD is how we keep an AI-heavy system grounded and maintainable.

- **Specs are versioned** and live under `specs/`.
- **Acceptance criteria** in specs must be reflected in tests.
- When implementation diverges from a spec, **the spec must be updated** (or the change is incomplete).

Spec naming:

- Follow the conventions in `specs/README.md` (kebab-case; ADRs as `ADR-####-title.md`).

What counts as a “spec change”:

- API shape changes (request/response)
- event payload/schema changes
- storage/schema changes
- investigation/brain behavior that affects user-visible outputs

What does _not_ require a spec change:

- pure refactors with identical behavior
- comments, formatting, lint-only changes

---

## Environment variables

Never hard-code connection strings. Use a `.env` file locally (git-ignored) with the keys defined in `docs/setup/SETUP.md`.

- `.env` is **never committed**
- `.env.example` is committed with placeholder values and must be kept up to date

---

## Secrets policy

- Never log secret values, even in debug mode
- Never store K8s Secret values in the database (key names only)
- Diff payloads for ConfigMap/Secret changes must redact values before storage

---

## Testing requirements

- Every Brain node must have a unit test with a mocked LLM + mocked store
- Every new Pydantic schema must have a test that asserts invalid shapes are rejected
- Fixture JSON files live in `tests/fixtures/`; they are the canonical inputs for deterministic tests
- See `docs/testing/TESTING.md` for full strategy

---

## Pre-commit hooks (recommended)

```
ruff check .
black --check .
mypy rca/
pytest tests/unit/ -q
```

---

## LLM provider conventions

- Never call an LLM provider directly from a node; always go through the `LLMClient` wrapper in `rca/brain/llm_client.py`
- The wrapper enforces token budgets, logs usage, and supports swapping providers via config
- Prompt templates live in `rca/brain/prompts/` as `.txt` or `.j2` files — never inline in code
