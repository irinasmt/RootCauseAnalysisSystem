---
applyTo: "**/README.md, **/docs/**/*.md, **/specs/**/*.md"
---

# Documentation Guidelines — RootCauseAnalysisSystem

## Required Sections (README.md and module docs)

Every `README.md` and top-level documentation file must contain these sections in order:

1. **Purpose** — one paragraph explaining what this module/component does and why it exists.
2. **Architecture** — how it fits into the broader system (reference other modules by path).
3. **Environment Variables** — table of all env vars consumed (see format below).
4. **Entry Points / Usage** — how to run it, with copy-pasteable shell commands in code blocks.
5. **Examples** — at least one concrete end-to-end example with expected output.

Optional but encouraged: **Testing**, **Troubleshooting**, **Known Limitations**.

## Environment Variable Tables

Every env var used by the component must appear in a table:

```markdown
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEO4J_URL` | No | `bolt://localhost:7687` | Bolt URL for the Neo4j instance |
| `NEO4J_PASSWORD` | **Yes** | — | Neo4j password; triggers Neo4j mode if set |
| `GEMINI_API_KEY` | **Yes** | — | Google Gemini API key for LLM calls |
```

- Mark required vars with `**Yes**` and use `—` for no default.
- Group vars by system (Neo4j, Gemini, connector-specific, etc.) with a subheading.
- If a var is optional but changes behavior significantly, add a **Behavior** note below the table.

## Shell Commands

Wrap every runnable command in a fenced code block with the shell language:

````markdown
```bash
python run_fixture_pipeline.py tests/fixtures/shoe_store/order_slow_due_to_payment
```
````

- Include the working directory assumption if it's not the repo root.
- For multi-step sequences, number them and show each step separately.
- Always include the `--no-embed` flag in examples where embeddings are optional (they require `GEMINI_API_KEY`).

## Spec / Implementation Alignment

- When a behavior or contract changes, update the corresponding file under `specs/` in the same PR.
- Spec files live at `specs/<NNN>-<feature-slug>/spec.md` — link to them from implementation docs.
- Do not describe behavior that diverges from the spec without explicitly noting the divergence and the reason.

## Cross-references

- Reference other modules using repo-relative paths, not absolute filesystem paths.
- When referencing a Brain node, link to `rca/brain/nodes.py`.
- When referencing a Pydantic model, link to the models file where it's defined.
- Avoid "see above" or "see below" — use section anchor links instead.

## Tone and Style

- Write in **imperative voice** for instructions ("Run X", "Set Y", "Pass Z").
- Keep paragraphs short — three sentences maximum per paragraph.
- Avoid jargon without a one-line definition on first use.
- Do not use passive voice when active voice is available ("The engine processes" not "The incident is processed by the engine").
