"""Typed contracts for the Differential Indexer."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Repository adapter protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class RepositoryAdapter(Protocol):
    """Adapter that provides file content and raw diffs from a VCS backend.

    The indexer depends on this protocol only — no concrete VCS client
    is imported here. Implementations are injected at construction time.
    """

    def get_file(self, path: str, commit_sha: str) -> str:
        """Return the full text content of *path* at *commit_sha*."""
        ...

    def get_diff(self, path: str, commit_sha: str) -> str:
        """Return the unified diff string for *path* introduced by *commit_sha*."""
        ...

    def list_changed_files(self, commit_sha: str) -> list[str]:
        """Return all file paths changed by *commit_sha*."""
        ...

    def list_commits(self, since_days: int, branch: str = "main") -> list[str]:
        """Return commit SHAs on *branch* within the last *since_days* calendar days."""
        ...


# ---------------------------------------------------------------------------
# Request / config models
# ---------------------------------------------------------------------------

class RepoEntry(BaseModel):
    """A single service → repository mapping entry."""

    repo_url: str
    language: str = "python"
    default_branch: str = "main"


class DifferentialIndexerRequest(BaseModel):
    """Input for a single differential indexing operation."""

    service: str = Field(min_length=1)
    commit_sha: str = Field(min_length=7)
    file_paths: list[str] = Field(default_factory=list,
                                  description="Explicit file list. Empty = auto-detect from diff.")
    enable_semantic_delta: bool = False


class BackfillPolicy(BaseModel):
    """Controls bounded onboarding backfill scope."""

    max_days: int = Field(default=90, gt=0,
                          description="Walk back at most this many calendar days from today.")
    batch_size: int = Field(default=20, gt=0,
                            description="Maximum commits processed per backfill batch.")
    branch: str = "main"


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

class IndexingDiagnostic(BaseModel):
    """Structured error / warning emitted when indexing cannot complete cleanly."""

    severity: str = Field(description="'error' or 'warning'")
    stage: str = Field(description="Which pipeline stage raised this (parse/project/upsert/backfill)")
    message: str
    file_path: str | None = None
    commit_sha: str | None = None
