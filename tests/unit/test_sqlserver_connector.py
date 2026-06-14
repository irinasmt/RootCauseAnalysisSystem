"""Unit tests for the SQL Server connector.

No real SQL Server instance required — all tests use the in-memory stub
adapter and the fixture JSON from tests/fixtures/connectors/sqlserver/.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from rca.connectors.sqlserver.models import SlowQueryRecord, WaitStatRecord
from rca.connectors.sqlserver.protocol import SqlServerAdapter

# ---------------------------------------------------------------------------
# Load fixture
# ---------------------------------------------------------------------------

_FIXTURE_PATH = (
    Path(__file__).parent.parent
    / "fixtures" / "connectors" / "sqlserver" / "sample_response.json"
)


@pytest.fixture(scope="module")
def fixture_data() -> dict:
    return json.loads(_FIXTURE_PATH.read_text())


# ---------------------------------------------------------------------------
# Stub adapter
# ---------------------------------------------------------------------------

class StubSqlServerAdapter:
    """In-memory stub satisfying SqlServerAdapter protocol using fixture data."""

    def __init__(self, data: dict) -> None:
        self._slow_queries = [
            SlowQueryRecord.model_validate(r) for r in data["slow_queries"]
        ]
        self._wait_stats = [
            WaitStatRecord.model_validate(r) for r in data["wait_stats"]
        ]

    def fetch_slow_queries(
        self,
        service: str,
        min_avg_duration_ms: float = 0.0,
        top_n: int = 100,
    ) -> list[SlowQueryRecord]:
        return [
            r for r in self._slow_queries
            if r.service == service and r.avg_duration_ms >= min_avg_duration_ms
        ][:top_n]

    def fetch_wait_stats(
        self,
        service: str,
        top_n: int = 100,
    ) -> list[WaitStatRecord]:
        return [r for r in self._wait_stats if r.service == service][:top_n]


# ---------------------------------------------------------------------------
# Protocol contract
# ---------------------------------------------------------------------------

def test_stub_satisfies_protocol(fixture_data: dict) -> None:
    stub = StubSqlServerAdapter(fixture_data)
    assert isinstance(stub, SqlServerAdapter), (
        "StubSqlServerAdapter must satisfy the SqlServerAdapter runtime_checkable Protocol"
    )


# ---------------------------------------------------------------------------
# Pydantic payload parsing
# ---------------------------------------------------------------------------

def test_slow_query_parses_from_fixture(fixture_data: dict) -> None:
    records = [SlowQueryRecord.model_validate(r) for r in fixture_data["slow_queries"]]
    assert len(records) == 3
    assert records[0].service == "payment-service"
    assert records[0].avg_duration_ms > 0
    assert isinstance(records[0].observed_at, datetime)


def test_wait_stat_parses_from_fixture(fixture_data: dict) -> None:
    records = [WaitStatRecord.model_validate(r) for r in fixture_data["wait_stats"]]
    assert len(records) == 3
    # first record has a blocking session id (blocking chain scenario)
    assert records[0].blocking_session_id == 58
    # second record has no blocking session (pure IO wait)
    assert records[1].blocking_session_id is None


def test_slow_query_evidence_refs(fixture_data: dict) -> None:
    """Confirm evidence_refs can be constructed from SlowQueryRecord fields."""
    record = SlowQueryRecord.model_validate(fixture_data["slow_queries"][0])
    ref = f"sqlserver:slow_query:{record.query_hash}:{record.database}"
    assert record.query_hash in ref
    assert record.database in ref


# ---------------------------------------------------------------------------
# Stub filtering behaviour
# ---------------------------------------------------------------------------

def test_stub_filters_by_service(fixture_data: dict) -> None:
    stub = StubSqlServerAdapter(fixture_data)
    results = stub.fetch_slow_queries("payment-service")
    assert all(r.service == "payment-service" for r in results)
    assert len(results) == 2  # fixture has 2 payment-service slow query rows


def test_stub_filters_slow_queries_by_duration(fixture_data: dict) -> None:
    stub = StubSqlServerAdapter(fixture_data)
    results = stub.fetch_slow_queries("payment-service", min_avg_duration_ms=3000.0)
    assert all(r.avg_duration_ms >= 3000.0 for r in results)


def test_stub_wait_stats_filter_by_service(fixture_data: dict) -> None:
    stub = StubSqlServerAdapter(fixture_data)
    results = stub.fetch_wait_stats("order-service")
    assert all(r.service == "order-service" for r in results)


# ---------------------------------------------------------------------------
# Missing env var
# ---------------------------------------------------------------------------

def test_factory_raises_on_missing_dsn() -> None:
    """create_sqlserver_connector must raise RuntimeError when SQLSERVER_DSN is absent."""
    import rca.connectors.sqlserver.factory as factory_module

    # Simulate SDK available so the DSN check is reached even when pyodbc is absent
    with patch.object(factory_module, "_SDK_AVAILABLE", True):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="SQLSERVER_DSN"):
                factory_module.create_sqlserver_connector()


# ---------------------------------------------------------------------------
# Missing SDK
# ---------------------------------------------------------------------------

def test_client_raises_when_sdk_unavailable() -> None:
    """SqlServerClient must raise RuntimeError when pyodbc is not installed."""
    import rca.connectors.sqlserver.sqlserver_client as client_module

    original = client_module._SDK_AVAILABLE
    try:
        client_module._SDK_AVAILABLE = False
        with pytest.raises(RuntimeError, match="pyodbc"):
            from rca.connectors.sqlserver.sqlserver_client import SqlServerClient
            SqlServerClient()
    finally:
        client_module._SDK_AVAILABLE = original


# ---------------------------------------------------------------------------
# BrainEngineConfig integration
# ---------------------------------------------------------------------------

def test_brain_engine_config_accepts_sqlserver_adapter(fixture_data: dict) -> None:
    """BrainEngineConfig.sqlserver_adapter must accept any SqlServerAdapter."""
    from rca.brain.engine import BrainEngineConfig

    stub = StubSqlServerAdapter(fixture_data)
    config = BrainEngineConfig(sqlserver_adapter=stub)  # type: ignore[arg-type]
    assert config.sqlserver_adapter is stub
    assert isinstance(config.sqlserver_adapter, SqlServerAdapter)
