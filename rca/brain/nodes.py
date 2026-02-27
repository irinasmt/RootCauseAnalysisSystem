"""Brain node implementations — real LLM prompts with stub fallback when no LLM is configured."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from statistics import median

from .models import (
    BrainState,
    CriticOutput,
    FixAdvisorOutput,
    GitScoutOutput,
    Hypothesis,
    MeshScoutOutput,
    MetricAnalystOutput,
    SupervisorOutput,
    SynthesizerOutput,
)
from .llm import LLMClient


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _extract_mesh_events(extra_context: dict) -> list[dict]:
    raw = extra_context.get("mesh_events")
    if raw is None:
        raw = extra_context.get("mesh_events_jsonl")

    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict)]

    if isinstance(raw, str):
        rows: list[dict] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                if isinstance(payload, dict):
                    rows.append(payload)
            except json.JSONDecodeError:
                continue
        return rows

    return []


def _find_suspects_from_mesh(state: BrainState) -> tuple[list[str], list[str]]:
    """Return (suspect_services, suspect_edges) from incident mesh evidence.

    A dependency is suspect when, in the incident window, calls from the
    impacted service to that upstream show server errors, high latency, or
    retry spikes.
    """
    events = _extract_mesh_events(state.incident.extra_context)
    if not events:
        return [], []

    service = state.incident.service
    start = state.incident.started_at
    pre_start = start - timedelta(minutes=30)

    baseline_latency: list[float] = []
    current: dict[str, dict[str, float]] = {}

    for e in events:
        if e.get("service") != service:
            continue

        ts_raw = e.get("ts")
        if not isinstance(ts_raw, str):
            continue
        try:
            ts = datetime.fromisoformat(ts_raw)
        except ValueError:
            continue

        latency = float(e.get("latency_ms", 0) or 0)
        retries = float(e.get("retry_count", 0) or 0)
        code = int(e.get("response_code", 0) or 0)
        upstream = str(e.get("upstream", "")).strip()
        if not upstream:
            continue

        if pre_start <= ts < start:
            baseline_latency.append(latency)

        if ts < start:
            continue

        stats = current.setdefault(upstream, {
            "count": 0.0,
            "err": 0.0,
            "lat_sum": 0.0,
            "retry_sum": 0.0,
        })
        stats["count"] += 1.0
        stats["lat_sum"] += latency
        stats["retry_sum"] += retries
        if code >= 500:
            stats["err"] += 1.0

    if not current:
        return [], []

    baseline = median(baseline_latency) if baseline_latency else 0.0
    suspects: list[str] = []
    suspect_edges: list[str] = []

    for upstream, stats in current.items():
        count = max(stats["count"], 1.0)
        err_rate = stats["err"] / count
        avg_latency = stats["lat_sum"] / count
        avg_retry = stats["retry_sum"] / count

        degraded = (
            err_rate >= 0.10
            or avg_retry >= 3.0
            or (baseline > 0 and avg_latency >= baseline * 2.0)
            or avg_latency >= 500.0
        )
        if degraded:
            suspects.append(upstream)
            suspect_edges.append(f"{service}->{upstream}")

    return _dedupe(suspects), _dedupe(suspect_edges)


def _query_scopes(state: BrainState) -> list[str]:
    candidates = state.suspect_services or [state.incident.service]
    scopes = [s.strip() for s in candidates if isinstance(s, str) and s.strip()]
    return _dedupe(scopes) or [state.incident.service]


# ---------------------------------------------------------------------------
# mesh_scout
# ---------------------------------------------------------------------------

def mesh_scout(state: BrainState, mesh_driver=None) -> BrainState:
    """Traverse the service mesh graph to rank suspect upstream services.

    Queries the mesh Neo4j instance for:
    - DEPENDS_ON edges (architecture topology, up to 2 hops from incident service)
    - OBSERVED_CALL edges (live stats: error_count, call_count, avg_latency_ms)

    Suspects are ranked:
      1. Services with OBSERVED_CALL showing high error_count (observed degradation)
      2. Services with OBSERVED_CALL showing high avg_latency
      3. Services reachable only via DEPENDS_ON (in scope for git search, lower priority)

    Populates state.suspect_services BEFORE git_scout runs, so the repo graph
    is queried for the right services rather than only the triggering service.

    Falls back to raw mesh_events_jsonl parsing if no driver is provided.
    """
    if mesh_driver is not None:
        try:
            cypher = """
            MATCH (trigger:MeshService {name: $service})-[:DEPENDS_ON*1..2]->(dep:MeshService)
            OPTIONAL MATCH (trigger)-[o:OBSERVED_CALL]->(dep)
            RETURN DISTINCT
                dep.name AS svc,
                dep.is_external AS is_external,
                o.error_count AS error_count,
                o.call_count AS call_count,
                o.avg_latency_ms AS avg_latency_ms,
                o.p99_latency_ms AS p99_latency_ms
            """
            with mesh_driver.session() as session:
                rows = list(session.run(cypher, service=state.incident.service))

            suspects_observed: list[tuple[str, float]] = []  # (name, degradation_score)
            suspects_arch_only: list[str] = []
            summary_lines: list[str] = []

            for row in rows:
                svc = row["svc"]
                error_count = row["error_count"] or 0
                call_count = row["call_count"] or 0
                avg_lat = row["avg_latency_ms"] or 0.0
                p99_lat = row["p99_latency_ms"] or 0.0
                err_rate = (error_count / call_count) if call_count > 0 else 0.0

                if call_count > 0:
                    # Score: weight error rate heavily, normalise latency as secondary signal
                    score = err_rate * 10.0 + (avg_lat / 100.0)
                    suspects_observed.append((svc, score))
                    summary_lines.append(
                        f"  {svc}: {call_count} calls, {error_count} errors "
                        f"({err_rate:.0%} err rate), avg {avg_lat:.0f}ms, p99 {p99_lat:.0f}ms"
                    )
                    state.evidence_refs.append(f"mesh:observed:{svc}")
                else:
                    suspects_arch_only.append(svc)
                    summary_lines.append(f"  {svc}: architecture dependency (no observed calls in this scenario)")
                    state.evidence_refs.append(f"mesh:depends_on:{svc}")

            # Rank: observed services by score desc, then arch-only, incident service always first
            ranked_observed = [s for s, _ in sorted(suspects_observed, key=lambda x: -x[1])]
            state.suspect_services = _dedupe([state.incident.service, *ranked_observed, *suspects_arch_only])
            state.suspect_edges = [f"{state.incident.service}->{s}" for s in ranked_observed]

            if summary_lines:
                state.mesh_summary = (
                    f"Mesh graph traversal from '{state.incident.service}' "
                    f"({len(ranked_observed)} observed degraded, {len(suspects_arch_only)} arch-only):\n"
                    + "\n".join(summary_lines)
                )
            else:
                state.mesh_summary = f"No dependencies found for '{state.incident.service}' in mesh graph."

            state.evidence_refs = _dedupe(state.evidence_refs)
            MeshScoutOutput(suspect_services=state.suspect_services, mesh_summary=state.mesh_summary)
            return state

        except Exception:  # noqa: BLE001
            pass  # fall through to raw-event fallback

    # Fallback: derive suspects from raw mesh_events_jsonl in extra_context
    suspects, suspect_edges = _find_suspects_from_mesh(state)
    if suspects:
        state.suspect_services = _dedupe([state.incident.service, *suspects])
        state.suspect_edges = suspect_edges
        state.mesh_summary = f"Suspect services from raw mesh events (no graph driver): {', '.join(suspects)}"
    else:
        state.suspect_services = _dedupe([state.incident.service])
        state.mesh_summary = "No mesh suspects found (no graph driver, no qualifying events)."

    state.evidence_refs = _dedupe(state.evidence_refs)
    MeshScoutOutput(suspect_services=state.suspect_services, mesh_summary=state.mesh_summary)
    return state


# ---------------------------------------------------------------------------
# supervisor
# ---------------------------------------------------------------------------

def supervisor(state: BrainState, llm: LLMClient | None = None) -> BrainState:
    """Analyze the incident and build a short investigation plan."""
    if not state.suspect_services:
        state.suspect_services = [state.incident.service]
    elif state.incident.service not in state.suspect_services:
        state.suspect_services.insert(0, state.incident.service)
    state.suspect_services = _dedupe(state.suspect_services)

    state.evidence_refs.append(f"incident:{state.incident.incident_id}")
    state.evidence_refs = _dedupe(state.evidence_refs)

    if llm:
        extra = state.incident.extra_context
        evidence_block = ""
        if extra:
            evidence_block = "\n\nAdditional evidence from the incident bundle:\n" + "\n".join(
                f"  [{k}]\n{v}" for k, v in extra.items()
            )
        refinement_block = ""
        if state.iteration > 1 and state.critic_reasoning:
            refinement_block = f"\n\nA critic flagged these gaps in the previous investigation:\n{state.critic_reasoning}\nFocus on gathering stronger evidence for the existing theory rather than pivoting to a new one, unless the critic has explicitly ruled it out."
        prompt = f"""You are a senior SRE analyst. An incident has been reported.

Incident details:
- Service: {state.incident.service}
- Started at: {state.incident.started_at.isoformat()}
- Linked deployment: {state.incident.deployment_id or "none"}{evidence_block}{refinement_block}

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

    # Validate supervisor output before passing to next node
    SupervisorOutput(task_plan=state.task_plan, evidence_refs=state.evidence_refs)
    return state


# ---------------------------------------------------------------------------
# git_scout
# ---------------------------------------------------------------------------

def _format_graph_nodes(nodes: list) -> str:
    """Format NodeWithScore objects from PropertyGraphIndex retriever into a
    human-readable summary string.
    """
    if not nodes:
        return ""
    lines: list[str] = []
    for nws in nodes:
        meta = getattr(nws, "node", nws).metadata
        status = meta.get("status", "UNKNOWN")
        path = meta.get("file_path", "?")
        symbol = meta.get("symbol_name") or meta.get("name", "?")
        kind = meta.get("symbol_kind", "symbol")
        delta = meta.get("semantic_delta", "")
        line = f"  [{status}] {kind} '{symbol}' in {path}"
        if delta:
            line += f"\n    Delta: {delta[:120]}"
        text = getattr(getattr(nws, "node", nws), "text", "")
        if isinstance(text, str) and text.strip():
            snippet = " ".join(text.strip().splitlines()[:2])
            line += f"\n    Patch: {snippet[:180]}"
        lines.append(line)
    return "\n".join(lines)


def git_scout(
    state: BrainState,
    llm: LLMClient | None = None,
    graph_index=None,
) -> BrainState:
    """Characterise the deployment change evidence relevant to this incident.

    When a ``graph_index`` (LlamaIndex ``PropertyGraphIndex``) is provided the
    node queries the persistent differential graph via ``.as_retriever()`` and
    builds a structured summary from ``NodeWithScore`` metadata.  This path
    performs zero raw-diff string parsing — all symbol-level context is already
    in the graph.

    Falls back to LLM-only or stub summarisation when no graph is available.
    """
    if state.incident.deployment_id:
        state.evidence_refs.append(f"deploy:{state.incident.deployment_id}")

    # ------------------------------------------------------------------
    # Path 1: Graph-backed retrieval (preferred — structured, no raw diff)
    # ------------------------------------------------------------------
    graph_context = ""
    if graph_index is not None:
        try:
            retriever = graph_index.as_retriever(include_text=False)
            collected_lines: list[str] = []
            for scope_service in _query_scopes(state):
                query = (
                    f"service:{scope_service} "
                    f"deployment:{state.incident.deployment_id or 'unknown'} "
                    "status:(MODIFIED OR ADDED) "
                    f"incident:{state.incident.started_at.isoformat()}"
                )
                results = retriever.retrieve(query)
                formatted = _format_graph_nodes(results)
                if formatted:
                    collected_lines.append(f"Service {scope_service}:\n{formatted}")
                    state.evidence_refs.append(f"graph:{scope_service}")

            graph_context = "\n\n".join(collected_lines)
            state.evidence_refs = _dedupe(state.evidence_refs)
        except Exception:  # noqa: BLE001
            # Graph retrieval failure is non-fatal — degrade gracefully
            graph_context = ""

    # ------------------------------------------------------------------
    # Path 2: LLM summarisation (with or without graph context)
    # ------------------------------------------------------------------
    if llm:
        graph_block = ""
        if graph_context:
            graph_block = f"\n\nDifferential graph context (structured, no raw diff):\n{graph_context}"
        prompt = f"""You are a software engineer reviewing a deployment that coincided with a production incident.

Service: {state.incident.service}
Suspect services in scope: {", ".join(_query_scopes(state))}
Incident started: {state.incident.started_at.isoformat()}
Deployment ID: {state.incident.deployment_id or "none"}
Investigation plan: {state.task_plan}{graph_block}

In 3-5 sentences, describe which categories of code changes in this deployment are most likely to have caused the incident.
Prioritise: DB schema migrations, connection pool or timeout config changes, dependency version bumps, retry logic, caching changes.
If no deployment ID is present, state that the incident is likely infrastructure-related rather than code-related."""
        state.git_summary = llm.generate(prompt)

    # ------------------------------------------------------------------
    # Path 3: Graph context alone (no LLM)
    # ------------------------------------------------------------------
    elif graph_context:
        state.git_summary = (
            "Differential graph nodes across suspect scope:\n"
            f"{graph_context}"
        )

    # ------------------------------------------------------------------
    # Path 4: Stub fallback (no LLM, no graph)
    # ------------------------------------------------------------------
    else:
        if state.incident.deployment_id:
            state.git_summary = (
                f"Deployment {state.incident.deployment_id} found near the incident window. "
                "Review DB migrations, timeout settings, and dependency bumps across suspect services."
            )
        else:
            state.git_summary = (
                "No deployment linked to this incident. "
                "Focus on infrastructure, traffic, and dependency signals across suspect services."
            )

    # Validate git_scout output before passing to next node
    GitScoutOutput(git_summary=state.git_summary)
    return state


# ---------------------------------------------------------------------------
# metric_analyst
# ---------------------------------------------------------------------------

def metric_analyst(state: BrainState, llm: LLMClient | None = None) -> BrainState:
    """Characterise the metric anomaly pattern for this incident."""
    state.evidence_refs.append(f"metric:{state.incident.service}:p99")

    # Only run raw-event suspect detection if mesh_scout didn't already populate suspects
    # (mesh_scout sets >1 entry when it finds graph-based dependencies)
    if len(state.suspect_services) <= 1:
        suspect_services, suspect_edges = _find_suspects_from_mesh(state)
        if suspect_services:
            merged = [state.incident.service, *state.suspect_services, *suspect_services]
            state.suspect_services = _dedupe(merged)
            state.suspect_edges = _dedupe([*state.suspect_edges, *suspect_edges])
            for svc in suspect_services:
                state.evidence_refs.append(f"mesh-suspect:{svc}")
                state.evidence_refs.append(f"logs:{svc}")
    else:
        # mesh_scout already found suspects — just add evidence refs for them
        for svc in state.suspect_services[1:]:  # skip incident service itself
            state.evidence_refs.append(f"logs:{svc}")

    state.evidence_refs = _dedupe(state.evidence_refs)

    if llm:
        extra = state.incident.extra_context
        raw_logs_block = ""
        if extra:
            raw_logs_block = "\n\nRaw log evidence from the incident bundle:\n" + "\n".join(
                f"  [{k}]\n{v}" for k, v in extra.items()
            )
        prompt = f"""You are an SRE metrics expert analysing a production incident.

Service: {state.incident.service}
Suspect services in scope: {", ".join(_query_scopes(state))}
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
        scope_line = (
            f" Suspect dependencies: {', '.join(state.suspect_services)}."
            if state.suspect_services
            else ""
        )
        state.metrics_summary = (
            f"Anomaly detected on {state.incident.service}. "
            "Expect elevated p99 latency and error rate in the incident window. "
            "Check CPU and connection pool saturation."
            + scope_line
        )

    # Validate metric_analyst output before passing to next node
    MetricAnalystOutput(metrics_summary=state.metrics_summary, evidence_refs=state.evidence_refs)
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
        critique_block = ""
        if state.iteration > 1 and state.critic_reasoning:
            critique_block = f"\n\nA critic reviewed the previous hypotheses and noted these gaps in the evidence:\n{state.critic_reasoning}\nKeep the same hypotheses if they are still the best fit. Strengthen them by citing more specific evidence from the logs and metrics. Do NOT invent new root causes unless the evidence clearly rules out the existing ones."
        prompt = f"""You are an SRE root-cause analyst. Generate root-cause hypotheses for this incident.

Service: {state.incident.service}
Incident started: {state.incident.started_at.isoformat()}
Deployment: {state.incident.deployment_id or "none"}
Investigation plan: {state.task_plan}
Git context: {state.git_summary}
Metrics context: {state.metrics_summary}
Evidence refs: {", ".join(state.evidence_refs)}{raw_logs_block}{critique_block}

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

    # Validate synthesizer output before passing to next node
    SynthesizerOutput(hypotheses=state.hypotheses)
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
            state.critic_reasoning = parsed.get("reasoning", "") or "LLM returned no reasoning."
        except Exception as exc:
            state.errors.append(f"critic_parse_error: {exc}")
            decay = max(0.0, 0.02 * (state.iteration - 1))
            state.critic_score = max(0.0, min(1.0, top.confidence - decay))
            state.critic_reasoning = f"LLM critic failed ({exc}); stub score applied."
    else:
        # Deterministic stub
        decay = max(0.0, 0.02 * (state.iteration - 1))
        state.critic_score = max(0.0, min(1.0, top.confidence - decay))
        state.critic_reasoning = f"Stub evaluation: top hypothesis confidence {top.confidence:.2f} with decay {decay:.2f}."

    # Validate critic output — surfaces bad scores early
    CriticOutput(critic_score=state.critic_score, critic_reasoning=state.critic_reasoning)
    return state


# ---------------------------------------------------------------------------
# fix_advisor
# ---------------------------------------------------------------------------

def fix_advisor(state: BrainState, llm: LLMClient | None = None) -> BrainState:
    """Recommend the best remediation that holds across ALL plausible causes.

    The critic may flag evidential ambiguity (low cause_confidence), but the
    on-call engineer still needs an action.  fix_advisor asks: "what single
    intervention resolves the incident regardless of which hypothesis is
    correct?"  fix_confidence is independent of cause certainty and drives
    the final escalation decision.
    """
    if not state.hypotheses:
        state.fix_summary = "No hypotheses available — manual investigation required."
        state.fix_confidence = 0.0
        state.fix_reasoning = "No hypotheses to base a fix on."
        return state

    top = max(state.hypotheses, key=lambda h: h.confidence)
    hyp_list = "\n".join(
        f"  {i + 1}. {h.title} (confidence={h.confidence:.2f})"
        for i, h in enumerate(state.hypotheses)
    )

    if llm:
        prompt = f"""You are an SRE fix advisor. The investigation team has produced hypotheses but the exact root cause is uncertain. Your job is NOT to determine the exact cause — the critic already flagged ambiguity. Your job is to recommend the single best remediation that is safe and effective across ALL plausible causes.

Incident: {state.incident.service} at {state.incident.started_at.isoformat()}
Top hypothesis: "{top.title}"
Summary: {top.summary}
Critic's concern: {state.critic_reasoning}

All hypotheses under consideration:
{hyp_list}

Ask yourself:
- Is there a single fix that resolves the incident regardless of which hypothesis is correct?
- What is the minimum-risk intervention an on-call engineer can safely apply right now?
- Who owns the affected component — can we fix it ourselves or do we need to escalate to a third party?
- Does the fix hold even if the critic's alternative explanation turns out to be true?

Return ONLY a valid JSON object — no markdown, no extra text:
{{"fix": "Concise action: what to do and on which service/config", "fix_confidence": 0.90, "fix_reasoning": "This fix is valid because it addresses the symptom regardless of cause X or Y..."}}

fix_confidence guide: 0.9+ = fix is safe under all plausible causes, 0.7-0.89 = covers most cases with low risk, <0.7 = uncertain or depends on which hypothesis is correct."""
        try:
            parsed = llm.generate_json(prompt)
            state.fix_summary = str(parsed.get("fix", "")).strip() or "No fix suggested."
            state.fix_confidence = max(0.0, min(1.0, float(parsed.get("fix_confidence", 0.5))))
            state.fix_reasoning = str(parsed.get("fix_reasoning", "")).strip() or "No reasoning provided."
        except Exception as exc:
            state.errors.append(f"fix_advisor_parse_error: {exc}")
            state.fix_summary = f"Fix advisor failed ({exc}). Manual review recommended."
            state.fix_confidence = 0.0
            state.fix_reasoning = f"LLM fix advisor error: {exc}"
    else:
        # Deterministic stub: derive fix_confidence from hypothesis agreement
        avg_confidence = sum(h.confidence for h in state.hypotheses) / len(state.hypotheses)
        state.fix_confidence = round(min(1.0, avg_confidence * 0.9), 2)
        state.fix_summary = f"Investigate and remediate: {top.title.lower()} on {state.incident.service}."
        state.fix_reasoning = (
            f"Stub fix advisor: derived from top hypothesis '{top.title}' "
            f"(confidence {top.confidence:.2f}) averaged across {len(state.hypotheses)} hypothesis/es."
        )

    # Validate fix_advisor output
    FixAdvisorOutput(
        fix_summary=state.fix_summary,
        fix_confidence=state.fix_confidence,
        fix_reasoning=state.fix_reasoning,
    )
    return state
