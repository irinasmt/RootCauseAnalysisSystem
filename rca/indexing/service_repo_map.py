"""ServiceRepoMap adapter — resolves service name → (repo_url, language)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import RepoEntry


class ServiceRepoMap(ABC):
    """Abstract contract for service → repository resolution.

    Inject a concrete implementation at construction time.  The
    ``InMemoryServiceRepoMap`` is the default for testing and local dev;
    production deployments substitute a config-file or API-backed impl.
    """

    @abstractmethod
    def get(self, service: str) -> RepoEntry:
        """Return the ``RepoEntry`` for *service*.

        Raises
        ------
        KeyError
            If *service* is not registered.
        """
        ...

    @abstractmethod
    def register(self, service: str, entry: RepoEntry) -> None:
        """Register or overwrite the mapping for *service*."""
        ...

    def has(self, service: str) -> bool:
        """Return ``True`` if *service* is registered."""
        try:
            self.get(service)
            return True
        except KeyError:
            return False


class InMemoryServiceRepoMap(ServiceRepoMap):
    """Mutable in-memory implementation — suitable for tests and local dev."""

    def __init__(self, entries: dict[str, RepoEntry] | None = None) -> None:
        self._map: dict[str, RepoEntry] = dict(entries or {})

    def get(self, service: str) -> RepoEntry:
        if service not in self._map:
            raise KeyError(
                f"Service '{service}' is not registered in ServiceRepoMap. "
                "Register it via InMemoryServiceRepoMap.register() before indexing."
            )
        return self._map[service]

    def register(self, service: str, entry: RepoEntry) -> None:
        self._map[service] = entry

    def __len__(self) -> int:
        return len(self._map)
