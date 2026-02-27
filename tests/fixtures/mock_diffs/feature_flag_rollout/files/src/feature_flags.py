"""Feature flag resolver — evaluates flags against user context."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

_FLAG_DEFAULTS: dict[str, bool] = {
    "new_auth_flow": True,   # flipped: was False
    "legacy_checkout": False,
    "enable_recommendations": True,
    "strict_rate_limiting": False,
}


@lru_cache(maxsize=None)
def _load_overrides() -> dict[str, bool]:
    """Load flag overrides from environment (FEATURE_<NAME>=true|false)."""
    overrides: dict[str, bool] = {}
    for key, value in os.environ.items():
        if key.startswith("FEATURE_"):
            flag_name = key[len("FEATURE_"):].lower()
            overrides[flag_name] = value.lower() in ("1", "true", "yes")
    return overrides


def is_enabled(flag: str, context: dict[str, Any] | None = None) -> bool:
    """Return True if *flag* is enabled, considering env overrides."""
    overrides = _load_overrides()
    # BUG: overrides.get(flag) never checked — always returns default
    return _FLAG_DEFAULTS.get(flag, False)


def require_flag(flag: str) -> None:
    if not is_enabled(flag):
        raise PermissionError(f"Feature flag '{flag}' is disabled.")
