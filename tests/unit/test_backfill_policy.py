"""Unit tests for DifferentialIndexerRequest, BackfillPolicy, and IndexingDiagnostic."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rca.indexing.models import BackfillPolicy, DifferentialIndexerRequest, IndexingDiagnostic


class TestDifferentialIndexerRequest:
    def test_valid_minimum(self):
        r = DifferentialIndexerRequest(service="payment-api", commit_sha="abc1234")
        assert r.service == "payment-api"
        assert r.commit_sha == "abc1234"
        assert r.file_paths == []
        assert r.enable_semantic_delta is False

    def test_with_explicit_files(self):
        r = DifferentialIndexerRequest(
            service="auth-svc",
            commit_sha="deadbeef",
            file_paths=["src/Auth.cs", "src/Token.cs"],
        )
        assert len(r.file_paths) == 2

    def test_service_too_short(self):
        with pytest.raises(ValidationError):
            DifferentialIndexerRequest(service="", commit_sha="abc1234")

    def test_commit_sha_too_short(self):
        with pytest.raises(ValidationError):
            DifferentialIndexerRequest(service="svc", commit_sha="abc")

    def test_enable_semantic_delta(self):
        r = DifferentialIndexerRequest(
            service="svc", commit_sha="abc1234", enable_semantic_delta=True
        )
        assert r.enable_semantic_delta is True


class TestBackfillPolicy:
    def test_defaults(self):
        p = BackfillPolicy()
        assert p.max_days == 90
        assert p.batch_size == 20
        assert p.branch == "main"

    def test_custom_window(self):
        p = BackfillPolicy(max_days=30, batch_size=10, branch="develop")
        assert p.max_days == 30
        assert p.batch_size == 10
        assert p.branch == "develop"

    def test_max_days_must_be_positive(self):
        with pytest.raises(ValidationError):
            BackfillPolicy(max_days=0)

    def test_batch_size_must_be_positive(self):
        with pytest.raises(ValidationError):
            BackfillPolicy(batch_size=0)


class TestIndexingDiagnostic:
    def test_error_diagnostic(self):
        d = IndexingDiagnostic(severity="error", stage="parse", message="Parser failed")
        assert d.severity == "error"
        assert d.file_path is None

    def test_warning_with_context(self):
        d = IndexingDiagnostic(
            severity="warning",
            stage="upsert",
            message="Slow upsert",
            file_path="src/Foo.cs",
            commit_sha="abc1234",
        )
        assert d.file_path == "src/Foo.cs"
        assert d.commit_sha == "abc1234"
