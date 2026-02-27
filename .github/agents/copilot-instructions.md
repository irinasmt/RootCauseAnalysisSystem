# RootCauseAnalysisSystem Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-02-22

## Active Technologies

- Python 3.12+ + Pydantic v2, standard library (`json`, `pathlib`, `datetime`, `random`), pytest (001-build-realistic-mock)

## Project Structure

```text
src/
tests/
```

## Commands

cd src; pytest; ruff check .

## Code Style

Python 3.12+: Follow standard conventions

## Recent Changes

- 001-build-realistic-mock: Added Python 3.12+ + Pydantic v2, standard library (`json`, `pathlib`, `datetime`, `random`), pytest

## Architecture Principles

- Architecture review stance:
  - Do not blindly accept architecture decisions.
  - Always evaluate whether a simpler, safer, or more scalable design exists.
  - For non-trivial architecture choices, present at least one alternative with explicit tradeoffs
    (complexity, operability, cost, reliability, and migration impact).
  - If the proposed architecture appears risky or over-engineered, call it out clearly and suggest
    a concrete improvement path.
  - Prefer evidence-driven recommendations (tests, failure modes, runtime constraints, data shape,
    and production operability) over stylistic preference.
