# Contributing to expdeploy

Thanks for your interest in contributing.

## Development setup

```bash
git clone https://github.com/lobennett/expdeploy.git
cd expdeploy
uv sync --extra dev
uv run pre-commit install
uv run playwright install --with-deps chromium
```

## Branches

- `main` is the integration branch; releases are tagged from `main` (`v0.X.Y`).
- Feature work lands on `feat/<short-name>` branches and merges via PR.
- Each PR runs the full CI matrix (Ubuntu+macOS × Python 3.11+3.12).

## Commit messages

Short imperative subject lines, ≤72 characters. Examples:
- `Add SupabaseAdapter.save (Postgres upsert + storage bucket upload)`
- `Drop dead tomli conditional dep (we require Python 3.11+)`

## Tests

- TDD is the default workflow. Write a failing test before the implementation.
- Three tiers: `tests/unit/`, `tests/integration/`, `tests/e2e/` (Playwright).
- New storage adapters must satisfy the parametrized adapter contract suite (TBD).
- E2E tests are marked `@pytest.mark.e2e`. Run with `uv run pytest -m e2e`.

## Lint + format + types

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/expdeploy
```

`pre-commit` runs all three on every commit. If a hook reformats your code, re-stage and commit again.

## jsPsych asset re-vendoring

If you bump the jsPsych version in `scripts/fetch_jspsych_assets.py`, re-run the script:

```bash
uv run python scripts/fetch_jspsych_assets.py
```

Commit the regenerated `src/expdeploy/jspsych_assets/<version>/` directory.

## Releasing

1. Bump `version` in `pyproject.toml` and `__version__` in `src/expdeploy/__init__.py`.
2. Open a PR titled `Release v0.X.Y`.
3. After merge, tag `v0.X.Y`. CI publishes the multi-arch container to GHCR and the wheel to PyPI.
