"""Persistence adapter for Brain reports."""

from __future__ import annotations

from .models import RcaReport


class InMemoryReportRepository:
    """In-memory storage for RCA reports.
    
    Provides simple key-value persistence for Brain Engine reports during
    testing and development. For production deployments, replace with a
    database-backed implementation.
    """
    
    def __init__(self) -> None:
        self._reports: dict[str, RcaReport] = {}

    def save(self, report: RcaReport) -> None:
        """Persist an RCA report by incident ID.
        
        Args:
            report: The completed RCA report to store.
        """
        self._reports[report.incident_id] = report

    def get(self, incident_id: str) -> RcaReport | None:
        """Retrieve a report by incident ID.
        
        Args:
            incident_id: The unique incident identifier.
            
        Returns:
            The stored report, or None if not found.
        """
        return self._reports.get(incident_id)
