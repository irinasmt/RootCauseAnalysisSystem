"""Persistence adapter for Brain reports."""

from __future__ import annotations

from .models import RcaReport, RcaReportSummary


class InMemoryReportRepository:
    def __init__(self) -> None:
        self._reports: dict[str, RcaReport] = {}

    def save(self, report: RcaReport) -> None:
        self._reports[report.incident_id] = report

    def get(self, incident_id: str) -> RcaReport | None:
        return self._reports.get(incident_id)

    def list_all(self) -> list[RcaReport]:
        """Return all stored reports in insertion order."""
        return list(self._reports.values())

    def find_by_status(self, status: str) -> list[RcaReport]:
        """Return every report matching the given status (e.g. 'escalated')."""
        return [r for r in self._reports.values() if r.status == status]

    def summaries(self) -> list[RcaReportSummary]:
        """Return a lightweight summary for every stored report.

        Convenience for alerting/dashboard callers that only need the headline
        fields rather than the full hypothesis and metadata payload.
        """
        return [r.summarize() for r in self._reports.values()]

    def count(self) -> int:
        """Return the number of stored reports."""
        return len(self._reports)
