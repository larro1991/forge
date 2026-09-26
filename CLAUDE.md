# CLAUDE.md

Guidance for AI agents (and humans) working in this repo.

## What this repo is

FORGE — a structured, YAML-driven assessment framework (`engine.py`) with
pluggable "disciplines" (`disciplines/*.yaml`), an intake/gate system for
skipping irrelevant questions, and a discipline router.

## Running tests

```bash
python3 -m pip install --user pytest pyyaml   # first time only
python3 -m pytest -q
```

Tests live at the repo root as `test_*.py`:
- `test_engine.py` — discipline loading, `ForgeEngine` core (answers, gaps,
  fixes, verification, reporting), FRAMEWORK.md/security.yaml DQ-count sync.
- `test_intake_router.py` — intake questions, gate system, discipline router,
  deduplication, consolidation/service analysis.
- `test_forge_lint.py` — the DQ-file linter (see below), including that the
  real `disciplines/*.yaml` + `forge-profile-*.json` data lints clean.
- `test_bazarr_priority_search.py` — API-key handling only (no DB/network).

All tests run offline — no network access, no live credentials.

## Running the DQ-file linter

```bash
python3 forge_lint.py
```

Validates `disciplines/*.yaml` and `forge-profile-*.json`:
- required schema fields (discipline top-level, BQ/TQ/DQ, KB entries)
- duplicate mapping keys within a YAML file (PyYAML silently keeps the last
  value on a duplicate key, so this needs a dedicated check)
- duplicate DQ text within the same TQ
- `triage_presets` referencing real BQs
- `gates.yaml` conditions referencing real `intake.yaml` fields, and targets
  referencing real discipline/BQ/TQ/DQ-index paths
- `router.yaml` referencing real disciplines and decision-tree nodes
- `forge-profile-*.json` matching the schema `engine.create_profile()`
  writes, with answers referencing real intake fields and valid values

Exit code is non-zero if any error is found. Run it before committing changes
to any file under `disciplines/` or any `forge-profile-*.json`.

## CI

`.github/workflows/tests.yml` runs `pytest` and `forge_lint.py` on every push
and pull request. Both must pass before merging.

## Guardrails

- **No real credentials, ever.** Scripts that talk to external services
  (e.g. `bazarr_priority_search.py`) read secrets from environment variables
  and fail loudly with a clear message if unset. Never hardcode API keys,
  tokens, or passwords — including "rotated" or "dead" ones. `.env` is
  gitignored; use it for local secrets, never commit it.
- **No network calls in tests or CI.** This repo's test suite and linter run
  fully offline. Don't add tests that hit real APIs, databases, or hosts.
- **No private network references.** This is a public repo — never commit
  private IPs (e.g. `192.168.x.x`, `10.x.x.x`), internal hostnames, or
  account-specific identifiers.
- **This is a public repo.** Assume everything committed here is visible to
  anyone. If something looks like it might be a live secret, don't print or
  commit it — flag the file instead and let a human rotate/handle it.
