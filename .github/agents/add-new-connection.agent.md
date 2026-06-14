---
description: Scaffold a new optional connector (monitoring or database), generate test fixtures, write unit and integration tests, and run them — including spinning up a Docker container for supported connector types.
tools: [vscode, execute, read, agent, edit, search, web, browser, todo]
---

## User Input

```text
$ARGUMENTS
```

You **MUST** read the user's connector description before proceeding. If no description is provided, ask:

> "Which connector do you want to add? Examples:
>
> - Monitoring: Datadog, New Relic, Prometheus
> - Relational DB: PostgreSQL, SQL Server, MySQL
>
> Also: what data should Brain read from it? (e.g. metric timeseries, alert history, slow query logs, incident events)"

## Goal

Scaffold a fully working, tested, optional connector under `rca/connectors/<name>/`. The connector activates only when its SDK is installed and env vars are set — otherwise it is silently absent. Unit tests must pass with zero external dependencies. Integration tests spin up a Docker container (for DB connectors) or mock HTTPS (for monitoring APIs).

## Operating Constraints

- **Option A pattern**: `rca/connectors/<name>/` sub-module — not a pip entry-point plugin system.
- All third-party SDK imports must be guarded with `try/except ImportError`.
- Never hard-code credentials — read only from `os.environ`.
- Follow `rca/indexing/graph_store_factory.py` as the primary pattern for factory functions.
- Follow `rca/indexing/models.py` (`RepositoryAdapter`) as the pattern for Protocol definitions.
- Connector type determines integration test strategy:
  - **Relational DB** (PostgreSQL, SQL Server, MySQL) → `testcontainers` Docker container
  - **Monitoring API** (Datadog, New Relic, Prometheus) → `responses` library (HTTP mocks; no Docker)
- One connector per invocation.

## Execution Steps

### Step 1 — Gather Requirements

Before generating any code, confirm:

1. **Connector name and type** (monitoring or DB)
2. **Brain data contract**: what Pydantic model fields does the consuming Brain node need? (e.g. `service: str`, `metric_name: str`, `values: list[float]`, `timestamps: list[datetime]`)
3. **Docker availability**: ask "Should I generate Docker-based integration tests? (yes/no/skip)"

Read these files first to understand the existing patterns:

- `rca/indexing/graph_store_factory.py` — factory function pattern
- `rca/indexing/models.py` lines 1–60 — Protocol definition pattern
- `rca/brain/models.py` lines 1–80 — `BrainEngineConfig` structure to extend
- `tests/unit/test_differential_indexer.py` lines 1–80 — `StubRepoAdapter` unit test pattern
- `tests/integration/test_differential_indexer_kuzu.py` lines 1–40 — `pytest.importorskip` pattern

### Step 2 — Scaffold `rca/connectors/<name>/`

Create the following files in order:

#### `rca/connectors/__init__.py` (create once; skip if exists)

Empty init — just a namespace marker.

#### `rca/connectors/<name>/__init__.py`

Export the Protocol class and factory function:

```python
from .protocol import <Name>Adapter
from .factory import create_<name>_connector
__all__ = ["<Name>Adapter", "create_<name>_connector"]
```

#### `rca/connectors/<name>/protocol.py`

Define a `@runtime_checkable` Protocol:

```python
from typing import Protocol, runtime_checkable
from .<name>_models import <PayloadModel>

@runtime_checkable
class <Name>Adapter(Protocol):
    def fetch_metrics(self, service: str, window_minutes: int) -> list[<PayloadModel>]: ...
    # add methods matching the Brain node's data contract
```

#### `rca/connectors/<name>/models.py`

Pydantic models for connector-specific payloads. Every field must have `description=`:

```python
from pydantic import BaseModel, Field

class <PayloadModel>(BaseModel):
    service: str = Field(..., description="Service name matching shoe_store canonical names")
    # ... fields per data contract
```

#### `rca/connectors/<name>/<name>_client.py`

Concrete implementation with guarded import:

```python
try:
    import <sdk>
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False

class <Name>Client:
    def __init__(self) -> None:
        if not _SDK_AVAILABLE:
            raise RuntimeError("<sdk> is not installed. Run: pip install <package>")
        self._api_key = _require_env("<NAME>_API_KEY")
        # ... init SDK client
```

#### `rca/connectors/<name>/factory.py`

Mirror the `graph_store_factory.py` style exactly:

```python
import os
from .protocol import <Name>Adapter

def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name!r} is not set.")
    return value

def create_<name>_connector() -> <Name>Adapter:
    # guard SDK availability, read env vars, return client
```

### Step 3 — Extend `BrainEngineConfig`

Read `rca/brain/models.py` to find `BrainEngineConfig`. Add an optional field:

```python
from rca.connectors.<name> import <Name>Adapter
# inside BrainEngineConfig:
<name>_adapter: Optional[<Name>Adapter] = Field(None, description="Optional <Name> connector for Brain nodes")
```

Use `TYPE_CHECKING` guard if needed to avoid circular imports.

### Step 4 — Generate Test Fixture Data

Create `tests/fixtures/connectors/<name>/sample_response.json` — a realistic JSON payload using shoe_store service names (`payment-service`, `order-service`, etc.) that the SDKs realistic response format would return. This fixture is used in unit tests and must be deterministic.

### Step 5 — Write Unit Tests

Create `tests/unit/test_<name>_connector.py`:

1. **Stub adapter**: `Stub<Name>Adapter` class implementing the Protocol using the fixture JSON
2. **Protocol contract test**: assert `isinstance(stub, <Name>Adapter)` passes
3. **Pydantic payload test**: `<PayloadModel>.model_validate(raw)` parses the fixture without errors
4. **Missing env var test**: mock `os.environ` empty and assert factory raises `RuntimeError` with a clear message
5. **Missing SDK test**: patch `_SDK_AVAILABLE = False` and assert client constructor raises `RuntimeError`

Run after writing: `pytest tests/unit/test_<name>_connector.py -q`

### Step 6 — Write Integration Tests

Create `tests/integration/test_<name>_docker.py`.

**For relational DB connectors (PostgreSQL, SQL Server, MySQL):**

```python
pytest.importorskip("testcontainers")
pytest.importorskip("<db_driver>")

@pytest.fixture(scope="session")
def db_container():
    from testcontainers.<db> import <DB>Container
    with <DB>Container() as container:
        yield container
```

Test that: container starts, connector connects, a sample query returns parseable `<PayloadModel>` objects.

**For monitoring API connectors (Datadog, New Relic, Prometheus):**

```python
pytest.importorskip("responses")
pytest.importorskip("<sdk>")

@responses.activate
def test_fetch_metrics_mocked():
    responses.add(responses.GET, "<api_endpoint>", json=<fixture_payload>, status=200)
    # assert connector returns valid PayloadModel list
```

Add `pytest.mark.docker` to any test that starts a container. Check `tests/conftest.py` — create it if it does not exist:

```python
# tests/conftest.py
import pytest

def pytest_configure(config):
    config.addinivalue_line("markers", "docker: mark test as requiring Docker")
```

### Step 7 — Run All Tests and Validate

Run in sequence:

```bash
pytest tests/unit/test_<name>_connector.py -q
```

If Docker tests were generated:

```bash
pytest tests/integration/test_<name>_docker.py -q -m docker
```

Then:

```bash
mypy rca/connectors/<name>/ --ignore-missing-imports
ruff check rca/connectors/<name>/
```

Fix any failures before proceeding to the report.

### Step 8 — Update SETUP.md

Append a new section to `docs/setup/SETUP.md` documenting the new connector's env vars in the required table format (per `docs.instructions.md`).

### Step 9 — Report

Tell the user:

1. All files created and modified
2. The env vars to set to activate the connector
3. How to wire it into `BrainEngineConfig` in `run_brain.py` or `run_fixture_pipeline.py`
4. Test results summary
5. Next step: which Brain node consumes this connector and how to inject it
