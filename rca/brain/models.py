"""Typed models for Brain execution."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ApprovedIncident(BaseModel):
    incident_id: str = Field(min_length=3)
    service: str = Field(min_length=2)
    started_at: datetime
    deployment_id: str | None = None
    extra_context: dict[str, Any] = Field(default_factory=dict)
    """Freeform evidence bag — log snippets, metric snapshots, ground truth, etc."""


class Hypothesis(BaseModel):
    title: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)


class RcaReport(BaseModel):
    incident_id: str
    status: Literal["completed", "escalated", "failed"]
    critic_score: float = Field(ge=0.0, le=1.0, default=0.0)
    fix_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrainState(BaseModel):
    incident: ApprovedIncident
    iteration: int = 0
    max_iterations: int = 3
    critic_threshold: float = 0.80
    evidence_refs: list[str] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    critic_score: float = 0.0
    status: Literal["running", "completed", "escalated", "failed"] = "running"
    errors: list[str] = Field(default_factory=list)
    # Node outputs carried through state
    task_plan: str = ""
    git_summary: str = ""
    metrics_summary: str = ""
    critic_reasoning: str = ""
    # Dependency-aware scope discovered during runtime analysis
    suspect_services: list[str] = Field(default_factory=list)
    suspect_edges: list[str] = Field(default_factory=list)
    # Mesh graph traversal summary (populated by mesh_scout)
    mesh_summary: str = ""
    # Fix advisor outputs (populated by fix_advisor)
    fix_summary: str = ""
    fix_confidence: float = 0.0
    fix_reasoning: str = ""


# ---------------------------------------------------------------------------
# Per-node output validators — each node validates its produced fields
# through these models before passing state to the next node.
# ---------------------------------------------------------------------------

class MeshScoutOutput(BaseModel):
    suspect_services: list[str] = Field(min_length=1, description="At least the incident service must be in scope")
    mesh_summary: str = Field(min_length=1, description="Mesh traversal summary must be non-empty")


class SupervisorOutput(BaseModel):
    task_plan: str = Field(min_length=1, description="Investigation plan must be non-empty")
    evidence_refs: list[str] = Field(min_length=1, description="At least one evidence ref required")


class GitScoutOutput(BaseModel):
    git_summary: str = Field(min_length=1, description="Git/deployment context must be non-empty")


class MetricAnalystOutput(BaseModel):
    metrics_summary: str = Field(min_length=1, description="Metrics analysis must be non-empty")
    evidence_refs: list[str] = Field(min_length=1, description="At least one evidence ref required")


class SynthesizerOutput(BaseModel):
    hypotheses: list[Hypothesis] = Field(min_length=1, description="At least one hypothesis required")


class CriticOutput(BaseModel):
    critic_score: float = Field(ge=0.0, le=1.0, description="Score must be between 0.0 and 1.0")
    critic_reasoning: str = Field(min_length=1, description="Critic must provide reasoning")


class FixAdvisorOutput(BaseModel):
    fix_summary: str = Field(min_length=1, description="Suggested fix must be non-empty")
    fix_confidence: float = Field(ge=0.0, le=1.0, description="Fix confidence must be between 0.0 and 1.0")
    fix_reasoning: str = Field(min_length=1, description="Fix reasoning must be non-empty")
