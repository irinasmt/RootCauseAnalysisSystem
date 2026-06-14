"""Concrete SQL Server connector implementation using pyodbc.

Guards the ``pyodbc`` import so the rest of the codebase loads cleanly
when the driver is not installed.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

try:
    import pyodbc  # type: ignore[import]
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False

from .models import SlowQueryRecord, WaitStatRecord


# ---------------------------------------------------------------------------
# Slow-query DMV query
# ---------------------------------------------------------------------------

_SLOW_QUERY_SQL = """\
SELECT TOP (?)
    qs.total_elapsed_time / qs.execution_count / 1000.0  AS avg_duration_ms,
    qs.execution_count,
    CONVERT(varchar(64), qs.sql_handle, 1)                AS query_hash,
    SUBSTRING(
        st.text,
        (qs.statement_start_offset / 2) + 1,
        (
            CASE qs.statement_end_offset
                WHEN -1 THEN DATALENGTH(st.text)
                ELSE qs.statement_end_offset
            END - qs.statement_start_offset
        ) / 2 + 1
    )                                                      AS query_text
FROM sys.dm_exec_query_stats AS qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) AS st
WHERE qs.total_elapsed_time / qs.execution_count / 1000.0 >= ?
ORDER BY avg_duration_ms DESC
"""

# ---------------------------------------------------------------------------
# Wait-stats DMV query
# ---------------------------------------------------------------------------

_WAIT_STATS_SQL = """\
SELECT TOP (?)
    ws.wait_type,
    ws.waiting_tasks_count,
    ws.wait_time_ms,
    ws.max_wait_time_ms
FROM sys.dm_os_wait_stats AS ws
WHERE ws.wait_type NOT IN (
    'SLEEP_TASK','BROKER_TO_FLUSH','BROKER_EVENTHANDLER',
    'REQUEST_FOR_DEADLOCK_SEARCH','LOGMGR_QUEUE','CHECKPOINT_QUEUE',
    'CLR_AUTO_EVENT','DISPATCHER_QUEUE_SEMAPHORE','FT_IFTS_SCHEDULER_IDLE_WAIT',
    'HADR_WORK_QUEUE','HADR_FILESTREAM_IOMGR_IOCOMPLETION',
    'HADR_TIMER_TASK','HADR_LOG_CAPTURE_WAIT','HADR_TRANSPORT_DBRLIST',
    'SQLTRACE_BUFFER_FLUSH','LAZYWRITER_SLEEP','RESOURCE_QUEUE',
    'SERVER_IDLE_CHECK','SLEEP_DBSTARTUP','SLEEP_DBTASK','SLEEP_TEMPDBSTARTUP',
    'SNI_HTTP_ACCEPT','SP_SERVER_DIAGNOSTICS_SLEEP','SQLTRACE_INCREMENTAL_FLUSH_SLEEP',
    'WAIT_XTP_OFFLINE_CKPT_NEW_LOG','XE_DISPATCHER_WAIT','XE_TIMER_EVENT',
    'WAITFOR','SLEEP_MASTERDBREADY','SLEEP_MASTERMDREADY',
    'SLEEP_MASTERUPGRADED','SLEEP_MSDBSTARTUP','SLEEP_SYSTEMTASK',
    'SLEEP_TEMPDBSTARTUP','SNI_HTTP_ACCEPT','ONDEMAND_TASK_QUEUE',
    'PARALLEL_REDO_DRAIN_WORKER','PARALLEL_REDO_LOG_CACHE',
    'PARALLEL_REDO_TRAN_LIST','PARALLEL_REDO_WORKER_SYNC',
    'PARALLEL_REDO_WORKER_WAIT_WORK'
)
ORDER BY ws.wait_time_ms DESC
"""


class SqlServerClient:
    """Reads slow-query and wait-stat evidence from a SQL Server instance."""

    def __init__(self) -> None:
        if not _SDK_AVAILABLE:
            raise RuntimeError(
                "pyodbc is not installed. Run: pip install pyodbc"
            )
        dsn = _require_env("SQLSERVER_DSN")
        self._database = os.environ.get("SQLSERVER_DATABASE", "master")
        self._conn: pyodbc.Connection = pyodbc.connect(dsn, autocommit=True)

    # ------------------------------------------------------------------
    # Public interface (satisfies SqlServerAdapter protocol)
    # ------------------------------------------------------------------

    def fetch_slow_queries(
        self,
        service: str,
        min_avg_duration_ms: float = 100.0,
        top_n: int = 20,
    ) -> list[SlowQueryRecord]:
        """Query sys.dm_exec_query_stats for the slowest queries."""
        now = datetime.now(tz=timezone.utc)
        cursor = self._conn.cursor()
        cursor.execute(_SLOW_QUERY_SQL, top_n, min_avg_duration_ms)
        rows = cursor.fetchall()
        return [
            SlowQueryRecord(
                service=service,
                database=self._database,
                query_hash=row.query_hash or "",
                query_text=(row.query_text or "").strip(),
                avg_duration_ms=float(row.avg_duration_ms),
                execution_count=int(row.execution_count),
                observed_at=now,
            )
            for row in rows
        ]

    def fetch_wait_stats(
        self,
        service: str,
        top_n: int = 20,
    ) -> list[WaitStatRecord]:
        """Query sys.dm_os_wait_stats for the most burdensome waits."""
        now = datetime.now(tz=timezone.utc)
        cursor = self._conn.cursor()
        cursor.execute(_WAIT_STATS_SQL, top_n)
        rows = cursor.fetchall()
        return [
            WaitStatRecord(
                service=service,
                database=self._database,
                wait_type=row.wait_type,
                waiting_tasks_count=int(row.waiting_tasks_count),
                wait_time_ms=float(row.wait_time_ms),
                max_wait_time_ms=float(row.max_wait_time_ms),
                blocking_session_id=None,
                observed_at=now,
            )
            for row in rows
        ]

    def close(self) -> None:
        """Close the underlying pyodbc connection."""
        self._conn.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Required environment variable {name!r} is not set. "
            f"Example: SQLSERVER_DSN='DRIVER={{ODBC Driver 18 for SQL Server}};SERVER=localhost;UID=sa;PWD=<pw>'"
        )
    return value
