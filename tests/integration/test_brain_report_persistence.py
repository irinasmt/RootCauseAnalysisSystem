from datetime import datetime, timezone

from rca.brain.engine import BrainEngine
from rca.brain.models import ApprovedIncident
from rca.brain.repository import InMemoryReportRepository


def test_report_is_persisted_by_incident_id() -> None:
    repo = InMemoryReportRepository()
    engine = BrainEngine(repository=repo)
    incident = ApprovedIncident(
        incident_id="inc-77",
        service="payments-api",
        started_at=datetime(2026, 2, 22, tzinfo=timezone.utc),
    )

    report = engine.run(incident)
    loaded = repo.get("inc-77")

    assert loaded is not None
    assert loaded.incident_id == report.incident_id
    assert loaded.status == report.status
