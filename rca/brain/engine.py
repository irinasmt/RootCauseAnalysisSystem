"""Brain orchestration engine — LangGraph StateGraph implementation.

Graph topology:
    supervisor → git_scout → metric_analyst → rca_synthesizer → critic
                    ↑                                                |
                    └──────────── (score < threshold) ──────────────┘
                                         END (score >= threshold OR max_iterations reached)

Pydantic output models in nodes.py validate each node's produced fields before
control passes to the next node, surfacing bad output as early as possible.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from langgraph.graph import END, StateGraph

from .llm import LLMClient, LLMConfig
from .models import ApprovedIncident, BrainState, RcaReport
from .nodes import critic, git_scout, metric_analyst, rca_synthesizer, supervisor
from .repository import InMemoryReportRepository


@dataclass
class BrainEngineConfig:
    critic_threshold: float = 0.80
    max_iterations: int = 3
    llm_config: LLMConfig | None = field(default=None)


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

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_graph(self):
        llm = self._llm
        config = self.config

        # Node wrappers: call the existing node function, return a dict so
        # LangGraph can update the Pydantic state.  Each underlying node runs
        # its own Pydantic output validation before returning.

        def _supervisor_node(state: BrainState) -> dict:
            # Increment iteration counter on every entry into the supervisor
            updated = state.model_copy(update={"iteration": state.iteration + 1})
            return supervisor(updated, llm=llm).model_dump()

        def _git_scout_node(state: BrainState) -> dict:
            return git_scout(state, llm=llm).model_dump()

        def _metric_analyst_node(state: BrainState) -> dict:
            return metric_analyst(state, llm=llm).model_dump()

        def _rca_synthesizer_node(state: BrainState) -> dict:
            return rca_synthesizer(state, llm=llm).model_dump()

        def _critic_node(state: BrainState) -> dict:
            return critic(state, llm=llm).model_dump()

        def _route_after_critic(state: BrainState) -> str:
            """Conditional edge: loop back to supervisor or finish."""
            if state.critic_score >= config.critic_threshold:
                return "done"
            if state.iteration >= config.max_iterations:
                return "done"
            return "refine"

        graph = StateGraph(BrainState)

        graph.add_node("supervisor", _supervisor_node)
        graph.add_node("git_scout", _git_scout_node)
        graph.add_node("metric_analyst", _metric_analyst_node)
        graph.add_node("rca_synthesizer", _rca_synthesizer_node)
        graph.add_node("critic", _critic_node)

        graph.set_entry_point("supervisor")
        graph.add_edge("supervisor", "git_scout")
        graph.add_edge("git_scout", "metric_analyst")
        graph.add_edge("metric_analyst", "rca_synthesizer")
        graph.add_edge("rca_synthesizer", "critic")
        graph.add_conditional_edges(
            "critic",
            _route_after_critic,
            {"done": END, "refine": "supervisor"},
        )

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

            status = "completed" if final.critic_score >= self.config.critic_threshold else "escalated"

            report = RcaReport(
                incident_id=final.incident.incident_id,
                status=status,
                critic_score=final.critic_score,
                hypotheses=final.hypotheses,
                errors=final.errors,
                metadata={
                    "iteration": final.iteration,
                    "max_iterations": final.max_iterations,
                    "llm_enabled": self._llm is not None,
                },
            )
            self.repository.save(report)
            return report

        except Exception as exc:
            report = RcaReport(
                incident_id=incident.incident_id,
                status="failed",
                errors=[str(exc)],
                metadata={},
            )
            self.repository.save(report)
            return report
