from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from rca.brain.models import ApprovedIncident, Hypothesis, RcaReport


def test_approved_incident_requires_service() -> None:
    with pytest.raises(ValidationError):
        ApprovedIncident(
            incident_id="inc-1",
            service="",
            started_at=datetime(2026, 2, 22, tzinfo=timezone.utc),
        )


def test_hypothesis_confidence_is_bounded() -> None:
    with pytest.raises(ValidationError):
        Hypothesis(title="bad", summary="bad", confidence=1.2)


def test_report_status_accepts_known_values() -> None:
    report = RcaReport(incident_id="inc-1", status="completed")
    assert report.status == "completed"
