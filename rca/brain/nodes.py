"""Brain node implementations — real LLM prompts with stub fallback when no LLM is configured."""

from __future__ import annotations

from .models import BrainState, Hypothesis
from .llm import LLMClient


# ---------------------------------------------------------------------------
# supervisor
# ---------------------------------------------------------------------------

def supervisor(state: BrainState, llm: LLMClient | None = None) -> BrainState:
    """Analyze the incident and build a short investigation plan."""
    state.evidence_refs.append(f"incident:{state.incident.incident_id}")

    if llm:
        extra = state.incident.extra_context
        evidence_block = ""
        if extra:
            evidence_block = "\n\nAdditional evidence from the incident bundle:\n" + "\n".join(
                f"  [{k}]\n{v}" for k, v in extra.items()
            )
        prompt = f"""You are a senior SRE analyst. An incident has been reported.

Incident details:
- Service: {state.incident.service}
- Started at: {state.incident.started_at.isoformat()}
- Linked deployment: {state.incident.deployment_id or "none"}{evidence_block}

In 2-3 sentences, write a focused investigation plan: what evidence to gather and which failure modes to explore first.
Do not speculate beyond the facts given. Be concise and actionable."""
        state.task_plan = llm.generate(prompt)
    else:
        state.task_plan = (
            f"Investigate {state.incident.service} incident starting at "
            f"{state.incident.started_at}. "
            + (
                f"Linked deployment {state.incident.deployment_id} is a prime suspect."
                if state.incident.deployment_id
                else "No linked deployment — check infra and dependency signals."
            )
        )

    return state


# ---------------------------------------------------------------------------
# git_scout
# ---------------------------------------------------------------------------

def git_scout(state: BrainState, llm: LLMClient | None = None) -> BrainState:
    """Characterise the deployment change evidence relevant to this incident."""
    if state.incident.deployment_id:
        state.evidence_refs.append(f"deploy:{state.incident.deployment_id}")

    if llm:
        prompt = f"""You are a software engineer reviewing a deployment that coincided with a production incident.

Service: {state.incident.service}
Incident started: {state.incident.started_at.isoformat()}
Deployment ID: {state.incident.deployment_id or "none"}
Investigation plan: {state.task_plan}

In 3-5 sentences, describe which categories of code changes in this deployment are most likely to have caused the incident.
Prioritise: DB schema migrations, connection pool or timeout config changes, dependency version bumps, retry logic, caching changes.
If no deployment ID is present, state that the incident is likely infrastructure-related rather than code-related."""
        state.git_summary = llm.generate(prompt)
    else:
        if state.incident.deployment_id:
            state.git_summary = (
                f"Deployment {state.incident.deployment_id} found near the incident window. "
                "Review DB migrations, timeout settings, and dependency bumps."
            )
        else:
            state.git_summary = (
                "No deployment linked to this incident. "
                "Focus on infrastructure, traffic, and dependency signals."
            )

    return state


# ---------------------------------------------------------------------------
# metric_analyst
# ---------------------------------------------------------------------------

def metric_analyst(state: BrainState, llm: LLMClient | None = None) -> BrainState:
    """Characterise the metric anomaly pattern for this incident."""
    state.evidence_refs.append(f"metric:{state.incident.service}:p99")

    if llm:
        extra = state.incident.extra_context
        raw_logs_block = ""
        if extra:
            raw_logs_block = "\n\nRaw log evidence from the incident bundle:\n" + "\n".join(
                f"  [{k}]\n{v}" for k, v in extra.items()
            )
        prompt = f"""You are an SRE metrics expert analysing a production incident.

Service: {state.incident.service}
Incident started: {state.incident.started_at.isoformat()}
Deployment: {state.incident.deployment_id or "none"}
Investigation plan: {state.task_plan}
Git context: {state.git_summary}{raw_logs_block}

In 3-5 sentences, describe the likely metric anomaly pattern:
- Which RED metrics (request rate, error rate, latency/p99) and resource signals (CPU, memory, DB connections) would confirm this incident.
- Characterise the anomaly shape: step spike, slow creep, periodic oscillation, or sustained saturation.
- Note any downstream service signals that should be checked."""
        state.metrics_summary = llm.generate(prompt)
    else:
        state.metrics_summary = (
            f"Anomaly detected on {state.incident.service}. "
            "Expect elevated p99 latency and error rate in the incident window. "
            "Check CPU and connection pool saturation."
        )

    return state


# ---------------------------------------------------------------------------
# rca_synthesizer
# ---------------------------------------------------------------------------

def rca_synthesizer(state: BrainState, llm: LLMClient | None = None) -> BrainState:
    """Combine evidence into ranked root-cause hypotheses."""
    if llm:
        extra = state.incident.extra_context
        raw_logs_block = ""
        if extra:
            raw_logs_block = "\n\nRaw log evidence:\n" + "\n".join(
                f"  [{k}]\n{v}" for k, v in extra.items()
            )
        prompt = f"""You are an SRE root-cause analyst. Generate root-cause hypotheses for this incident.

Service: {state.incident.service}
Incident started: {state.incident.started_at.isoformat()}
Deployment: {state.incident.deployment_id or "none"}
Investigation plan: {state.task_plan}
Git context: {state.git_summary}
Metrics context: {state.metrics_summary}
Evidence refs: {", ".join(state.evidence_refs)}{raw_logs_block}

Return ONLY a valid JSON object — no markdown, no extra text:
{{
  "hypotheses": [
    {{
      "title": "Short hypothesis title (max 10 words)",
      "summary": "2-3 sentence explanation of this root cause and why the evidence supports it.",
      "confidence": 0.85,
      "evidence_refs": ["deploy:xxx", "metric:yyy"]
    }}
  ]
}}

Provide 2-3 hypotheses ranked from most to least likely.
Confidence must be between 0.0 and 1.0. If no deployment exists, lower confidence on code-change hypotheses."""
        try:
            parsed = llm.generate_json(prompt)
            state.hypotheses = [
                Hypothesis(
                    title=h["title"],
                    summary=h["summary"],
                    confidence=float(h["confidence"]),
                    evidence_refs=h.get("evidence_refs", list(state.evidence_refs)),
                )
                for h in parsed.get("hypotheses", [])
            ]
        except Exception as exc:
            state.errors.append(f"synthesizer_parse_error: {exc}")
            state.hypotheses = [
                Hypothesis(
                    title="Unknown root cause",
                    summary=f"LLM synthesis failed: {exc}",
                    confidence=0.30,
                    evidence_refs=list(state.evidence_refs),
                )
            ]
    else:
        # Deterministic stub used when no LLM is configured (e.g., in tests)
        if state.incident.deployment_id:
            confidence = 0.86
            title = "Recent rollout regression"
            summary = "Error spike aligns with deployment window."
        else:
            confidence = 0.62
            title = "Traffic or dependency instability"
            summary = "Signal exists but no deployment linkage found."

        state.hypotheses = [
            Hypothesis(
                title=title,
                summary=summary,
                confidence=confidence,
                evidence_refs=list(dict.fromkeys(state.evidence_refs)),
            )
        ]

    return state


# ---------------------------------------------------------------------------
# critic
# ---------------------------------------------------------------------------

def critic(state: BrainState, llm: LLMClient | None = None) -> BrainState:
    """Challenge the top hypothesis and produce a critic score."""
    if not state.hypotheses:
        state.critic_score = 0.0
        return state

    top = max(state.hypotheses, key=lambda h: h.confidence)

    if llm:
        prompt = f"""You are a critical SRE reviewer. Your job is to DISPROVE the proposed root cause.

Incident: {state.incident.service} at {state.incident.started_at.isoformat()}
Top hypothesis: "{top.title}"
Explanation: {top.summary}
Evidence: {", ".join(top.evidence_refs)}
Deployment: {state.incident.deployment_id or "none"}
Metrics context: {state.metrics_summary}
Investigation iteration: {state.iteration}

Ask yourself:
- Is there a simpler explanation that fits the data better?
- Did the regression start BEFORE the deployment went out?
- Is the evidence actually strong or circumstantial?
- Are there alternative causes (traffic spike, dependency failure, infra issue)?

Return ONLY a valid JSON object — no markdown, no extra text:
{{"score": 0.85, "reasoning": "Concise critique: what confirms or undermines the hypothesis."}}

Score guide: 0.9+ = definitive, 0.8 = strong, 0.6-0.79 = plausible, <0.6 = weak evidence."""
        try:
            parsed = llm.generate_json(prompt)
            state.critic_score = max(0.0, min(1.0, float(parsed.get("score", 0.5))))
            state.critic_reasoning = parsed.get("reasoning", "")
        except Exception as exc:
            state.errors.append(f"critic_parse_error: {exc}")
            decay = max(0.0, 0.02 * (state.iteration - 1))
            state.critic_score = max(0.0, min(1.0, top.confidence - decay))
    else:
        # Deterministic stub
        decay = max(0.0, 0.02 * (state.iteration - 1))
        state.critic_score = max(0.0, min(1.0, top.confidence - decay))

    return state
