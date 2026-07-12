from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from rca.brain.models import ApprovedIncident, Hypothesis, RcaReport
from rca.brain.repository import InMemoryReportRepository


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


def test_derive_severity_low_for_confident_completed_report() -> None:
    report = RcaReport(
        incident_id="inc-1",
        status="completed",
        critic_score=0.9,
        fix_confidence=0.85,
    )
    assert report.derive_severity() == "low"
    assert report.is_actionable is True


def test_derive_severity_high_for_low_confidence_escalation() -> None:
    report = RcaReport(
        incident_id="inc-2",
        status="escalated",
        critic_score=0.4,
        fix_confidence=0.3,
    )
    assert report.derive_severity() == "high"
    assert report.is_actionable is False


def test_derive_severity_critical_for_failed_report() -> None:
    report = RcaReport(incident_id="inc-3", status="failed", errors=["boom"])
    assert report.derive_severity() == "critical"
    assert report.is_actionable is False


def test_errors_on_completed_report_raise_severity_to_high() -> None:
    report = RcaReport(
        incident_id="inc-4",
        status="completed",
        critic_score=0.9,
        fix_confidence=0.85,
        errors=["synthesizer_parse_error: bad json"],
    )
    assert report.derive_severity() == "high"


def test_summarize_carries_severity_and_actionability() -> None:
    report = RcaReport(
        incident_id="inc-5",
        status="completed",
        critic_score=0.9,
        fix_confidence=0.85,
        hypotheses=[
            Hypothesis(title="Low", summary="s", confidence=0.4),
            Hypothesis(title="Top cause", summary="s", confidence=0.8),
        ],
    )
    summary = report.summarize()
    assert summary.top_hypothesis == "Top cause"
    assert summary.top_confidence == pytest.approx(0.8)
    assert summary.severity == "low"
    assert summary.is_actionable is True
    assert summary.error_count == 0


def test_repository_query_methods() -> None:
    repo = InMemoryReportRepository()
    repo.save(RcaReport(incident_id="a", status="completed", fix_confidence=0.85, critic_score=0.9))
    repo.save(RcaReport(incident_id="b", status="escalated", fix_confidence=0.2))
    repo.save(RcaReport(incident_id="c", status="completed", fix_confidence=0.9, critic_score=0.85))

    assert repo.count() == 3
    assert {r.incident_id for r in repo.list_all()} == {"a", "b", "c"}
    assert [r.incident_id for r in repo.find_by_status("escalated")] == ["b"]

    summaries = repo.summaries()
    assert len(summaries) == 3
    assert all(s.incident_id in {"a", "b", "c"} for s in summaries)
