# Feature Specification: Connectors (K8s + GitHub + DB) Plug-and-Play

**Feature Branch**: `003-connectors`
**Created**: 2026-02-24
**Status**: Draft
**Input**: User description: "Add plug-and-play connectors for Kubernetes, GitHub, and databases with low exposure."

## Problem Statement

The Brain needs production evidence (deploys, changes, runtime signals) from multiple external systems. Hard-coding integrations makes the system brittle, hard to deploy, and risky (especially for database access).

We need a connector system that:
- is **plug-and-play** (turn connectors on/off via config)
- is **safe-by-default** (data minimization; least-privilege)
- is **deterministic and auditable** (what was collected and why)
- normalizes evidence into the existing RCA data model.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Enable/Disable Connectors via Config (Priority: P1)

As an operator, I can enable a subset of connectors (K8s/GitHub/DB) via a configuration file, and the system runs without code changes.

**Independent Test**: Provide a config enabling only one connector; verify evidence collection runs and produces normalized evidence without importing or requiring the other connector dependencies.

**Acceptance Scenarios**:
1. **Given** config enables `kubernetes` only, **When** the collector runs, **Then** only K8s evidence is fetched and normalized.
2. **Given** config enables `github` only, **When** the collector runs, **Then** only GitHub evidence is fetched and normalized.
3. **Given** config enables `postgres` only, **When** the collector runs, **Then** only DB evidence is fetched and normalized.

---

### User Story 2 - Safe-by-Default Database Evidence (Priority: P1)

As a security-minded operator, I can connect to a database without exposing application row data by default.

**Independent Test**: Run the DB connector with default config; verify it only reads metadata/aggregates from allowed system sources and never executes arbitrary SQL.

**Acceptance Scenarios**:
1. **Given** DB connector runs in default mode, **When** it collects evidence, **Then** it collects only metadata/aggregates and no user table rows.
2. **Given** an operator attempts to configure a free-form query, **When** config is validated, **Then** validation fails with a clear error.
3. **Given** DB connector runs, **When** evidence is persisted, **Then** it is redacted according to policy before storage.

---

### User Story 3 - K8s + GitHub Correlation for Identity Mapping (Priority: P2)

As an RCA engineer, I can correlate Kubernetes deploys to Git commits so the Brain can reason about what changed.

**Independent Test**: Provide a fixture with a deploy referencing an image with OCI revision labels; verify a `DeploymentEvent` includes `revision` and mapping confidence.

**Acceptance Scenarios**:
1. **Given** a workload image contains `org.opencontainers.image.revision`, **When** a deploy is detected, **Then** `revision` is set with high confidence.
2. **Given** revision is unknown, **When** a deploy is detected, **Then** mapping confidence is low and the Brain avoids strong attribution.

---

### Edge Cases

- K8s audit logging disabled (no actor attribution).
- GitHub rate limits or transient API errors.
- DB user lacks required permissions (collector degrades gracefully).
- Clock skew across sources.

## Non-goals (this feature iteration)

- Building a UI for connector configuration.
- Writing data back to external systems (connectors are read-only by default).
- Supporting every DB engine initially (start with PostgreSQL).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a connector registry so connectors can be enabled/disabled via config.
- **FR-002**: System MUST define a stable connector interface: `health_check`, `capabilities`, and `collect(window, scope)`.
- **FR-003**: System MUST normalize collected data into the project’s evidence/event models (see `docs/data_structure/DATA_MODELS.md`).
- **FR-004**: System MUST support incremental collection (cursor/"since" per connector) for a long-running service.
- **FR-005**: System MUST persist an evidence manifest describing what was collected (source, window, counts, redaction applied).
- **FR-006**: System MUST isolate optional dependencies per connector (install-time extras).

### Security & Privacy Requirements

- **SR-001 (Data Minimization)**: Connectors MUST collect the minimum evidence needed for RCA. Default settings MUST avoid row-level payloads.
- **SR-002 (Least Privilege)**: Connector credentials MUST be scoped read-only with minimal permissions.
- **SR-003 (No Arbitrary DB SQL)**: The DB connector MUST NOT execute free-form SQL. Only allowlisted sources (system views / allowlisted views / fixed templates) are permitted.
- **SR-004 (Redaction First)**: Evidence MUST be redacted/hashed before persistence according to a configurable policy.
- **SR-005 (Auditability)**: The system MUST log connector actions at a high level (what was queried, not secrets) and produce a manifest suitable for audit.
- **SR-006 (Secrets Handling)**: Secrets MUST be provided via env vars or mounted files; never stored in repo or logs.
- **SR-007 (No Sensitive Text by Default)**: Connectors MUST NOT persist sensitive free-form text by default (examples: SQL query text, HTTP headers, request bodies). Such collection must be explicit opt-in with additional redaction.

### Connector-Specific Requirements

#### Kubernetes Connector
- **K8S-001**: MUST support in-cluster auth via ServiceAccount.
- **K8S-002**: MUST collect deploy/config change evidence and normalize into `DeploymentEvent` and `ConfigChangeEvent`.
- **K8S-003**: MUST never persist Secret values (only key names / hashes if needed).

#### GitHub Connector
- **GH-001**: MUST support GitHub App auth (preferred) and PAT fallback.
- **GH-002**: MUST support incremental sync for commits/PRs and store pre-computed commit summaries (see `docs/data_gathering/IDENTITY_MAPPING.md`, Section 7).

#### PostgreSQL Connector (Safe-by-Default)

The PostgreSQL connector MUST support explicit access levels:

- **Level 0: `metadata` (default)**
  - Read-only access to system/metrics sources only (examples: `pg_stat_database`, `pg_stat_activity`, `pg_locks`, `pg_stat_bgwriter`).
  - Optional integration with `pg_stat_statements` if enabled.
  - Output is aggregates and normalized events (e.g., "connection saturation", "lock contention", "migration applied").

- **Level 1: `views` (recommended for orgs)**
  - Connector may `SELECT` only from an operator-provided allowlist of views in a dedicated schema (e.g., `rca_evidence.*`).
  - No access to base tables.
  - Views are designed to exclude/obfuscate PII at the source.

- **Level 2: `templates` (opt-in)**
  - Connector may execute a fixed set of parameterized templates shipped with the tool.
  - Templates MUST be reviewed, documented, and versioned.

Constraints:
- **PG-001**: Default configuration MUST be Level 0 (`metadata`).
- **PG-002**: Connector MUST refuse to run if configured for Level 1/2 without explicit allowlists.
- **PG-003**: Connector MUST enforce statement timeouts and row limits (defense-in-depth).

### PostgreSQL Data Minimization Contract

**What the connector MAY collect by default (Level 0)**
- Aggregate counters and timings (connections, waits, locks) suitable for diagnosing: connection exhaustion, lock contention, slowdowns.
- Identifiers that are infrastructure-scoped (database name, role name) where necessary for correlation.
- Query fingerprints/IDs (e.g., `queryid`) and aggregate stats **without query text**.

**What the connector MUST NOT collect by default**
- Any row-level application data from user tables.
- SQL query text (unless explicitly enabled and redacted).
- Values that are likely secrets (passwords, tokens) or direct PII (emails, names).

**How to get richer DB evidence safely (operator-controlled)**
- Prefer Level 1 (`views`) with a dedicated schema such as `rca_evidence.*`.
- Views must be designed to be RCA-safe (aggregated, pre-redacted, column-allowlisted).
- Connector configuration lists allowed view names explicitly; any non-allowlisted view read fails closed.

## Design Notes

### Normalization and Identity Mapping

Connectors produce raw records, then a normalizer converts them into:
- `DeploymentEvent`, `ConfigChangeEvent`
- Git commit metadata and pre-computed summaries
- DB evidence events (connection pool saturation, lock contention, schema change indicators)

Service identity follows `docs/data_gathering/IDENTITY_MAPPING.md`:
- `service_key = <cluster_id>/<namespace>/<service_name>`

### Evidence Redaction Policy (high level)

Redaction policy is configured centrally and applied before persistence:
- allowlist of fields allowed to persist
- hashing of identifiers (user_id, email, IP) when needed for correlation
- truncation or omission for long text fields

### Deployment Model

Target deployment is a long-running service:
- in-cluster K8s access via ServiceAccount
- GitHub App private key in Kubernetes Secret
- DB credentials in Secret, read-only role, network-restricted

## Success Criteria *(mandatory)*

- **SC-001**: A minimal deployment can enable only K8s connector and produce normalized deployment/config evidence.
- **SC-002**: DB connector default mode produces only metadata/aggregate evidence and persists a manifest showing redaction.
- **SC-003**: Enabling/disabling connectors requires only config changes.
- **SC-004**: Connector failures degrade gracefully and do not crash the worker; manifest records partial collection.
