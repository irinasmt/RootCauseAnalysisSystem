# Project Guidelines

## Code Style

- Use Python 3.12+ with explicit type annotations on public functions and cross-layer APIs.
- Use Pydantic models for structured data that crosses node or component boundaries (Brain node I/O, indexing requests, report payloads).
- Keep changes deterministic for fixture-driven tests; avoid nondeterministic behavior unless explicitly required.
- Do not hard-code credentials or DSNs. Read configuration from environment variables.
- Prefer updating and extending existing patterns in `rca/brain/models.py`, `rca/indexing/models.py`, and `tests/unit/` over introducing new ad-hoc structures.

## Architecture

- Core runtime modules:
  - `rca/brain/`: on-demand RCA engine (`BrainEngine`) and node orchestration.
  - `rca/indexing/`: differential indexing and graph store integration.
  - `rca/seed/`: deterministic fixture and mock data generation.
- Entry points:
  - `run_brain.py`: run Brain against a mock incident fixture.
  - `run_index.py`: index mock diff bundles and inspect graph-indexing behavior.
  - `run_fixture_pipeline.py`: end-to-end fixture ingestion into Neo4j + Brain execution.
- Brain should run on approved incidents, not as an always-on loop. See `docs/architecture/ARCHITECTURE.md` and `docs/brain/BRAIN.md`.

## Build and Test

- Quick unit run: `pytest tests/unit -q`
- Full suite: `pytest`
- Lint: `ruff check .`
- Format check: `black --check .`
- Type check: `mypy rca/`
- Fixture pipeline smoke test (requires Neo4j):
  - `python run_fixture_pipeline.py tests/fixtures/shoe_store/order_slow_due_to_payment`

## Conventions

- Keep spec and implementation aligned: behavior or contract changes should update related files under `specs/` in the same PR.
- Favor evidence-backed outputs: hypotheses and conclusions must reference concrete evidence artifacts (tests should assert this).
- Integration tests may require optional dependencies (`kuzu`, `llama-index-*`, `unidiff`) and can skip when unavailable.
- Neo4j environment naming differs across docs and scripts:
  - Scripts (`run_index.py`, `run_fixture_pipeline.py`) use `NEO4J_URL`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` and repo/mesh-specific variants.
  - Some docs describe `NEO4J_URI` / `NEO4J_AUTH` as conceptual defaults.
  - Prefer script-specific variable names when running local tooling.
- LLM integration is currently Gemini-first via `rca/brain/llm.py` and `GEMINI_*` variables.

## Architecture Review Stance

- Do not blindly accept architecture decisions.
- Evaluate whether a simpler, safer, or more scalable design exists.
- For non-trivial architecture choices, present at least one alternative with explicit tradeoffs (complexity, operability, cost, reliability, migration impact).
- If a design appears risky or over-engineered, call it out and suggest a concrete improvement path.
- Prefer evidence-driven recommendations grounded in tests, failure modes, runtime constraints, data shape, and production operability.
