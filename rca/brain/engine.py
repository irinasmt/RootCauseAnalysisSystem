"""Brain orchestration engine — LangGraph StateGraph implementation.

Graph topology:
    supervisor → mesh_scout → git_scout → metric_analyst → rca_synthesizer → critic → fix_advisor
                    ↑                                              (done) ──────────────────┘   |
                    └──────────────────────── (refine: score < threshold) ────────────────┘   END

mesh_scout runs before git_scout so that suspect services are ranked by
observed mesh degradation (error rate + latency) rather than timestamp
proximity. This ensures git_scout queries the repo DB for the right services.

fix_advisor always runs after the critic loop completes. It asks: "what single
intervention resolves the incident across ALL plausible causes?" — decoupling
actionability (fix_confidence) from root-cause certainty (critic_score).
The report status is "completed" when EITHER score exceeds its threshold.

Pydantic output models in nodes.py validate each node's produced fields before
control passes to the next node, surfacing bad output as early as possible.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from langgraph.graph import END, StateGraph

from .llm import LLMClient, LLMConfig
from .models import ApprovedIncident, BrainState, RcaReport
from .nodes import critic, fix_advisor, git_scout, mesh_scout, metric_analyst, rca_synthesizer, supervisor
from .repository import InMemoryReportRepository


@dataclass
class BrainEngineConfig:
    critic_threshold: float = 0.80
    fix_confidence_threshold: float = 0.75  # fix_advisor score needed to resolve despite low critic_score
    max_iterations: int = 3
    llm_config: LLMConfig | None = field(default=None)
    graph_index: object | None = None
    mesh_driver: object | None = None  # neo4j.Driver for mesh graph traversal
    report_log_path: str | None = field(default_factory=lambda: os.environ.get("BRAIN_REPORT_LOG_PATH"))


class BrainEngine:
    def __init__(
        self,
        repository: InMemoryReportRepository | None = None,
        config: BrainEngineConfig | None = None,
    ) -> None:
        self.repository = repository or InMemoryReportRepository()
        self.config = config or BrainEngineConfig()
        self._llm: LLMClient | None = (
            LLMClient(self.config.llm_config)
            if self.config.llm_config and self.config.llm_config.is_configured
            else None
        )
        self._graph = self._build_graph()

    def _persist_report_log(self, report: RcaReport) -> None:
        if not self.config.report_log_path:
            return

        out_path = Path(self.config.report_log_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "report": report.model_dump(mode="json"),
        }
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_graph(self):
        llm = self._llm
        config = self.config
        graph_index = config.graph_index
        mesh_driver = config.mesh_driver

        # Node wrappers: call the existing node function, return a dict so
        # LangGraph can update the Pydantic state.  Each underlying node runs
        # its own Pydantic output validation before returning.

        def _supervisor_node(state: BrainState) -> dict:
            # Increment iteration counter on every entry into the supervisor
            updated = state.model_copy(update={"iteration": state.iteration + 1})
            return supervisor(updated, llm=llm).model_dump()

        def _mesh_scout_node(state: BrainState) -> dict:
            return mesh_scout(state, mesh_driver=mesh_driver).model_dump()

        def _git_scout_node(state: BrainState) -> dict:
            return git_scout(state, llm=llm, graph_index=graph_index).model_dump()

        def _metric_analyst_node(state: BrainState) -> dict:
            return metric_analyst(state, llm=llm).model_dump()

        def _rca_synthesizer_node(state: BrainState) -> dict:
            return rca_synthesizer(state, llm=llm).model_dump()

        def _critic_node(state: BrainState) -> dict:
            return critic(state, llm=llm).model_dump()

        def _fix_advisor_node(state: BrainState) -> dict:
            return fix_advisor(state, llm=llm).model_dump()

        def _route_after_critic(state: BrainState) -> str:
            """Conditional edge: loop back to supervisor or finish."""
            if state.critic_score >= config.critic_threshold:
                return "done"
            if state.iteration >= config.max_iterations:
                return "done"
            return "refine"

        graph = StateGraph(BrainState)

        graph.add_node("supervisor", _supervisor_node)
        graph.add_node("mesh_scout", _mesh_scout_node)
        graph.add_node("git_scout", _git_scout_node)
        graph.add_node("metric_analyst", _metric_analyst_node)
        graph.add_node("rca_synthesizer", _rca_synthesizer_node)
        graph.add_node("critic", _critic_node)
        graph.add_node("fix_advisor", _fix_advisor_node)

        graph.set_entry_point("supervisor")
        graph.add_edge("supervisor", "mesh_scout")
        graph.add_edge("mesh_scout", "git_scout")
        graph.add_edge("git_scout", "metric_analyst")
        graph.add_edge("metric_analyst", "rca_synthesizer")
        graph.add_edge("rca_synthesizer", "critic")
        graph.add_conditional_edges(
            "critic",
            _route_after_critic,
            {"done": "fix_advisor", "refine": "supervisor"},
        )
        graph.add_edge("fix_advisor", END)

        return graph.compile()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, incident: ApprovedIncident) -> RcaReport:
        initial = BrainState(
            incident=incident,
            max_iterations=self.config.max_iterations,
            critic_threshold=self.config.critic_threshold,
        )

        try:
            result = self._graph.invoke(initial)
            # LangGraph returns a dict when state is a Pydantic model
            final = BrainState.model_validate(result) if isinstance(result, dict) else result

            status = "completed" if (
                final.critic_score >= self.config.critic_threshold
                or final.fix_confidence >= self.config.fix_confidence_threshold
            ) else "escalated"

            report = RcaReport(
                incident_id=final.incident.incident_id,
                status=status,
                critic_score=final.critic_score,
                fix_confidence=final.fix_confidence,
                hypotheses=final.hypotheses,
                errors=final.errors,
                metadata={
                    "iteration": final.iteration,
                    "max_iterations": final.max_iterations,
                    "llm_enabled": self._llm is not None,
                    "critic_threshold": self.config.critic_threshold,
                    "fix_confidence_threshold": self.config.fix_confidence_threshold,
                    "critic_reasoning": final.critic_reasoning,
                    "fix_summary": final.fix_summary,
                    "fix_confidence": final.fix_confidence,
                    "fix_reasoning": final.fix_reasoning,
                    "task_plan": final.task_plan,
                    "mesh_summary": final.mesh_summary,
                    "git_summary": final.git_summary,
                    "metrics_summary": final.metrics_summary,
                    "suspect_services": final.suspect_services,
                    "suspect_edges": final.suspect_edges,
                    "evidence_refs": final.evidence_refs,
                },
            )
            self.repository.save(report)
            self._persist_report_log(report)
            return report

        except Exception as exc:
            report = RcaReport(
                incident_id=incident.incident_id,
                status="failed",
                errors=[str(exc)],
                metadata={},
            )
            self.repository.save(report)
            self._persist_report_log(report)
            return report
