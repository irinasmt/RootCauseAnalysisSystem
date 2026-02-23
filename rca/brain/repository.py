"""Persistence adapter for Brain reports."""

from __future__ import annotations

from .models import RcaReport


class InMemoryReportRepository:
    def __init__(self) -> None:
        self._reports: dict[str, RcaReport] = {}

    def save(self, report: RcaReport) -> None:
        self._reports[report.incident_id] = report

    def get(self, incident_id: str) -> RcaReport | None:
        return self._reports.get(incident_id)
