"""Brain orchestration engine."""

from __future__ import annotations

from dataclasses import dataclass, field

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
    def __init__(self, repository: InMemoryReportRepository | None = None, config: BrainEngineConfig | None = None) -> None:
        self.repository = repository or InMemoryReportRepository()
        self.config = config or BrainEngineConfig()
        self._llm: LLMClient | None = (
            LLMClient(self.config.llm_config)
            if self.config.llm_config and self.config.llm_config.is_configured
            else None
        )

    def run(self, incident: ApprovedIncident) -> RcaReport:
        state = BrainState(
            incident=incident,
            max_iterations=self.config.max_iterations,
            critic_threshold=self.config.critic_threshold,
        )

        try:
            for attempt in range(1, state.max_iterations + 1):
                state.iteration = attempt
                state = supervisor(state, llm=self._llm)
                state = git_scout(state, llm=self._llm)
                state = metric_analyst(state, llm=self._llm)
                state = rca_synthesizer(state, llm=self._llm)
                state = critic(state, llm=self._llm)

                if state.critic_score >= state.critic_threshold:
                    state.status = "completed"
                    break

            if state.status != "completed":
                state.status = "escalated"

            report = RcaReport(
                incident_id=state.incident.incident_id,
                status=state.status,
                critic_score=state.critic_score,
                hypotheses=state.hypotheses,
                errors=state.errors,
                metadata={
                    "iteration": state.iteration,
                    "max_iterations": state.max_iterations,
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
                metadata={"iteration": state.iteration},
            )
            self.repository.save(report)
            return report
