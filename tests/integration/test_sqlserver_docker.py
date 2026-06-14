"""Integration tests for the SQL Server connector using a real container.

Requires:
    pip install testcontainers pyodbc

The ODBC Driver 18 for SQL Server must be installed on the host machine.
On Windows: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server
On Linux/macOS: install via apt/brew per Microsoft docs.

Tests spin up a SQL Server 2022 Developer Edition container and exercise
the ``SqlServerClient`` end-to-end, asserting that live DMV queries return
``SlowQueryRecord`` and ``WaitStatRecord`` objects that satisfy their Pydantic
schemas.

Skipped automatically when ``testcontainers`` or ``pyodbc`` are not installed.
"""

from __future__ import annotations

import os
import time
from datetime import datetime

import pytest

testcontainers = pytest.importorskip("testcontainers", reason="testcontainers not installed")
pytest.importorskip("pyodbc", reason="pyodbc not installed")

from testcontainers.mssql import SqlServerContainer  # type: ignore[import]

from rca.connectors.sqlserver.models import SlowQueryRecord, WaitStatRecord
from rca.connectors.sqlserver.sqlserver_client import SqlServerClient


# ---------------------------------------------------------------------------
# Session-scoped container fixture
# ---------------------------------------------------------------------------

_MSSQL_IMAGE = "mcr.microsoft.com/mssql/server:2022-latest"
_SA_PASSWORD = "RcaTest!2026"  # Meets SQL Server password complexity requirements


@pytest.fixture(scope="session")
def sqlserver_container():
    """Start a SQL Server 2022 container and yield the DSN."""
    with SqlServerContainer(
        image=_MSSQL_IMAGE,
        password=_SA_PASSWORD,
    ) as container:
        # testcontainers exposes a JDBC-style URL; build an ODBC DSN manually
        host = container.get_container_host_ip()
        port = container.get_exposed_port(1433)
        dsn = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={host},{port};"
            f"UID=sa;PWD={_SA_PASSWORD};"
            f"TrustServerCertificate=yes"
        )
        # Wait for SQL Server to accept connections (up to 60 s)
        import pyodbc
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                conn = pyodbc.connect(dsn, timeout=5)
                conn.close()
                break
            except Exception:
                time.sleep(2)
        else:
            pytest.fail("SQL Server container did not become ready within 60 s")

        yield dsn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.docker
def test_slow_queries_returns_list(sqlserver_container: str) -> None:
    """fetch_slow_queries must return a list of SlowQueryRecord against a real server."""
    os.environ["SQLSERVER_DSN"] = sqlserver_container
    os.environ["SQLSERVER_DATABASE"] = "master"

    client = SqlServerClient()
    try:
        results = client.fetch_slow_queries(
            service="payment-service",
            min_avg_duration_ms=0.0,
            top_n=10,
        )
    finally:
        client.close()
        os.environ.pop("SQLSERVER_DSN", None)

    assert isinstance(results, list)
    for r in results:
        assert isinstance(r, SlowQueryRecord)
        assert r.service == "payment-service"
        assert r.avg_duration_ms >= 0.0
        assert isinstance(r.observed_at, datetime)


@pytest.mark.docker
def test_wait_stats_returns_list(sqlserver_container: str) -> None:
    """fetch_wait_stats must return a list of WaitStatRecord against a real server."""
    os.environ["SQLSERVER_DSN"] = sqlserver_container
    os.environ["SQLSERVER_DATABASE"] = "master"

    client = SqlServerClient()
    try:
        results = client.fetch_wait_stats(service="order-service", top_n=10)
    finally:
        client.close()
        os.environ.pop("SQLSERVER_DSN", None)

    assert isinstance(results, list)
    for r in results:
        assert isinstance(r, WaitStatRecord)
        assert r.service == "order-service"
        assert r.wait_time_ms >= 0.0
        assert isinstance(r.observed_at, datetime)


@pytest.mark.docker
def test_slow_query_records_parse_as_pydantic(sqlserver_container: str) -> None:
    """SlowQueryRecord.model_validate must succeed on every row returned by the live DMV."""
    os.environ["SQLSERVER_DSN"] = sqlserver_container
    os.environ["SQLSERVER_DATABASE"] = "master"

    client = SqlServerClient()
    try:
        results = client.fetch_slow_queries(
            service="payment-service",
            min_avg_duration_ms=0.0,
            top_n=5,
        )
    finally:
        client.close()
        os.environ.pop("SQLSERVER_DSN", None)

    for r in results:
        # Re-validate via round-trip to ensure the model is self-consistent
        revalidated = SlowQueryRecord.model_validate(r.model_dump())
        assert revalidated == r


@pytest.mark.docker
def test_wait_stat_records_parse_as_pydantic(sqlserver_container: str) -> None:
    """WaitStatRecord.model_validate must succeed on every row returned by the live DMV."""
    os.environ["SQLSERVER_DSN"] = sqlserver_container
    os.environ["SQLSERVER_DATABASE"] = "master"

    client = SqlServerClient()
    try:
        results = client.fetch_wait_stats(service="order-service", top_n=5)
    finally:
        client.close()
        os.environ.pop("SQLSERVER_DSN", None)

    for r in results:
        revalidated = WaitStatRecord.model_validate(r.model_dump())
        assert revalidated == r
