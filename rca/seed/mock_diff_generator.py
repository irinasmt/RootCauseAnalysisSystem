"""Mock diff generator — realistic multi-language commit bundles for indexer smoke testing.

Produces ``MockDiffBundle`` objects containing current file content + a unified diff
across a mix of file types: Python, C#, YAML, JSON, .env, TOML, and INI.

Each bundle maps directly onto the ``RepositoryAdapter`` contract so it can be
injected directly into ``DifferentialIndexer`` without a real git repo.

Usage::

    from rca.seed.mock_diff_generator import ALL_SCENARIOS, get_scenario

    bundle = get_scenario("timeout_cascade")
    print(bundle.description)
    for path, entry in bundle.files.items():
        print(path, "→", entry.language)

Dump to disk (writes tests/fixtures/mock_diffs/<scenario_id>/)::

    python -m rca.seed.mock_diff_generator
    python -m rca.seed.mock_diff_generator timeout_cascade      # single scenario
    python -m rca.seed.mock_diff_generator --out tests/fixtures/mock_diffs
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

Language = Literal["python", "csharp", "yaml", "json", "env", "toml", "ini", "text"]


@dataclass
class FileEntry:
    """Current (post-commit) content plus the unified diff that produced it."""
    content: str       # full file content at HEAD of this commit
    diff: str          # unified diff (--- a/  +++ b/ format)
    language: Language


@dataclass
class MockDiffBundle:
    """A single commit worth of changes across multiple files and languages."""
    scenario_id: str
    description: str
    service: str
    commit_sha: str
    files: dict[str, FileEntry]   # path → FileEntry

    def changed_files(self) -> list[str]:
        return list(self.files.keys())

    def get_file(self, path: str, _commit_sha: str) -> str:
        return self.files[path].content

    def get_diff(self, path: str, _commit_sha: str) -> str:
        return self.files[path].diff

    def list_changed_files(self, _commit_sha: str) -> list[str]:
        return self.changed_files()


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Scenario 1 — timeout_cascade
# A downstream HTTP timeout was halved by a config PR that touched a Python
# client, a YAML k8s ConfigMap, and a .env defaults file.
# ---------------------------------------------------------------------------

_TIMEOUT_PY_AFTER = '''\
"""HTTP client for the payment gateway — configurable timeout + retry."""
from __future__ import annotations

import os
import httpx

GATEWAY_URL = os.getenv("GATEWAY_URL", "https://payments.internal")
TIMEOUT_SECONDS = float(os.getenv("GATEWAY_TIMEOUT", "15"))  # was 30
MAX_RETRIES = int(os.getenv("GATEWAY_MAX_RETRIES", "3"))


class PaymentGatewayClient:
    def __init__(self, timeout: float = TIMEOUT_SECONDS) -> None:
        self._timeout = timeout
        self._client = httpx.Client(timeout=self._timeout)

    def charge(self, amount: float, token: str) -> dict:
        response = self._client.post(
            f"{GATEWAY_URL}/charge",
            json={"amount": amount, "token": token},
        )
        response.raise_for_status()
        return response.json()

    def refund(self, charge_id: str) -> dict:
        response = self._client.post(
            f"{GATEWAY_URL}/refund",
            json={"charge_id": charge_id},
        )
        response.raise_for_status()
        return response.json()
'''

_TIMEOUT_PY_DIFF = '''\
--- a/src/payment_gateway_client.py
+++ b/src/payment_gateway_client.py
@@ -4,6 +4,6 @@
 import os
 import httpx
 
 GATEWAY_URL = os.getenv("GATEWAY_URL", "https://payments.internal")
-TIMEOUT_SECONDS = float(os.getenv("GATEWAY_TIMEOUT", "30"))
+TIMEOUT_SECONDS = float(os.getenv("GATEWAY_TIMEOUT", "15"))  # was 30
 MAX_RETRIES = int(os.getenv("GATEWAY_MAX_RETRIES", "3"))
'''

_TIMEOUT_YAML_AFTER = '''\
apiVersion: v1
kind: ConfigMap
metadata:
  name: payment-service-config
  namespace: production
data:
  GATEWAY_URL: "https://payments.internal"
  GATEWAY_TIMEOUT: "15"
  GATEWAY_MAX_RETRIES: "3"
  LOG_LEVEL: "info"
  ENABLE_CIRCUIT_BREAKER: "true"
'''

_TIMEOUT_YAML_DIFF = '''\
--- a/k8s/payment-service-configmap.yaml
+++ b/k8s/payment-service-configmap.yaml
@@ -6,6 +6,6 @@
 data:
   GATEWAY_URL: "https://payments.internal"
-  GATEWAY_TIMEOUT: "30"
+  GATEWAY_TIMEOUT: "15"
   GATEWAY_MAX_RETRIES: "3"
   LOG_LEVEL: "info"
   ENABLE_CIRCUIT_BREAKER: "true"
'''

_TIMEOUT_ENV_AFTER = '''\
# Payment service defaults — overridden by k8s ConfigMap in production
GATEWAY_URL=https://payments.internal
GATEWAY_TIMEOUT=15
GATEWAY_MAX_RETRIES=3
LOG_LEVEL=debug
ENABLE_CIRCUIT_BREAKER=false
'''

_TIMEOUT_ENV_DIFF = '''\
--- a/.env.defaults
+++ b/.env.defaults
@@ -2,6 +2,6 @@
 # Payment service defaults — overridden by k8s ConfigMap in production
 GATEWAY_URL=https://payments.internal
-GATEWAY_TIMEOUT=30
+GATEWAY_TIMEOUT=15
 GATEWAY_MAX_RETRIES=3
 LOG_LEVEL=debug
 ENABLE_CIRCUIT_BREAKER=false
'''

TIMEOUT_CASCADE = MockDiffBundle(
    scenario_id="timeout_cascade",
    description=(
        "HTTP timeout halved from 30 → 15 s across a Python client, "
        "a Kubernetes ConfigMap YAML, and the .env defaults file. "
        "Root cause: downstream payment gateway started responding in 20 s "
        "during peak load, causing cascading 504s after the deploy."
    ),
    service="payment-service",
    commit_sha=_sha("timeout_cascade"),
    files={
        "src/payment_gateway_client.py": FileEntry(
            content=_TIMEOUT_PY_AFTER,
            diff=_TIMEOUT_PY_DIFF,
            language="python",
        ),
        "k8s/payment-service-configmap.yaml": FileEntry(
            content=_TIMEOUT_YAML_AFTER,
            diff=_TIMEOUT_YAML_DIFF,
            language="yaml",
        ),
        ".env.defaults": FileEntry(
            content=_TIMEOUT_ENV_AFTER,
            diff=_TIMEOUT_ENV_DIFF,
            language="env",
        ),
    },
)


# ---------------------------------------------------------------------------
# Scenario 2 — db_pool_exhaustion
# Connection pool max_size reduced in a C# DbContext, reflected in both
# appsettings.json and the TOML service config.
# ---------------------------------------------------------------------------

_POOL_CS_AFTER = '''\
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;

namespace OrderService.Data
{
    public class OrderDbContext : DbContext
    {
        private readonly IConfiguration _config;

        public OrderDbContext(DbContextOptions<OrderDbContext> options,
                              IConfiguration config) : base(options)
        {
            _config = config;
        }

        protected override void OnConfiguring(DbContextOptionsBuilder optionsBuilder)
        {
            var connStr = _config.GetConnectionString("OrdersDb");
            optionsBuilder.UseNpgsql(connStr, npgsql =>
            {
                npgsql.MaxPoolSize(5);   // reduced from 20 — cost optimisation
                npgsql.MinPoolSize(1);
                npgsql.ConnectionIdleLifetime(TimeSpan.FromMinutes(2));
            });
        }

        public DbSet<Order> Orders => Set<Order>();
        public DbSet<OrderLine> OrderLines => Set<OrderLine>();
    }
}
'''

_POOL_CS_DIFF = '''\
--- a/src/OrderService/Data/OrderDbContext.cs
+++ b/src/OrderService/Data/OrderDbContext.cs
@@ -17,7 +17,7 @@
             var connStr = _config.GetConnectionString("OrdersDb");
             optionsBuilder.UseNpgsql(connStr, npgsql =>
             {
-                npgsql.MaxPoolSize(20);
+                npgsql.MaxPoolSize(5);   // reduced from 20 — cost optimisation
                 npgsql.MinPoolSize(1);
                 npgsql.ConnectionIdleLifetime(TimeSpan.FromMinutes(2));
             });
'''

_POOL_JSON_AFTER = '''\
{
  "ConnectionStrings": {
    "OrdersDb": "Host=orders-db;Database=orders;Username=app;Password=${DB_PASSWORD}"
  },
  "Database": {
    "MaxPoolSize": 5,
    "MinPoolSize": 1,
    "CommandTimeoutSeconds": 30,
    "EnableSensitiveDataLogging": false
  },
  "Logging": {
    "LogLevel": {
      "Default": "Warning",
      "Microsoft": "Warning"
    }
  }
}
'''

_POOL_JSON_DIFF = '''\
--- a/src/OrderService/appsettings.json
+++ b/src/OrderService/appsettings.json
@@ -4,7 +4,7 @@
   "Database": {
-    "MaxPoolSize": 20,
+    "MaxPoolSize": 5,
     "MinPoolSize": 1,
     "CommandTimeoutSeconds": 30,
     "EnableSensitiveDataLogging": false
   },
'''

_POOL_TOML_AFTER = '''\
[service]
name = "order-service"
version = "2.4.1"
environment = "production"

[database]
max_pool_size = 5
min_pool_size = 1
command_timeout_seconds = 30
retry_on_failure = true
max_retries = 3

[observability]
metrics_port = 9090
tracing_enabled = true
log_level = "warning"
'''

_POOL_TOML_DIFF = '''\
--- a/config/service.toml
+++ b/config/service.toml
@@ -8,7 +8,7 @@

 [database]
-max_pool_size = 20
+max_pool_size = 5
 min_pool_size = 1
 command_timeout_seconds = 30
 retry_on_failure = true
'''

DB_POOL_EXHAUSTION = MockDiffBundle(
    scenario_id="db_pool_exhaustion",
    description=(
        "DB connection pool max_size reduced from 20 → 5 in a C# DbContext, "
        "appsettings.json, and TOML service config. "
        "Root cause: connection exhaustion under load after the pool was "
        "shrunk during a cost-cutting sprint."
    ),
    service="order-service",
    commit_sha=_sha("db_pool_exhaustion"),
    files={
        "src/OrderService/Data/OrderDbContext.cs": FileEntry(
            content=_POOL_CS_AFTER,
            diff=_POOL_CS_DIFF,
            language="csharp",
        ),
        "src/OrderService/appsettings.json": FileEntry(
            content=_POOL_JSON_AFTER,
            diff=_POOL_JSON_DIFF,
            language="json",
        ),
        "config/service.toml": FileEntry(
            content=_POOL_TOML_AFTER,
            diff=_POOL_TOML_DIFF,
            language="toml",
        ),
    },
)


# ---------------------------------------------------------------------------
# Scenario 3 — feature_flag_rollout
# A Python feature-flag resolver started gating a new auth flow. The flag was
# flipped in a JSON feature config and .env, but the Python resolver has a bug
# where the new code path is always taken regardless of the flag value.
# ---------------------------------------------------------------------------

_FLAG_PY_AFTER = '''\
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
'''

_FLAG_PY_DIFF = '''\
--- a/src/feature_flags.py
+++ b/src/feature_flags.py
@@ -8,7 +8,7 @@
 _FLAG_DEFAULTS: dict[str, bool] = {
-    "new_auth_flow": False,
+    "new_auth_flow": True,   # flipped: was False
     "legacy_checkout": False,
     "enable_recommendations": True,
     "strict_rate_limiting": False,
 }
'''

_FLAG_JSON_AFTER = '''\
{
  "flags": {
    "new_auth_flow": true,
    "legacy_checkout": false,
    "enable_recommendations": true,
    "strict_rate_limiting": false
  },
  "overrides": {},
  "schema_version": "1.2"
}
'''

_FLAG_JSON_DIFF = '''\
--- a/config/feature_flags.json
+++ b/config/feature_flags.json
@@ -2,7 +2,7 @@
   "flags": {
-    "new_auth_flow": false,
+    "new_auth_flow": true,
     "legacy_checkout": false,
     "enable_recommendations": true,
     "strict_rate_limiting": false
'''

_FLAG_ENV_AFTER = '''\
# Feature flag environment overrides — take precedence over JSON config
FEATURE_NEW_AUTH_FLOW=true
FEATURE_LEGACY_CHECKOUT=false
FEATURE_ENABLE_RECOMMENDATIONS=true
FEATURE_STRICT_RATE_LIMITING=false
'''

_FLAG_ENV_DIFF = '''\
--- a/.env.features
+++ b/.env.features
@@ -1,5 +1,5 @@
 # Feature flag environment overrides — take precedence over JSON config
-FEATURE_NEW_AUTH_FLOW=false
+FEATURE_NEW_AUTH_FLOW=true
 FEATURE_LEGACY_CHECKOUT=false
 FEATURE_ENABLE_RECOMMENDATIONS=true
 FEATURE_STRICT_RATE_LIMITING=false
'''

_FLAG_INI_AFTER = '''\
[auth]
provider = oauth2
new_flow_enabled = true
session_timeout_minutes = 60
max_sessions_per_user = 5

[rate_limiting]
enabled = false
requests_per_minute = 100
burst_multiplier = 2.0

[cache]
backend = redis
ttl_seconds = 300
'''

_FLAG_INI_DIFF = '''\
--- a/config/auth.ini
+++ b/config/auth.ini
@@ -2,7 +2,7 @@
 [auth]
 provider = oauth2
-new_flow_enabled = false
+new_flow_enabled = true
 session_timeout_minutes = 60
 max_sessions_per_user = 5
'''

FEATURE_FLAG_ROLLOUT = MockDiffBundle(
    scenario_id="feature_flag_rollout",
    description=(
        "new_auth_flow flag flipped to True in a Python resolver, "
        "feature_flags.json, .env.features, and auth.ini simultaneously. "
        "Root cause: the Python resolver has a bug — env overrides are loaded "
        "but never consulted, so the new (broken) auth flow activates for all "
        "users regardless of partial rollout intent."
    ),
    service="auth-service",
    commit_sha=_sha("feature_flag_rollout"),
    files={
        "src/feature_flags.py": FileEntry(
            content=_FLAG_PY_AFTER,
            diff=_FLAG_PY_DIFF,
            language="python",
        ),
        "config/feature_flags.json": FileEntry(
            content=_FLAG_JSON_AFTER,
            diff=_FLAG_JSON_DIFF,
            language="json",
        ),
        ".env.features": FileEntry(
            content=_FLAG_ENV_AFTER,
            diff=_FLAG_ENV_DIFF,
            language="env",
        ),
        "config/auth.ini": FileEntry(
            content=_FLAG_INI_AFTER,
            diff=_FLAG_INI_DIFF,
            language="ini",
        ),
    },
)


# ---------------------------------------------------------------------------
# Scenario 4 — rate_limit_misconfiguration
# New Python rate-limiter middleware added; corresponding YAML Helm values and
# a TOML service manifest updated — but the middleware was wired before auth,
# causing unauthenticated requests to consume the per-user quota.
# ---------------------------------------------------------------------------

_RATE_PY_AFTER = '''\
"""Rate limiting middleware — per-user request throttling."""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable

import httpx

MAX_REQUESTS_PER_MINUTE: int = 60
WINDOW_SECONDS: int = 60

_buckets: dict[str, list[float]] = defaultdict(list)


def rate_limit_middleware(request: httpx.Request, call_next: Callable) -> httpx.Response:
    """Sliding-window rate limiter keyed on X-User-Id header.

    NOTE: middleware is registered before auth — X-User-Id may be absent or
    spoofed at this point in the pipeline.
    """
    user_id = request.headers.get("X-User-Id", "anonymous")
    now = time.monotonic()
    window = _buckets[user_id]

    # Evict timestamps outside the window
    _buckets[user_id] = [t for t in window if now - t < WINDOW_SECONDS]

    if len(_buckets[user_id]) >= MAX_REQUESTS_PER_MINUTE:
        return httpx.Response(429, text="Rate limit exceeded")

    _buckets[user_id].append(now)
    return call_next(request)
'''

_RATE_PY_DIFF = '''\
--- /dev/null
+++ b/src/middleware/rate_limiter.py
@@ -0,0 +1,33 @@
+"""Rate limiting middleware — per-user request throttling."""
+from __future__ import annotations
+
+import time
+from collections import defaultdict
+from typing import Callable
+
+import httpx
+
+MAX_REQUESTS_PER_MINUTE: int = 60
+WINDOW_SECONDS: int = 60
+
+_buckets: dict[str, list[float]] = defaultdict(list)
+
+
+def rate_limit_middleware(request: httpx.Request, call_next: Callable) -> httpx.Response:
+    """Sliding-window rate limiter keyed on X-User-Id header.
+
+    NOTE: middleware is registered before auth — X-User-Id may be absent or
+    spoofed at this point in the pipeline.
+    """
+    user_id = request.headers.get("X-User-Id", "anonymous")
+    now = time.monotonic()
+    window = _buckets[user_id]
+
+    # Evict timestamps outside the window
+    _buckets[user_id] = [t for t in window if now - t < WINDOW_SECONDS]
+
+    if len(_buckets[user_id]) >= MAX_REQUESTS_PER_MINUTE:
+        return httpx.Response(429, text="Rate limit exceeded")
+
+    _buckets[user_id].append(now)
+    return call_next(request)
'''

_RATE_YAML_AFTER = '''\
# Helm values for api-gateway
replicaCount: 3

image:
  repository: myregistry/api-gateway
  tag: "2.1.0"
  pullPolicy: IfNotPresent

rateLimiting:
  enabled: true
  maxRequestsPerMinute: 60
  windowSeconds: 60
  keyHeader: "X-User-Id"

middleware:
  order:
    - rate_limiter     # WRONG: should be after auth
    - auth
    - logging
    - cors

resources:
  requests:
    cpu: 250m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 512Mi
'''

_RATE_YAML_DIFF = '''\
--- a/helm/api-gateway/values.yaml
+++ b/helm/api-gateway/values.yaml
@@ -8,6 +8,14 @@
+rateLimiting:
+  enabled: true
+  maxRequestsPerMinute: 60
+  windowSeconds: 60
+  keyHeader: "X-User-Id"
+
+middleware:
+  order:
+    - rate_limiter     # WRONG: should be after auth
+    - auth
+    - logging
+    - cors
+
 resources:
'''

_RATE_TOML_AFTER = '''\
[service]
name = "api-gateway"
version = "2.1.0"

[middleware]
rate_limiting_enabled = true
rate_limiting_position = "pre_auth"   # should be post_auth
max_requests_per_minute = 60
window_seconds = 60

[auth]
provider = "jwt"
jwks_url = "https://auth.internal/.well-known/jwks.json"
audience = "api.internal"
'''

_RATE_TOML_DIFF = '''\
--- a/config/gateway.toml
+++ b/config/gateway.toml
@@ -4,6 +4,11 @@

+[middleware]
+rate_limiting_enabled = true
+rate_limiting_position = "pre_auth"   # should be post_auth
+max_requests_per_minute = 60
+window_seconds = 60
+
 [auth]
 provider = "jwt"
'''

RATE_LIMIT_MISCONFIGURATION = MockDiffBundle(
    scenario_id="rate_limit_misconfiguration",
    description=(
        "New rate-limiter middleware added in Python, Helm values YAML, and "
        "TOML gateway config. Root cause: middleware registered before auth "
        "in all three places — unauthenticated requests consume the per-user "
        "quota keyed on X-User-Id which is absent pre-auth, causing all "
        "anonymous traffic to share one bucket and trigger 429s."
    ),
    service="api-gateway",
    commit_sha=_sha("rate_limit_misconfiguration"),
    files={
        "src/middleware/rate_limiter.py": FileEntry(
            content=_RATE_PY_AFTER,
            diff=_RATE_PY_DIFF,
            language="python",
        ),
        "helm/api-gateway/values.yaml": FileEntry(
            content=_RATE_YAML_AFTER,
            diff=_RATE_YAML_DIFF,
            language="yaml",
        ),
        "config/gateway.toml": FileEntry(
            content=_RATE_TOML_AFTER,
            diff=_RATE_TOML_DIFF,
            language="toml",
        ),
    },
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_SCENARIOS: dict[str, MockDiffBundle] = {
    "timeout_cascade": TIMEOUT_CASCADE,
    "db_pool_exhaustion": DB_POOL_EXHAUSTION,
    "feature_flag_rollout": FEATURE_FLAG_ROLLOUT,
    "rate_limit_misconfiguration": RATE_LIMIT_MISCONFIGURATION,
}


def get_scenario(scenario_id: str) -> MockDiffBundle:
    """Return a ``MockDiffBundle`` by scenario ID.

    Raises ``KeyError`` with a helpful message if the ID is not found.
    """
    if scenario_id not in ALL_SCENARIOS:
        available = ", ".join(ALL_SCENARIOS)
        raise KeyError(
            f"Unknown scenario '{scenario_id}'. Available: {available}"
        )
    return ALL_SCENARIOS[scenario_id]


def load_from_dir(fixture_dir: str | Path) -> MockDiffBundle:
    """Load a ``MockDiffBundle`` from an on-disk fixture directory.

    Expects the layout written by ``dump_to_fixtures()``::

        <fixture_dir>/
          manifest.json
          files/<rel_path>         ← full file content
          diffs/<rel_path>.diff    ← unified diff

    Parameters
    ----------
    fixture_dir:
        Path to a single scenario directory (e.g.
        ``tests/fixtures/mock_diffs/timeout_cascade``).
    """
    base = Path(fixture_dir)
    manifest_path = base / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No manifest.json found in {base.resolve()}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    files: dict[str, FileEntry] = {}
    for entry in manifest["files"]:
        rel_path = entry["path"]
        content = (base / entry["content_file"]).read_text(encoding="utf-8")
        diff    = (base / entry["diff_file"]).read_text(encoding="utf-8")
        files[rel_path] = FileEntry(
            content=content,
            diff=diff,
            language=entry["language"],
        )

    return MockDiffBundle(
        scenario_id=manifest["scenario_id"],
        description=manifest["description"],
        service=manifest["service"],
        commit_sha=manifest["commit_sha"],
        files=files,
    )


# ---------------------------------------------------------------------------
# Fixture writer
# ---------------------------------------------------------------------------

def dump_to_fixtures(
    out_dir: str | Path = "tests/fixtures/mock_diffs",
    scenarios: list[str] | None = None,
) -> None:
    """Write mock diff bundles to *out_dir* so they can be inspected on disk.

    Layout::

        tests/fixtures/mock_diffs/
          timeout_cascade/
            manifest.json          # scenario metadata + file list
            files/
              src/payment_gateway_client.py
              k8s/payment-service-configmap.yaml
              .env.defaults
            diffs/
              src/payment_gateway_client.py.diff
              k8s/payment-service-configmap.yaml.diff
              .env.defaults.diff

    Parameters
    ----------
    out_dir:
        Root output directory (created if absent).
    scenarios:
        Subset of scenario IDs to write.  Defaults to all.
    """
    root = Path(out_dir)
    ids = scenarios or list(ALL_SCENARIOS)

    for sid in ids:
        bundle = ALL_SCENARIOS[sid]
        base = root / sid
        files_dir = base / "files"
        diffs_dir = base / "diffs"
        files_dir.mkdir(parents=True, exist_ok=True)
        diffs_dir.mkdir(parents=True, exist_ok=True)

        file_entries = []
        for rel_path, entry in bundle.files.items():
            # Write file content
            dest = files_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(entry.content, encoding="utf-8")

            # Write unified diff
            diff_dest = diffs_dir / (rel_path + ".diff")
            diff_dest.parent.mkdir(parents=True, exist_ok=True)
            diff_dest.write_text(entry.diff, encoding="utf-8")

            file_entries.append({
                "path": rel_path,
                "language": entry.language,
                "content_file": f"files/{rel_path}",
                "diff_file": f"diffs/{rel_path}.diff",
            })

        manifest = {
            "scenario_id": bundle.scenario_id,
            "service": bundle.service,
            "commit_sha": bundle.commit_sha,
            "description": bundle.description,
            "files": file_entries,
        }
        (base / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        print(f"  wrote {sid}/  ({len(bundle.files)} files)")

    print(f"\nDone → {root.resolve()}")


# ---------------------------------------------------------------------------
# CLI  (python -m rca.seed.mock_diff_generator)
# ---------------------------------------------------------------------------

def _main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Write mock diff bundles to tests/fixtures/mock_diffs/",
    )
    parser.add_argument(
        "scenarios",
        nargs="*",
        help="Scenario IDs to dump (default: all)",
    )
    parser.add_argument(
        "--out",
        default="tests/fixtures/mock_diffs",
        metavar="DIR",
        help="Output root directory (default: tests/fixtures/mock_diffs)",
    )
    args = parser.parse_args()

    ids = args.scenarios or None
    if ids:
        unknown = [s for s in ids if s not in ALL_SCENARIOS]
        if unknown:
            print(f"Unknown scenario(s): {', '.join(unknown)}")
            print(f"Available: {', '.join(ALL_SCENARIOS)}")
            sys.exit(1)

    print(f"Writing to {args.out}/")
    dump_to_fixtures(out_dir=args.out, scenarios=ids)


if __name__ == "__main__":
    _main()

