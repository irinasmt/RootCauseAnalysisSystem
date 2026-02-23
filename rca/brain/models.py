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
