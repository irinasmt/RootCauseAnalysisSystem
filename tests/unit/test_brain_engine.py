from datetime import datetime, timezone

from rca.brain.engine import BrainEngine, BrainEngineConfig
from rca.brain.models import ApprovedIncident


def make_incident() -> ApprovedIncident:
    return ApprovedIncident(
        incident_id="inc-1",
        service="checkout-api",
        started_at=datetime(2026, 2, 22, 10, 0, tzinfo=timezone.utc),
        deployment_id="deploy-1",
    )


def test_engine_completes_with_hypothesis() -> None:
    engine = BrainEngine(config=BrainEngineConfig(critic_threshold=0.8, max_iterations=3))
    report = engine.run(make_incident())
    assert report.status == "completed"
    assert report.hypotheses
    assert report.critic_score >= 0.8


def test_engine_escalates_after_max_iterations() -> None:
    incident = ApprovedIncident(
        incident_id="inc-low-signal",
        service="checkout-api",
        started_at=datetime(2026, 2, 22, 10, 0, tzinfo=timezone.utc),
        deployment_id=None,
    )
    engine = BrainEngine(config=BrainEngineConfig(critic_threshold=0.9, max_iterations=2))
    report = engine.run(incident)
    assert report.status == "escalated"
    assert report.critic_score < 0.9


def test_engine_returns_failed_report_on_internal_error() -> None:
    incident = make_incident()
    engine = BrainEngine(config=BrainEngineConfig(critic_threshold=0.8, max_iterations=1))
    report = engine.run(incident)
    assert report.status != "running"
