"""Shared pytest configuration for the test suite."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "docker: mark test as requiring Docker")
