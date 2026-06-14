"""Factory for the SQL Server connector.

Mirrors the pattern in ``rca/indexing/graph_store_factory.py``:
reads environment variables, guards SDK availability, and returns a
``SqlServerAdapter``-compatible client.

Required environment variables
-------------------------------
``SQLSERVER_DSN``
    Full ODBC connection string, e.g.
    ``DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;UID=sa;PWD=secret``
``SQLSERVER_DATABASE``
    Database name to target (default: ``master``).
"""

from __future__ import annotations

import os

from .protocol import SqlServerAdapter
from .sqlserver_client import SqlServerClient, _SDK_AVAILABLE


def create_sqlserver_connector() -> SqlServerAdapter:
    """Instantiate and return a ``SqlServerClient``.

    Raises ``RuntimeError`` if ``pyodbc`` is not installed or if
    ``SQLSERVER_DSN`` is not set.
    """
    if not _SDK_AVAILABLE:
        raise RuntimeError(
            "pyodbc is not installed. Run: pip install pyodbc"
        )
    dsn = os.environ.get("SQLSERVER_DSN")
    if not dsn:
        raise RuntimeError(
            "Required environment variable 'SQLSERVER_DSN' is not set. "
            "Example: SQLSERVER_DSN='DRIVER={ODBC Driver 18 for SQL Server};"
            "SERVER=localhost;UID=sa;PWD=<password>'"
        )
    return SqlServerClient()
