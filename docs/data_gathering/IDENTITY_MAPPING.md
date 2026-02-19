# Identity Mapping (Service ↔ Deploy ↔ Commit)

This project succeeds or fails on identity mapping. The goal is to reliably map:

- a **logical service** (what SREs talk about)
- to its **deploy events** (what changed, when)
- and (best-effort) to the **code revision** (commit/PR)

## 1) Canonical service identity

### Required stable key

Define `service_key` as:

`<cluster_id>/<namespace>/<service_name>`

Where `service_name` is derived from (in priority order):
1) `app.kubernetes.io/name`
2) `app`
3) Deployment name

Record the full label set as metadata, but never depend on it for identity.

## 2) DeploymentEvent normalization

A `DeploymentEvent` should minimally include:
- `service_key`
- `started_at` (rollout start time)
- `finished_at` (optional)
- `image_ref` (resolved image reference)
- `deploy_type` (helm|k8s|argo|flux|other)
- `revision` (best-effort commit SHA or build ID — the **current** tip after this deploy)
- `previous_revision` (the SHA that was running before this deploy — required to compute the commit range)
- `is_rollback` (bool — true when `revision` is an ancestor of `previous_revision`; flips analysis logic)

### Commit range

The commit range for a deploy is always `previous_revision..revision` (exclusive..inclusive).

This range is the only thing Git_Scout ever needs at incident time — **all analysis of that range is pre-computed at push time** (see Section 7 below). If `previous_revision` is unknown, log a warning and fall back to the last N commits (default: 20).

### Rollback detection

When `is_rollback = true`:
- The "changes" are commits being **removed**, not added.
- The Brain should lead with "this deploy rolled back code to an earlier state" and look for symptoms that correlate with what was removed.
- Do not apply the normal "blame the new commit" logic.

### Manual / out-of-band changes

Not all changes arrive via CI/CD. The K8s collector must treat **any spec mutation** detected via the watch API as a potential cause, regardless of origin.

- A `kubectl edit`, `kubectl set image`, `kubectl scale`, or direct `kubectl apply` produces a `ConfigChangeEvent` (see `DATA_MODELS.md`) with `deploy_type = manual` and `revision = null`.
- The spec diff (old vs new) is stored as structured JSON in `diff_payload` — this is the evidence the Brain will cite.
- Attribution (who ran the command) is only available when K8s audit logging is enabled on the cluster.
- `ConfigChangeEvents` are correlated by timing the same way as `DeploymentEvents`. If one falls inside the anomaly window, it is a first-class hypothesis candidate.
- DB schema changes (manual `ALTER TABLE`, etc.) follow the same pattern with `source = db_schema`.

## 3) Revision mapping strategies (ranked)

### Strategy A (preferred): OCI image labels

Require the CI build to attach revision labels to the image:
- `org.opencontainers.image.revision = <git sha>`
- `org.opencontainers.image.source = <repo url>`

How it’s used
- On deploy, resolve `image_ref` and read image config labels.
- Use `revision` directly as the commit SHA.

Pros
- Most reliable across toolchains.

### Strategy B: K8s annotations

If image labels are not possible, standardize on deployment annotations:
- `rca.dev/repo = <repo url>`
- `rca.dev/revision = <git sha>`
- `rca.dev/build_id = <ci build id>`

### Strategy C: GitOps source-of-truth (Argo/Flux)

If using GitOps, use the GitOps commit as the deploy revision.

### Strategy D: Tag heuristics (last resort)

Heuristics when tags are used:
- If tag matches a SHA pattern (7–40 hex), treat as SHA.
- If tag is semantic version (`v1.2.3`), map to git tag → commit.

If none work
- Set `revision = null` and proceed with infra/dependency hypotheses.

## 4) Monorepo and multi-repo handling

### Monorepo

- Keep `repo` constant, and map commits to services via:
  - path ownership rules (e.g., `services/checkout/**`)
  - CODEOWNERS (optional)

### Multi-repo services

- Allow a service to reference multiple repos via metadata.
- Prefer a “primary repo” for revision mapping.

## 5) Confidence scoring for mappings

Mapping should be scored so the Brain can reason about uncertainty.

- `1.0` image label revision
- `0.9` explicit annotation
- `0.8` GitOps commit
- `0.4` tag heuristic
- `0.0` unknown

The Investigator must not claim “commit X caused incident” unless mapping confidence is above a minimum threshold (recommended: `>= 0.8`) **and** metrics correlation supports it.

## 6) Required developer actions (to make RCA accurate)

To get reliable code attribution in real environments, standardize at least one of:
- OCI image revision labels (best)
- deployment annotations
- GitOps-based deploys

---

## 7) Commit pre-computation (shift cost to push time, not incident time)

Do not analyze commits at incident time. That is slow, expensive, and happens under pressure.

Instead, process every commit as it is pushed (via GitHub webhook or polling fallback) and store the results.

### What to store per commit

- Commit metadata: SHA, repo, author, message, authored_at
- A **plain-language summary** of the commit (generated by a local/cheap LLM at push time)
- Per changed file:
  - `file_path`
  - `change_type` (see taxonomy below)
  - `diff_text` (raw diff hunk, stored as text for later retrieval if needed)
  - `lines_added`, `lines_removed`

### Change type taxonomy

Classify every changed file into exactly one of:

| change_type | Examples |
|---|---|
| `db_migration` | `*.sql`, `migrations/**`, Alembic/Flyway files |
| `dependency` | `go.mod`, `requirements.txt`, `package.json`, `*.csproj` |
| `config` | `*.yaml`, `*.env`, `*.toml`, `*.ini`, `*config*` |
| `timeout_retry` | Files whose diff includes timeout/retry/circuit-breaker keywords |
| `http_client` | HTTP client setup, gRPC stubs, API client wrappers |
| `shared_util` | Core libraries / shared packages used across multiple services |
| `auth` | Auth middleware, token validation, RBAC |
| `test` | `*_test.*`, `tests/**`, `spec/**` |
| `docs` | `*.md`, `docs/**` |
| `other` | Everything else |

Classification is deterministic (path patterns + keyword matching in the diff). No LLM needed.

### At incident time (Git_Scout's job becomes a query)

Git_Scout does **not** fetch or analyze diffs at incident time. It:
1. Looks up the deployment's commit range (`previous_revision..revision`).
2. Queries pre-computed `commit_files` filtered by `change_type` relevant to the anomaly.
3. Ranks the survivors and passes only the **summaries** (not raw diffs) to the Synthesizer.
4. Retrieves raw `diff_text` on demand only if the Synthesizer or Critic specifically requests it.
