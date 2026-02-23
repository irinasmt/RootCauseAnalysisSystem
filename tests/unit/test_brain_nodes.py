from datetime import datetime, timezone

from rca.brain.models import ApprovedIncident, BrainState
from rca.brain.nodes import critic, git_scout, metric_analyst, rca_synthesizer, supervisor


def make_state() -> BrainState:
    incident = ApprovedIncident(
        incident_id="inc-100",
        service="checkout-api",
        started_at=datetime(2026, 2, 22, tzinfo=timezone.utc),
        deployment_id="deploy-42",
    )
    return BrainState(incident=incident)


def test_nodes_return_state_without_crashing() -> None:
    state = make_state()
    state = supervisor(state)
    state = git_scout(state)
    state = metric_analyst(state)
    state = rca_synthesizer(state)
    state = critic(state)
    assert state.incident.incident_id == "inc-100"
