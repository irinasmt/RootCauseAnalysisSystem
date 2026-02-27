"""Bounded onboarding backfill runner for new service registration."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from .models import BackfillPolicy, DifferentialIndexerRequest, IndexingDiagnostic, RepositoryAdapter
from .service_repo_map import ServiceRepoMap

if TYPE_CHECKING:
    from .differential_indexer import DifferentialIndexer


class BackfillRunner:
    """Runs bounded commit-history backfill for a service on first onboarding.

    Walks backwards through the commit log for *service*, stopping at the
    ``BackfillPolicy.max_days`` boundary or the end of history — whichever
    comes first.  Processes commits in batches of ``BackfillPolicy.batch_size``.

    Parameters
    ----------
    indexer:
        A ``DifferentialIndexer`` instance already wired to a graph store.
    service_repo_map:
        Used to resolve service → repo entry (for branch + language info).
    repo_adapter:
        ``RepositoryAdapter`` providing ``list_commits`` and diff/file methods.
    """

    def __init__(
        self,
        indexer: "DifferentialIndexer",
        service_repo_map: ServiceRepoMap,
        repo_adapter: RepositoryAdapter,
    ) -> None:
        self._indexer = indexer
        self._service_repo_map = service_repo_map
        self._repo = repo_adapter

    def run(
        self, service: str, policy: BackfillPolicy | None = None
    ) -> tuple[int, int, list[IndexingDiagnostic]]:
        """Execute backfill for *service*.

        Parameters
        ----------
        service:
            Name of the service to backfill. Must be registered in
            ``ServiceRepoMap`` before this is called.
        policy:
            Override ``BackfillPolicy``. Uses default (90 days, batch 20)
            if omitted.

        Returns
        -------
        (commits_processed, nodes_upserted, diagnostics)
        """
        if policy is None:
            policy = BackfillPolicy()

        diagnostics: list[IndexingDiagnostic] = []

        # Validate service is registered
        if not self._service_repo_map.has(service):
            diagnostics.append(IndexingDiagnostic(
                severity="error",
                stage="backfill",
                message=(
                    f"Service '{service}' is not registered in ServiceRepoMap. "
                    "Register it before running backfill."
                ),
            ))
            return 0, 0, diagnostics

        # Walk recent commits within the policy window
        try:
            commit_shas = self._repo.list_commits(
                since_days=policy.max_days,
                branch=policy.branch,
            )
        except Exception as exc:  # noqa: BLE001
            diagnostics.append(IndexingDiagnostic(
                severity="error",
                stage="backfill",
                message=f"list_commits failed: {exc}",
            ))
            return 0, 0, diagnostics

        if not commit_shas:
            diagnostics.append(IndexingDiagnostic(
                severity="warning",
                stage="backfill",
                message=(
                    f"No commits found within {policy.max_days} days on "
                    f"branch '{policy.branch}' for service '{service}'."
                ),
            ))
            return 0, 0, diagnostics

        total_commits = 0
        total_nodes = 0

        # Process in batches
        for batch_start in range(0, len(commit_shas), policy.batch_size):
            batch = commit_shas[batch_start: batch_start + policy.batch_size]
            for sha in batch:
                request = DifferentialIndexerRequest(service=service, commit_sha=sha)
                nodes_upserted, commit_diags = self._indexer.index_commit(request)
                total_nodes += nodes_upserted
                total_commits += 1
                diagnostics.extend(commit_diags)

        return total_commits, total_nodes, diagnostics

    # ------------------------------------------------------------------
    # Convenience: register + backfill in one call
    # ------------------------------------------------------------------

    def onboard_service(
        self,
        service: str,
        policy: BackfillPolicy | None = None,
    ) -> tuple[int, int, list[IndexingDiagnostic]]:
        """Convenience wrapper: validate service is registered, then backfill.

        Raises
        ------
        KeyError
            If *service* is not registered in ``ServiceRepoMap``.
        """
        if not self._service_repo_map.has(service):
            raise KeyError(
                f"Service '{service}' must be registered in ServiceRepoMap before onboarding."
            )
        return self.run(service, policy=policy)
