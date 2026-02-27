"""Unit tests for ServiceRepoMap adapter contract and InMemoryServiceRepoMap."""

from __future__ import annotations

import pytest

from rca.indexing.models import RepoEntry
from rca.indexing.service_repo_map import InMemoryServiceRepoMap


class TestInMemoryServiceRepoMap:
    def _map(self) -> InMemoryServiceRepoMap:
        m = InMemoryServiceRepoMap()
        m.register("payment-api", RepoEntry(repo_url="https://github.com/org/payment", language="csharp"))
        m.register("auth-svc", RepoEntry(repo_url="https://github.com/org/auth", language="python"))
        return m

    def test_register_and_get(self):
        m = self._map()
        entry = m.get("payment-api")
        assert entry.repo_url == "https://github.com/org/payment"
        assert entry.language == "csharp"

    def test_has_registered_service(self):
        m = self._map()
        assert m.has("auth-svc") is True

    def test_has_returns_false_for_unknown(self):
        m = self._map()
        assert m.has("unknown-svc") is False

    def test_get_raises_keyerror_for_unknown(self):
        m = self._map()
        with pytest.raises(KeyError, match="unknown-svc"):
            m.get("unknown-svc")

    def test_error_message_is_descriptive(self):
        m = InMemoryServiceRepoMap()
        with pytest.raises(KeyError, match="ServiceRepoMap"):
            m.get("my-service")

    def test_register_overwrites_existing(self):
        m = self._map()
        m.register("payment-api", RepoEntry(repo_url="https://github.com/org/payment-v2", language="go"))
        assert m.get("payment-api").language == "go"

    def test_len_reflects_registrations(self):
        m = self._map()
        assert len(m) == 2
        m.register("new-svc", RepoEntry(repo_url="https://example.com/r", language="python"))
        assert len(m) == 3

    def test_initialise_with_dict(self):
        entries = {
            "svc-a": RepoEntry(repo_url="https://example.com/a", language="java"),
        }
        m = InMemoryServiceRepoMap(entries=entries)
        assert m.has("svc-a")
        assert not m.has("svc-b")
