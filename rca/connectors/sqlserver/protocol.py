"""Protocol definition for the SQL Server connector.

Defines ``SqlServerAdapter`` — the interface Brain nodes depend on.
Concrete implementations are injected at runtime via
``create_sqlserver_connector()``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import SlowQueryRecord, WaitStatRecord


@runtime_checkable
class SqlServerAdapter(Protocol):
    """Read-only view of a SQL Server instance for RCA evidence gathering.

    All methods return lists of Pydantic models so callers can iterate
    without inspecting raw rows.
    """

    def fetch_slow_queries(
        self,
        service: str,
        min_avg_duration_ms: float,
        top_n: int,
    ) -> list[SlowQueryRecord]:
        """Return the top-N slowest queries for *service* above the duration threshold.

        Parameters
        ----------
        service:
            Shoe-store canonical service name used to tag results.
        min_avg_duration_ms:
            Lower bound on average duration — queries below this are excluded.
        top_n:
            Maximum number of records to return, ordered by avg_duration_ms descending.
        """
        ...

    def fetch_wait_stats(
        self,
        service: str,
        top_n: int,
    ) -> list[WaitStatRecord]:
        """Return the top-N wait types by total wait time for *service*.

        Parameters
        ----------
        service:
            Shoe-store canonical service name used to tag results.
        top_n:
            Maximum number of wait types to return, ordered by wait_time_ms descending.
        """
        ...
