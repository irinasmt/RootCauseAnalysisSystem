---
applyTo: "**/*.py"
---

# Python Coding Guidelines — RootCauseAnalysisSystem

## Type Annotations

- All **public functions and methods** must have explicit type annotations on every parameter and the return type.
- Use `Optional[T]` (or `T | None` in Python 3.10+ syntax) for nullable fields — never leave them untyped.
- Prefer `list[T]` / `dict[K, V]` over `List[T]` / `Dict[K, V]` (no import from `typing` needed for built-ins in 3.12+).
- `Any` is a last resort — if you reach for `Any`, add a `# TODO: tighten type` comment.

## Pydantic Models

Use Pydantic `BaseModel` for **all data that crosses a layer boundary**:

| Boundary | Examples |
|----------|---------|
| Brain node input / output | `BrainState`, `RCAReport`, `HypothesisSet` |
| Indexing requests / responses | `IndexingRequest`, `DiffProjection`, `BackfillPolicy` |
| Connector payloads | `DatadogMetricSeries`, `PostgresSlowQuery` |
| Brain engine configuration | `BrainEngineConfig` |

- Use `Field(...)` with `description=` on every field in a cross-layer model.
- Never use a plain `dict` or `dataclass` where a Pydantic model should live.
- Validate at construction time — do not defer validation into business logic.
- Prefer `model_validator` / `field_validator` over ad-hoc checks scattered in node logic.

## LangGraph Node Signatures

Brain nodes follow this exact signature shape:

```python
def node_name(state: BrainState) -> dict[str, Any]:
    ...
```

- Return a `dict` of only the state keys being updated (LangGraph merges it into state).
- Do not return a full `BrainState` object from a node.
- Keep side effects (LLM calls, graph queries) contained inside the node function — do not mutate shared mutable state.

## Optional/Plugin Connectors (`rca/connectors/`)

Guard all third-party SDK imports at the top of the module:

```python
try:
    import some_external_sdk
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False
```

The factory function must raise `RuntimeError` with a clear, actionable message when the SDK or required env vars are missing:

```python
def create_postgres_connector() -> PostgresAdapter:
    if not _SDK_AVAILABLE:
        raise RuntimeError(
            "psycopg2 is not installed. Run: pip install psycopg2-binary"
        )
    ...
```

## Environment Variables

- Never hard-code credentials, DSNs, URLs, or API keys.
- Read all config from `os.environ` (or `os.getenv` with a sensible default).
- Call `load_dotenv()` at entry-point level only (`run_*.py`) — never inside library modules.
- Use a `_require_env(name: str) -> str` helper pattern that raises `RuntimeError` if the variable is absent.

## Testing Conventions

### Unit Tests

- Use `Stub<Name>Adapter` classes that implement the Protocol using in-memory fixture data — no real I/O.
- Contract tests must validate that the Pydantic model correctly parses fixture payloads:
  ```python
  def test_payload_parses():
      raw = json.loads((FIXTURES / "sample.json").read_text())
      model = MyModel.model_validate(raw)
      assert model.service == "payment-service"
  ```
- Assert **evidence-backed** outputs: if a node produces a hypothesis, assert it references a concrete evidence artifact.
- Anti-hallucination assertions: assert a critic node rejects conclusions that precede their evidence in the timeline.
- Keep tests deterministic — patch `random.seed()` or inject it via constructor when generating fixture data.

### Integration Tests

- Use `pytest.importorskip("package_name")` at module level to skip when optional deps are absent.
- Use `pytest.mark.docker` for tests that need a running container; skip with `SKIP_DOCKER_TESTS=1`.
- Use `testcontainers` for real DB containers; use the `responses` library to mock external HTTPS APIs.

## Linting and Formatting

- `ruff check .` must pass with zero errors — do not add `# noqa` without a comment explaining why.
- `black --check .` must pass — do not manually format; let Black own whitespace.
- `mypy rca/` must pass — do not use `# type: ignore` without an explanation comment.
- Run the quick unit suite after every non-trivial change: `pytest tests/unit -q`.
