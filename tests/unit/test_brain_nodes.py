from datetime import datetime, timezone
from unittest.mock import MagicMock

from rca.brain.models import ApprovedIncident, BrainState
from rca.brain.nodes import critic, git_scout, mesh_scout, metric_analyst, rca_synthesizer, supervisor


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


def test_metric_analyst_expands_suspect_services_from_mesh() -> None:
    mesh_events = [
        {
            "service": "checkout-api",
            "upstream": "payment-api",
            "response_code": 200,
            "latency_ms": 100,
            "retry_count": 0,
            "ts": "2026-02-22T09:55:00+00:00",
        },
        {
            "service": "checkout-api",
            "upstream": "payment-api",
            "response_code": 503,
            "latency_ms": 540,
            "retry_count": 6,
            "ts": "2026-02-22T10:01:00+00:00",
        },
    ]
    incident = ApprovedIncident(
        incident_id="inc-mesh-1",
        service="checkout-api",
        started_at=datetime(2026, 2, 22, 10, 0, tzinfo=timezone.utc),
        deployment_id="deploy-42",
        extra_context={"mesh_events": mesh_events},
    )
    state = BrainState(incident=incident)
    state = supervisor(state)
    state = metric_analyst(state)

    assert "checkout-api" in state.suspect_services
    assert "payment-api" in state.suspect_services
    assert "checkout-api->payment-api" in state.suspect_edges
    assert any(ref == "mesh-suspect:payment-api" for ref in state.evidence_refs)
    assert any(ref == "logs:payment-api" for ref in state.evidence_refs)


def test_git_scout_queries_each_suspect_service() -> None:
    incident = ApprovedIncident(
        incident_id="inc-mesh-2",
        service="checkout-api",
        started_at=datetime(2026, 2, 22, 10, 0, tzinfo=timezone.utc),
        deployment_id="deploy-42",
    )
    state = BrainState(
        incident=incident,
        task_plan="Investigate dependent services",
        suspect_services=["checkout-api", "payment-api"],
    )

    mock_retriever = MagicMock()
    mock_retriever.retrieve.side_effect = [[], []]
    mock_index = MagicMock()
    mock_index.as_retriever.return_value = mock_retriever

    git_scout(state, graph_index=mock_index)

    assert mock_retriever.retrieve.call_count == 2
    q1 = mock_retriever.retrieve.call_args_list[0][0][0]
    q2 = mock_retriever.retrieve.call_args_list[1][0][0]
    assert "service:checkout-api" in q1
    assert "service:payment-api" in q2


def test_mesh_scout_surfaces_third_party_labels_in_summary() -> None:
    incident = ApprovedIncident(
        incident_id="inc-mesh-3",
        service="order-service",
        started_at=datetime(2026, 2, 22, 10, 0, tzinfo=timezone.utc),
        deployment_id="deploy-43",
    )
    state = BrainState(incident=incident)

    mock_session = MagicMock()
    mock_session.run.return_value = [
        {
            "svc": "payment-gateway",
            "is_external": True,
            "dependency_type": "third_party_api",
            "ownership": "external_not_owned",
            "is_third_party_api": True,
            "error_count": 20,
            "call_count": 100,
            "avg_latency_ms": 750,
            "p99_latency_ms": 1200,
        }
    ]
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    updated = mesh_scout(state, mesh_driver=mock_driver)

    assert "payment-gateway" in updated.suspect_services
    assert "third_party_api" in updated.mesh_summary
    assert "external_not_owned" in updated.mesh_summary
