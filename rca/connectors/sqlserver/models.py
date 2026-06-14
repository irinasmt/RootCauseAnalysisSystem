"""Pydantic payload models for the SQL Server connector.

These models represent data returned from SQL Server DMVs and are consumed
by Brain nodes (e.g. MetricAnalyst) to surface DB-level evidence.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SlowQueryRecord(BaseModel):
    """A single slow-query observation sourced from sys.dm_exec_query_stats
    joined with sys.dm_exec_sql_text.
    """

    service: str = Field(
        ...,
        description="Shoe-store canonical service name (e.g. 'payment-service').",
    )
    database: str = Field(
        ...,
        description="SQL Server database name where the query executed.",
    )
    query_hash: str = Field(
        ...,
        description="Hex string of sql_handle / query_hash — stable across re-compilations.",
    )
    query_text: str = Field(
        ...,
        description="Sampled query text from sys.dm_exec_sql_text.",
    )
    avg_duration_ms: float = Field(
        ...,
        ge=0.0,
        description="Average elapsed time in milliseconds over execution_count executions.",
    )
    execution_count: int = Field(
        ...,
        ge=0,
        description="Number of executions recorded in the current plan cache entry.",
    )
    observed_at: datetime = Field(
        ...,
        description="UTC timestamp at which this DMV snapshot was taken.",
    )


class WaitStatRecord(BaseModel):
    """A single wait-type observation sourced from sys.dm_os_wait_stats or
    sys.dm_exec_session_wait_stats for blocking-chain analysis.
    """

    service: str = Field(
        ...,
        description="Shoe-store canonical service name associated with the connection.",
    )
    database: str = Field(
        ...,
        description="SQL Server database name.",
    )
    wait_type: str = Field(
        ...,
        description="SQL Server wait type name (e.g. 'LCK_M_X', 'PAGEIOLATCH_SH').",
    )
    waiting_tasks_count: int = Field(
        ...,
        ge=0,
        description="Cumulative number of tasks that have waited on this wait type.",
    )
    wait_time_ms: float = Field(
        ...,
        ge=0.0,
        description="Total wait time in milliseconds for this wait type.",
    )
    max_wait_time_ms: float = Field(
        ...,
        ge=0.0,
        description="Maximum single-wait duration in milliseconds.",
    )
    blocking_session_id: int | None = Field(
        None,
        description="Session ID of the head blocker, if a blocking chain was detected.",
    )
    observed_at: datetime = Field(
        ...,
        description="UTC timestamp at which this DMV snapshot was taken.",
    )
