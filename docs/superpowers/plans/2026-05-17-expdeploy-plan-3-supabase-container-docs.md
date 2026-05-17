# expdeploy — Plan 3: Supabase, Container, Docs, Release CI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take v0.1-beta to **v0.1.0 release**. Add the Supabase remote-sync adapter, the OCI container (base image + `expdeploy build` for study images), an mkdocs-material documentation site, GitHub Actions release CI (publish to GHCR + PyPI on tags), and a handful of small cleanups carried over from Plans 1 and 2.

**Architecture:** Plan 1 + Plan 2 built the local-first deploy package; Plan 3 adds remote sync + reproducible container + public docs + release automation. The Supabase adapter implements `StorageAdapter` and is loaded conditionally via the `expdeploy[supabase]` extra. The container is a multi-arch OCI image with two layers: a slim `base` image (runtime only), and a `study` image built per-deployment via `expdeploy build` (FROM base + experiments baked in). The docs site is built with mkdocs-material and published to GitHub Pages. Release CI fires on `v*` tags and publishes both PyPI wheels (via PyPI Trusted Publishing) and multi-arch container images to `ghcr.io/lobennett/expdeploy`.

**Tech Stack:** Same as Plans 1+2 (Python 3.11+, FastAPI, Pydantic v2, Typer, Jinja, filelock, pytest, Playwright, ruff, mypy) + `supabase>=2.4` (in `[supabase]` extra) + `mkdocs-material>=9.5` (in `[docs]` extra) + Docker/Podman at vendor/build time + esbuild (already used).

**Source spec:** `docs/superpowers/specs/2026-05-14-expdeploy-design.md`. Plan 3 implements spec §5.5 (Supabase), §8 (CLI: `supabase` + `build` + real `sync`), §9 (container), §10.5 (docs).

**Repo:** `/Users/lobennett/grants/r01_rdoc/projects/expdeploy/` on `main` after Plans 1+2 merged (commit `7502576`).

**Branching:** Work on `feat/plan-3-supabase-container-docs`. Each task commits to that branch. Final task opens a PR + tags v0.1.0 after merge.

---

## Phase A — Small follow-ups from Plans 1+2

These are quick cleanups that should land before the new features so the foundation is clean.

### Task 1: Drop dead `tomli` dep and create feature branch

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Branch**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/expdeploy
git checkout main && git pull
git checkout -b feat/plan-3-supabase-container-docs
```

- [ ] **Step 2: Remove the dead conditional dep**

In `pyproject.toml`, find and delete this single line from `[project] dependencies`:

```toml
"tomli>=2.0 ; python_version < '3.11'",
```

(The package requires Python ≥3.11, so this fallback can never install.)

- [ ] **Step 3: Re-sync and confirm**

```bash
uv sync --extra dev
uv run python -c "import tomllib; print('tomllib OK')"
uv run pytest -v
```

Expected: tomllib import works, all 86 tests pass.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "Drop dead tomli conditional dep (we require Python 3.11+)"
```

---

### Task 2: Restore stderr semantics for CLI error messages

**Files:**
- Modify: `src/expdeploy/cli.py`
- Modify: `tests/unit/test_cli.py`

Plan 1 dropped `err=True` from `typer.echo(...)` calls because Typer's `CliRunner` defaults to merging stdout+stderr awkwardly. Plan 3 restores stderr by switching the test invocations to read stderr explicitly via `mix_stderr=False`.

- [ ] **Step 1: Update tests to read stderr**

In `tests/unit/test_cli.py`, change the `runner = CliRunner()` line to:

```python
runner = CliRunner(mix_stderr=False)
```

Then in each test that asserts on stdout for error messages, switch to stderr. Specifically:

- `test_validate_missing_manifest`: change `assert "manifest.toml" in result.stdout` → `assert "manifest.toml" in result.stderr`
- `test_validate_bad_bids_task_label`: just check `assert result.exit_code != 0` (the stderr content isn't load-bearing for this test)
- `test_run_command_rejects_busy_port`: change `out = (result.stdout or "") + (result.stderr or "")` (already merges) — replace with `assert "busy" in (result.stderr or "").lower() or "in use" in (result.stderr or "").lower()`.

- [ ] **Step 2: Add `err=True` back to error `typer.echo` calls in `cli.py`**

Find each `typer.echo(msg)` followed by `raise typer.Exit(code=...)` for error paths, and change to `typer.echo(msg, err=True)`. There are roughly 4-5 places (validate INVALID, run argument errors, port-busy, etc.). Don't touch success/info messages (they should stay on stdout).

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/test_cli.py -v
```

Expected: 16 tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/expdeploy/cli.py tests/unit/test_cli.py
git commit -m "Restore stderr for CLI error messages; use CliRunner(mix_stderr=False)"
```

---

### Task 3: BIDS sidecar JSON uses PascalCase field names

**Files:**
- Modify: `src/expdeploy/storage/fs.py`
- Modify: `tests/unit/test_fs.py`

Per BIDS spec, sidecar JSON uses `Description` (PascalCase), `Levels`, `Units`, etc. Plan 2's `_write_events_sidecar` used lowercase `description` to match a sloppy test assertion. Fix both to be BIDS-compliant.

- [ ] **Step 1: Update the test in `tests/unit/test_fs.py`**

In `test_save_bids_writes_json_sidecar`, change:

```python
assert data["trial_type"]["description"] == "Congruency of flanker."
assert data["trial_type"]["Levels"]["congruent"] == "Congruent"
```

to:

```python
assert data["trial_type"]["Description"] == "Congruency of flanker."
assert data["trial_type"]["Levels"]["congruent"] == "Congruent"
```

- [ ] **Step 2: Run; expect failure (current `fs.py` writes lowercase)**

- [ ] **Step 3: Fix `fs.py`**

In `_write_events_sidecar`, change `"description": col.description` → `"Description": col.description`.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_fs.py -v
```

Expected: 10 fs tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/expdeploy/storage/fs.py tests/unit/test_fs.py
git commit -m "BIDS sidecar JSON uses PascalCase Description per BIDS spec"
```

---

### Task 4: Dedupe core via esbuild `--external` for plugin bundles

**Files:**
- Modify: `scripts/fetch_jspsych_assets.py`

Currently each plugin bundle inlines a copy of jsPsych core (~60-70KB per plugin × 9 plugins). Adding `--external:jspsych` to the esbuild invocation for plugins (but not core) makes each plugin bundle reference `jspsych` as an external import (~5-15KB per plugin instead). The import map already resolves `jspsych` to `/static/jspsych/<version>/jspsych.js`, so plugins fetch core from there in the browser.

- [ ] **Step 1: Update `scripts/fetch_jspsych_assets.py`**

Find the esbuild invocation for plugins. Add `--external:jspsych` to the args list. Do NOT add it to the core build (`jspsych.js`); only plugins. The change should be small — locate `subprocess.run([..., "esbuild", ..., entry, ..., "--outfile=...", ...])` for plugins and append `"--external:jspsych"`.

- [ ] **Step 2: Re-run vendoring**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/expdeploy
uv run python scripts/fetch_jspsych_assets.py
```

Expected: same 10 entries in manifest.json, but plugins are much smaller (~10-15KB each instead of ~60-70KB).

- [ ] **Step 3: Verify plugins still reference jspsych as external**

```bash
grep -o 'from "jspsych"' src/expdeploy/jspsych_assets/8.2.3/plugins/*.js | head -3
```

Expected: each plugin .js has at least one `from "jspsych"` import.

- [ ] **Step 4: Run all tests including e2e**

```bash
uv run pytest -v
```

Expected: 86 tests pass. The e2e tests load jsPsych core THEN plugins — the import map resolves the bare `jspsych` specifier so plugin bundles can find their dep.

If the e2e tests fail because plugins can't resolve `jspsych`, revert the change. There's a subtle gotcha: when esbuild marks something `--external`, the runtime must resolve the bare specifier. In our case the import map handles that. But if esbuild emits `from "jspsych"` and the import map points `"jspsych"` to `/static/jspsych/8.2.3/jspsych.js`, the plugin bundle fetched at `/static/jspsych/8.2.3/plugins/X.js` would try to fetch `jspsych` relative to... actually, the import map is a top-level browser config, so it resolves everywhere. Should work.

- [ ] **Step 5: Compare sizes before/after**

Run `du -sh src/expdeploy/jspsych_assets/8.2.3/plugins/`. Expected: total dropped from ~600KB to ~150KB.

- [ ] **Step 6: Commit**

```bash
git add scripts/fetch_jspsych_assets.py src/expdeploy/jspsych_assets/
git commit -m "Dedupe core across plugin bundles via esbuild --external:jspsych"
```

---

## Phase B — Supabase adapter

### Task 5: Add `[supabase]` extra and adapter skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `src/expdeploy/storage/supabase.py`

- [ ] **Step 1: Add the optional dep**

In `pyproject.toml`'s `[project.optional-dependencies]` section, after the `dev` extra, add:

```toml
supabase = [
  "supabase>=2.4",
]
```

- [ ] **Step 2: Re-sync (without the extra) to confirm it isn't pulled in by default**

```bash
uv sync --extra dev
uv run python -c "import supabase" 2>&1 | tail -2
```

Expected: `ModuleNotFoundError: No module named 'supabase'`. Good — it's gated behind the extra.

- [ ] **Step 3: Sync with the extra**

```bash
uv sync --extra dev --extra supabase
uv run python -c "from supabase import create_client; print('supabase importable')"
```

Expected: prints `supabase importable`.

- [ ] **Step 4: Write `src/expdeploy/storage/supabase.py` (skeleton, full impl in Task 6)**

```python
"""Supabase storage adapter — Postgres table + storage bucket. Optional install."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from expdeploy.storage.base import RunRecord, SaveResult


if TYPE_CHECKING:
    from supabase import Client


@dataclass(frozen=True, slots=True)
class SupabaseConfig:
    url: str
    service_role_key: str
    schema: str = "expdeploy"
    bucket: str = "expdeploy-raw"

    @classmethod
    def from_env(cls) -> "SupabaseConfig":
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            msg = (
                "Supabase requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY env vars."
            )
            raise RuntimeError(msg)
        schema = os.environ.get("SUPABASE_SCHEMA", "expdeploy")
        bucket = os.environ.get("SUPABASE_BUCKET", "expdeploy-raw")
        return cls(url=url, service_role_key=key, schema=schema, bucket=bucket)


class SupabaseAdapter:
    """Mirrors runs to a Supabase Postgres table + storage bucket."""

    name = "supabase"

    def __init__(self, config: SupabaseConfig) -> None:
        self.config = config
        self._client: Client | None = None

    def _get_client(self) -> "Client":
        if self._client is None:
            from supabase import create_client
            self._client = create_client(self.config.url, self.config.service_role_key)
        return self._client

    def save(self, record: RunRecord) -> SaveResult:
        # Stubbed; full impl in Task 6.
        return SaveResult(ok=False, path="", error="not yet implemented")
```

- [ ] **Step 5: Commit (skeleton only — no tests yet, full impl in Task 6)**

```bash
git add pyproject.toml uv.lock src/expdeploy/storage/supabase.py
git commit -m "Add [supabase] extra and SupabaseAdapter skeleton"
```

---

### Task 6: Implement `SupabaseAdapter.save` + unit tests with mock client

**Files:**
- Modify: `src/expdeploy/storage/supabase.py`
- Create: `tests/unit/test_supabase.py`

The adapter writes two destinations per run:
1. Inserts a row into `<schema>.runs` (mirrors the SQLite catalog schema).
2. Uploads the raw JSON to `<bucket>/sub-XX/[ses-Y/]sub-XX_[ses-Y_]task-EXPID_run-Z_beh.json`.

We test against a mock `Client` (using `unittest.mock`) — no live Supabase needed. A separate Task 12 covers live integration testing behind a `pytest -m supabase` marker.

- [ ] **Step 1: Write tests `tests/unit/test_supabase.py`**

```python
"""Tests for expdeploy.storage.supabase.SupabaseAdapter (mocked client)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from expdeploy.storage.base import RunRecord
from expdeploy.storage.supabase import SupabaseAdapter, SupabaseConfig


def _record(**overrides) -> RunRecord:
    fields = dict(
        exp_id="hello",
        subject_id="01",
        started_at=datetime(2026, 5, 17, 10, 0, 0, tzinfo=UTC),
        ended_at=datetime(2026, 5, 17, 10, 1, 0, tzinfo=UTC),
        status="finished",
        trials=[{"trial_type": "html-keyboard-response", "rt": 250}],
    )
    fields.update(overrides)
    return RunRecord(**fields)


def _make_adapter() -> tuple[SupabaseAdapter, MagicMock]:
    cfg = SupabaseConfig(
        url="https://example.supabase.co",
        service_role_key="srk_test",
    )
    adapter = SupabaseAdapter(config=cfg)
    mock_client = MagicMock()
    adapter._client = mock_client
    return adapter, mock_client


def test_save_inserts_into_runs_table():
    adapter, client = _make_adapter()
    rec = _record(subject_id="01")
    client.schema.return_value.table.return_value.upsert.return_value.execute.return_value = MagicMock(
        data=[{"run_id": rec.run_id}], count=1
    )
    client.storage.from_.return_value.upload.return_value = MagicMock(path="ok")
    result = adapter.save(rec)
    assert result.ok is True
    # Confirm schema().table().upsert(...) was called with run_id present
    client.schema.assert_called_with(adapter.config.schema)
    upsert_call = client.schema.return_value.table.return_value.upsert.call_args
    payload = upsert_call.args[0]
    assert payload["run_id"] == rec.run_id
    assert payload["exp_id"] == "hello"
    assert payload["subject_id"] == "01"


def test_save_uploads_to_bucket():
    adapter, client = _make_adapter()
    rec = _record(subject_id="01", session_num="1", run_num="2")
    client.schema.return_value.table.return_value.upsert.return_value.execute.return_value = MagicMock(
        data=[{"run_id": rec.run_id}], count=1
    )
    client.storage.from_.return_value.upload.return_value = MagicMock(path="ok")
    result = adapter.save(rec)
    assert result.ok is True
    upload_call = client.storage.from_.return_value.upload.call_args
    storage_path = upload_call.kwargs.get("path") or upload_call.args[0]
    assert "sub-01" in storage_path
    assert "ses-1" in storage_path
    assert "run-2" in storage_path
    assert storage_path.endswith("_beh.json")


def test_save_returns_error_on_pg_failure():
    adapter, client = _make_adapter()
    client.schema.return_value.table.return_value.upsert.return_value.execute.side_effect = (
        RuntimeError("connection refused")
    )
    result = adapter.save(_record())
    assert result.ok is False
    assert "connection refused" in (result.error or "")


def test_config_from_env_requires_url_and_key(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        SupabaseConfig.from_env()


def test_config_from_env_reads_defaults(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "srk_test")
    cfg = SupabaseConfig.from_env()
    assert cfg.url == "https://example.supabase.co"
    assert cfg.schema == "expdeploy"
    assert cfg.bucket == "expdeploy-raw"


def test_config_from_env_overrides(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "srk_test")
    monkeypatch.setenv("SUPABASE_SCHEMA", "custom")
    monkeypatch.setenv("SUPABASE_BUCKET", "raw")
    cfg = SupabaseConfig.from_env()
    assert cfg.schema == "custom"
    assert cfg.bucket == "raw"
```

- [ ] **Step 2: Run; expect failures (save returns stub error)**

- [ ] **Step 3: Implement the full `save` method**

Replace the placeholder `save` method in `src/expdeploy/storage/supabase.py` with:

```python
import json
import re

_LABEL_RE = re.compile(r"^[a-zA-Z0-9-]+$")


def _make_storage_path(record: RunRecord) -> str:
    parts = [f"sub-{record.subject_id}"]
    if record.session_num is not None:
        parts.append(f"ses-{record.session_num}")
    fname = parts[:]
    fname.append(f"task-{record.exp_id}")
    if record.run_num is not None:
        fname.append(f"run-{record.run_num}")
    filename = "_".join(fname) + "_beh.json"
    return "/".join(parts) + "/" + filename


# Inside SupabaseAdapter:

def save(self, record: RunRecord) -> SaveResult:
    try:
        client = self._get_client()
        row = record.model_dump(mode="json")
        # Drop fields that don't have Postgres columns; trials/interaction become JSONB
        row["trials_json"] = row.pop("trials")
        row["interaction_data_json"] = row.pop("interaction_data")
        row.pop("raw_payload", None)  # raw bucket upload carries the payload
        client.schema(self.config.schema).table("runs").upsert(row).execute()

        storage_path = _make_storage_path(record)
        body = json.dumps(record.model_dump(mode="json"), sort_keys=True).encode("utf-8")
        client.storage.from_(self.config.bucket).upload(
            path=storage_path,
            file=body,
            file_options={"content-type": "application/json", "upsert": "true"},
        )
        remote_uri = f"{self.config.url}/storage/v1/object/{self.config.bucket}/{storage_path}"
    except Exception as exc:  # noqa: BLE001
        return SaveResult(ok=False, path="", error=str(exc))
    return SaveResult(ok=True, path=remote_uri)
```

Place `_make_storage_path` as a module-level helper (not inside the class). Add `import json` and `import re` to the top of the file.

- [ ] **Step 4: Run; expect 6 passed**

```bash
uv run pytest tests/unit/test_supabase.py -v
```

- [ ] **Step 5: Full suite check**

```bash
uv run pytest -v
```

Expected: 92 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/expdeploy/storage/supabase.py tests/unit/test_supabase.py
git commit -m "Implement SupabaseAdapter.save (Postgres upsert + storage bucket upload)"
```

---

### Task 7: `expdeploy supabase migrate` subcommand + SQL DDL

**Files:**
- Create: `src/expdeploy/storage/supabase_schema.sql`
- Modify: `src/expdeploy/storage/supabase.py` (add `apply_migrations`)
- Modify: `src/expdeploy/cli.py` (add `supabase` Typer group)
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 1: Write the DDL**

Create `src/expdeploy/storage/supabase_schema.sql`:

```sql
-- expdeploy Supabase schema. Idempotent.

CREATE SCHEMA IF NOT EXISTS expdeploy;

CREATE TABLE IF NOT EXISTS expdeploy.runs (
  run_id TEXT PRIMARY KEY,
  exp_id TEXT NOT NULL,
  exp_version TEXT,
  subject_id TEXT NOT NULL,
  session_num TEXT,
  run_num TEXT,
  battery_id TEXT,
  group_index INTEGER,
  started_at TIMESTAMPTZ NOT NULL,
  ended_at TIMESTAMPTZ,
  status TEXT NOT NULL,
  trials_json JSONB DEFAULT '[]'::jsonb,
  interaction_data_json JSONB DEFAULT '[]'::jsonb,
  jspsych_version TEXT,
  deploy_version TEXT,
  client_user_agent TEXT,
  inserted_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_runs_subject ON expdeploy.runs(subject_id, session_num, run_num);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON expdeploy.runs(started_at);
```

- [ ] **Step 2: Add `apply_migrations` method to SupabaseAdapter**

In `supabase.py`, add (inside the class):

```python
from pathlib import Path


def apply_migrations(self) -> None:
    """Apply idempotent DDL via the Postgres-meta REST endpoint (psql-like)."""
    schema_path = Path(__file__).resolve().parent / "supabase_schema.sql"
    sql = schema_path.read_text()
    client = self._get_client()
    # Supabase client's `postgrest` doesn't expose raw SQL; use the RPC `exec_sql` if
    # the project has it, otherwise instruct the user to apply via SQL editor.
    try:
        client.postgrest.rpc("exec_sql", {"sql": sql}).execute()
    except Exception as exc:  # noqa: BLE001
        # Fallback: print SQL for manual application
        msg = (
            f"Could not apply DDL automatically ({exc}). "
            f"Run the SQL at {schema_path} via the Supabase SQL editor."
        )
        raise RuntimeError(msg) from exc
```

Note: many Supabase projects don't have a `exec_sql` RPC by default. We surface a useful error pointing the user at the SQL file. Task 8 (test-connection) and the docs site (Phase D) will document the manual SQL editor flow.

- [ ] **Step 3: Add the CLI tests**

Append to `tests/unit/test_cli.py`:

```python
def test_supabase_migrate_without_env_fails(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    result = runner.invoke(app, ["supabase", "migrate"])
    assert result.exit_code != 0
    err = (result.stderr or "") + (result.stdout or "")
    assert "SUPABASE_URL" in err or "service_role" in err.lower()


def test_supabase_test_connection_without_env_fails(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    result = runner.invoke(app, ["supabase", "test-connection"])
    assert result.exit_code != 0
```

- [ ] **Step 4: Add the `supabase` Typer group to `cli.py`**

Near the top, after the existing `init_app = typer.Typer(...)` declaration, add:

```python
supabase_app = typer.Typer(help="Manage Supabase remote adapter.")
app.add_typer(supabase_app, name="supabase")


@supabase_app.command("migrate")
def supabase_migrate() -> None:
    """Apply idempotent DDL to the configured Supabase Postgres."""
    try:
        from expdeploy.storage.supabase import SupabaseAdapter, SupabaseConfig
        cfg = SupabaseConfig.from_env()
        adapter = SupabaseAdapter(config=cfg)
        adapter.apply_migrations()
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"Migration failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo("Schema applied.")


@supabase_app.command("test-connection")
def supabase_test_connection() -> None:
    """Verify the configured Supabase credentials and bucket access."""
    try:
        from expdeploy.storage.supabase import SupabaseAdapter, SupabaseConfig
        cfg = SupabaseConfig.from_env()
        adapter = SupabaseAdapter(config=cfg)
        client = adapter._get_client()
        # A trivial read against the configured schema.
        client.schema(cfg.schema).table("runs").select("run_id").limit(1).execute()
        typer.echo(f"Connected to {cfg.url} (schema={cfg.schema}, bucket={cfg.bucket}).")
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"Connection failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@supabase_app.command("drop")
def supabase_drop(
    confirm: Annotated[bool, typer.Option("--confirm", help="Required for destructive operation")] = False,
) -> None:
    """DROP the expdeploy schema. Test envs only."""
    if not confirm:
        typer.echo("Refusing without --confirm.", err=True)
        raise typer.Exit(code=2)
    try:
        from expdeploy.storage.supabase import SupabaseAdapter, SupabaseConfig
        cfg = SupabaseConfig.from_env()
        adapter = SupabaseAdapter(config=cfg)
        client = adapter._get_client()
        client.postgrest.rpc("exec_sql", {"sql": f"DROP SCHEMA IF EXISTS {cfg.schema} CASCADE;"}).execute()
        typer.echo(f"Dropped schema {cfg.schema}.")
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"Drop failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
```

- [ ] **Step 5: Update `[tool.hatch.build.targets.wheel.force-include]` in pyproject.toml**

Add `"src/expdeploy/storage/supabase_schema.sql" = "expdeploy/storage/supabase_schema.sql"` so the SQL file ships in the wheel.

- [ ] **Step 6: Run all tests**

```bash
uv run pytest -v
```

Expected: 94 tests pass.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/expdeploy/storage/supabase.py src/expdeploy/storage/supabase_schema.sql src/expdeploy/cli.py tests/unit/test_cli.py
git commit -m "Add 'expdeploy supabase' subcommand group (migrate, test-connection, drop)"
```

---

### Task 8: Real `expdeploy sync` implementation

**Files:**
- Modify: `src/expdeploy/cli.py` (replace stub `sync` with real implementation)
- Modify: `src/expdeploy/storage/sqlite.py` (add `pending_remote_writes`, `mark_synced`, `mark_failed`)
- Create: `tests/unit/test_sync.py`

The stub from Plan 2 just echoes a placeholder. Plan 3 implements:
1. Query `remote_sync` for `status != 'synced'`
2. For each, re-attempt the write against the named adapter
3. Update `remote_sync` row with new status

- [ ] **Step 1: Add SQLiteCatalog methods**

In `src/expdeploy/storage/sqlite.py`, add to the class:

```python
def record_remote_attempt(self, run_id: str, adapter: str, status: str, remote_uri: str | None = None, error: str | None = None) -> None:
    from datetime import UTC, datetime
    with self._connect() as conn:
        conn.execute(
            """
            INSERT INTO remote_sync (run_id, adapter, status, attempted_at, remote_uri, error)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, adapter) DO UPDATE SET
                status = excluded.status,
                attempted_at = excluded.attempted_at,
                remote_uri = excluded.remote_uri,
                error = excluded.error
            """,
            (run_id, adapter, status, datetime.now(UTC).isoformat(), remote_uri, error),
        )


def pending_remote_writes(self, adapter: str | None = None) -> list[dict[str, Any]]:
    with self._connect() as conn:
        if adapter is not None:
            rows = conn.execute(
                """
                SELECT r.* FROM runs r
                LEFT JOIN remote_sync rs ON r.run_id = rs.run_id AND rs.adapter = ?
                WHERE rs.status IS NULL OR rs.status != 'synced'
                """,
                (adapter,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT r.* FROM runs r
                WHERE r.run_id NOT IN (SELECT run_id FROM remote_sync WHERE status = 'synced')
                """,
            ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 2: Replace the stub `sync` command in `cli.py`**

```python
@app.command()
def sync(
    adapter: Annotated[str, typer.Option("--adapter")] = "supabase",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    data_dir: Annotated[Path, typer.Option("--data-dir")] = Path("./data"),
) -> None:
    """Replay failed remote-storage writes against the configured adapter."""
    catalog = SQLiteCatalog(db_path=data_dir / "catalog.sqlite")
    if not catalog.db_path.exists():
        typer.echo(f"No catalog at {catalog.db_path}", err=True)
        raise typer.Exit(code=1)
    pending = catalog.pending_remote_writes(adapter=adapter)
    if not pending:
        typer.echo("Nothing to sync.")
        return

    if dry_run:
        typer.echo(f"Would replay {len(pending)} run(s) against {adapter}:")
        for r in pending:
            typer.echo(f"  - {r['run_id']} ({r['subject_id']} / {r['exp_id']})")
        return

    if adapter != "supabase":
        typer.echo(f"Unknown adapter {adapter!r}", err=True)
        raise typer.Exit(code=2)

    from expdeploy.storage.supabase import SupabaseAdapter, SupabaseConfig

    try:
        cfg = SupabaseConfig.from_env()
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"Supabase config error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    sa = SupabaseAdapter(config=cfg)
    ok_count = 0
    fail_count = 0
    for row in pending:
        record = _row_to_run_record(row)
        result = sa.save(record)
        if result.ok:
            catalog.record_remote_attempt(record.run_id, adapter, "synced", remote_uri=result.path)
            ok_count += 1
        else:
            catalog.record_remote_attempt(record.run_id, adapter, "failed", error=result.error)
            fail_count += 1

    typer.echo(f"Synced {ok_count} / Failed {fail_count}.")
    if fail_count:
        raise typer.Exit(code=1)
```

Add the row-to-record helper at module level in cli.py:

```python
def _row_to_run_record(row: dict) -> "RunRecord":
    import json as _json
    from expdeploy.storage.base import RunRecord
    return RunRecord(
        run_id=row["run_id"],
        exp_id=row["exp_id"],
        exp_version=row["exp_version"],
        subject_id=row["subject_id"],
        session_num=row["session_num"],
        run_num=row["run_num"],
        battery_id=row["battery_id"],
        group_index=row["group_index"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        status=row["status"],
        trials=_json.loads(row["trials_json"] or "[]"),
        interaction_data=_json.loads(row["interaction_data_json"] or "[]"),
        jspsych_version=row["jspsych_version"],
        deploy_version=row["deploy_version"],
        client_user_agent=row["client_user_agent"],
    )
```

- [ ] **Step 3: Tests `tests/unit/test_sync.py`**

```python
"""Tests for the real `expdeploy sync` command."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from expdeploy.cli import app
from expdeploy.storage.base import RunRecord, SaveResult
from expdeploy.storage.sqlite import SQLiteCatalog


runner = CliRunner(mix_stderr=False)


def _rec(**overrides) -> RunRecord:
    fields = dict(
        exp_id="hello",
        subject_id="01",
        started_at=datetime(2026, 5, 17, tzinfo=UTC),
        ended_at=datetime(2026, 5, 17, 0, 1, tzinfo=UTC),
        status="finished",
        trials=[],
    )
    fields.update(overrides)
    return RunRecord(**fields)


def _seed(tmp_path, records: list[RunRecord]) -> Path:
    data_dir = tmp_path / "data"
    catalog = SQLiteCatalog(db_path=data_dir / "catalog.sqlite")
    catalog.init_schema()
    for r in records:
        catalog.save(r)
    return data_dir


def test_sync_with_empty_catalog(tmp_path):
    data_dir = tmp_path / "data"
    SQLiteCatalog(db_path=data_dir / "catalog.sqlite").init_schema()
    result = runner.invoke(app, ["sync", "--data-dir", str(data_dir)])
    assert result.exit_code == 0
    assert "Nothing to sync" in result.stdout


def test_sync_dry_run_lists_pending(tmp_path):
    data_dir = _seed(tmp_path, [_rec(subject_id="01"), _rec(subject_id="02")])
    result = runner.invoke(app, ["sync", "--data-dir", str(data_dir), "--dry-run"])
    assert result.exit_code == 0
    assert "Would replay 2" in result.stdout


def test_sync_supabase_records_results(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "srk_test")
    data_dir = _seed(tmp_path, [_rec(subject_id="01"), _rec(subject_id="02")])
    with patch("expdeploy.storage.supabase.SupabaseAdapter.save") as mock_save:
        mock_save.side_effect = [
            SaveResult(ok=True, path="supabase://r1"),
            SaveResult(ok=False, path="", error="boom"),
        ]
        result = runner.invoke(app, ["sync", "--data-dir", str(data_dir), "--adapter", "supabase"])
    assert result.exit_code == 1  # one failure → non-zero
    assert "Synced 1" in result.stdout
    assert "Failed 1" in result.stdout
    # Verify remote_sync rows
    catalog = SQLiteCatalog(db_path=data_dir / "catalog.sqlite")
    with catalog._connect() as conn:
        rows = conn.execute("SELECT status FROM remote_sync ORDER BY run_id").fetchall()
    statuses = sorted(r[0] for r in rows)
    assert statuses == ["failed", "synced"]


def test_sync_idempotent_after_success(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "srk_test")
    data_dir = _seed(tmp_path, [_rec(subject_id="01")])
    with patch("expdeploy.storage.supabase.SupabaseAdapter.save") as mock_save:
        mock_save.return_value = SaveResult(ok=True, path="supabase://r1")
        result_first = runner.invoke(app, ["sync", "--data-dir", str(data_dir), "--adapter", "supabase"])
        assert result_first.exit_code == 0
        # Second invocation: nothing pending
        result_second = runner.invoke(app, ["sync", "--data-dir", str(data_dir), "--adapter", "supabase"])
    assert result_second.exit_code == 0
    assert "Nothing to sync" in result_second.stdout
```

- [ ] **Step 4: Run all tests; expect 98 passed**

- [ ] **Step 5: Commit**

```bash
git add src/expdeploy/cli.py src/expdeploy/storage/sqlite.py tests/unit/test_sync.py
git commit -m "Real 'expdeploy sync': replay failed remote writes against Supabase"
```

---

### Task 9: Wire Supabase into the app via `--remote` flag

**Files:**
- Modify: `src/expdeploy/app.py` (POST /api/data: call configured remotes after FS+SQLite)
- Modify: `src/expdeploy/cli.py` (run accepts `--remote supabase`)
- Modify: `tests/integration/test_app.py`

- [ ] **Step 1: Add a `remotes: list[StorageAdapter]` field to `AppConfig`**

In `app.py`:

```python
@dataclass(frozen=True, slots=True)
class AppConfig:
    # ... existing fields ...
    remotes: tuple[StorageAdapter, ...] = ()
```

Note: tuple (not list) so the dataclass remains hashable / immutable.

- [ ] **Step 2: After FS+SQLite writes in `post_data`, iterate `remotes`**

After `if config.catalog is not None: config.catalog.save(record)`, add:

```python
for remote in config.remotes:
    rresult = remote.save(record)
    if config.catalog is not None:
        # Record per-adapter outcome to drive `expdeploy sync` later
        from expdeploy.storage.sqlite import SQLiteCatalog
        if isinstance(config.catalog, SQLiteCatalog):
            config.catalog.record_remote_attempt(
                record.run_id,
                remote.name,
                "synced" if rresult.ok else "failed",
                remote_uri=rresult.path if rresult.ok else None,
                error=None if rresult.ok else rresult.error,
            )
```

- [ ] **Step 3: Update CLI `run` to accept `--remote`**

Add to the `run` command signature:

```python
remote: Annotated[list[str] | None, typer.Option("--remote", help="Remote adapter names to mirror writes to.")] = None,
```

And after constructing FS/catalog, before creating `AppConfig`:

```python
remotes_list: list[StorageAdapter] = []
for r in (remote or []):
    if r == "supabase":
        from expdeploy.storage.supabase import SupabaseAdapter, SupabaseConfig
        sa = SupabaseAdapter(config=SupabaseConfig.from_env())
        remotes_list.append(sa)
    else:
        typer.echo(f"Unknown --remote adapter: {r}", err=True)
        raise typer.Exit(code=2)
```

Pass `remotes=tuple(remotes_list)` into both `AppConfig` constructions (single + battery).

- [ ] **Step 4: Add integration test with mocked Supabase**

In `tests/integration/test_app.py`, add:

```python
def test_post_data_calls_remote_adapter(hello_experiment, tmp_path):
    from expdeploy.storage.base import SaveResult
    mock_remote = MagicMock()
    mock_remote.name = "fake"
    mock_remote.save.return_value = SaveResult(ok=True, path="remote://x")
    data_dir = tmp_path / "data"
    catalog = SQLiteCatalog(db_path=data_dir / "catalog.sqlite")
    catalog.init_schema()
    config = AppConfig(
        vendored_root=_vendored_root(),
        storage=FSAdapter(data_dir=data_dir),
        catalog=catalog,
        state_dir=tmp_path / "state",
        subject_id="01",
        session_num=None,
        run_num=None,
        experiment=ExperimentLoader().load(hello_experiment),
        remotes=(mock_remote,),
    )
    client = TestClient(create_app(config))
    response = client.post("/api/data", json={
        "exp_id": "hello",
        "subject_id": "01",
        "trials": [],
        "status": "finished",
        "started_at": "2026-05-17T10:00:00+00:00",
        "ended_at": "2026-05-17T10:01:00+00:00",
    })
    assert response.status_code == 200
    mock_remote.save.assert_called_once()
```

Add `from unittest.mock import MagicMock` to the imports if not already present.

- [ ] **Step 5: Run all tests; expect 99 passed**

- [ ] **Step 6: Commit**

```bash
git add src/expdeploy/app.py src/expdeploy/cli.py tests/integration/test_app.py
git commit -m "Wire --remote supabase through CLI/app; record per-adapter remote_sync rows"
```

---

## Phase C — OCI container

### Task 10: Base image Dockerfile

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim AS runtime

# Install uv from its official image
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /opt/expdeploy

# Install Python deps first (cache layer)
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

RUN uv sync --frozen --no-dev --extra supabase \
    && rm -rf /root/.cache/uv

# Non-root for HPC / Apptainer compatibility
RUN useradd -m -u 1000 expdeploy
USER expdeploy

ENV PYTHONUNBUFFERED=1 \
    EXPDEPLOY_DATA_DIR=/data

EXPOSE 8080
VOLUME ["/data", "/experiments"]

ENTRYPOINT ["uv", "run", "--no-sync", "expdeploy"]
CMD ["--help"]

LABEL org.opencontainers.image.title="expdeploy" \
      org.opencontainers.image.source="https://github.com/lobennett/expdeploy" \
      org.opencontainers.image.licenses="MIT"
```

- [ ] **Step 2: Write `.dockerignore`**

```
.git/
.venv/
.uv/
.mypy_cache/
.ruff_cache/
.pytest_cache/
**/__pycache__/
**/*.pyc
data/
state/
tests/
docs/
examples/
.github/
*.md
.gitignore
.pre-commit-config.yaml
playwright-report/
test-results/
```

- [ ] **Step 3: Build locally to verify**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/expdeploy
podman build -t expdeploy:local .
podman run --rm expdeploy:local version
podman run --rm expdeploy:local --help
```

Expected: image builds (~2-4 min); first command prints `expdeploy 0.1.0a0`; second prints help with all subcommands.

- [ ] **Step 4: Smoke-test the image serving the hello-world**

```bash
podman run --rm -d -p 18080:8080 \
  -v "$PWD/examples/hello_world:/experiments/hello_world:ro" \
  -v "$PWD/data-container:/data" \
  --name expdeploy-smoke \
  expdeploy:local \
  run /experiments/hello_world --subject 01 --data-dir /data --port 8080 --no-browser

sleep 5
curl -s -w "\nHTTP %{http_code}\n" -o /dev/null http://127.0.0.1:18080/healthz
curl -s http://127.0.0.1:18080/ | head -3
podman stop expdeploy-smoke
rm -rf data-container
```

Expected: 200 on healthz; HTML output. If it fails, debug with `podman logs expdeploy-smoke`.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "Add base Dockerfile + .dockerignore; smoke-tested with podman locally"
```

---

### Task 11: `expdeploy build` subcommand

**Files:**
- Modify: `src/expdeploy/cli.py` (add `build` command)
- Modify: `tests/unit/test_cli.py`

`expdeploy build` generates a `study.Dockerfile` next to the battery, validates everything, computes content hashes for labels, and runs `docker build` (or `podman build`).

- [ ] **Step 1: Tests**

```python
def test_build_generates_dockerfile(tmp_path, monkeypatch):
    # Build manifests + battery
    for exp_id in ["flanker", "stroop"]:
        d = tmp_path / exp_id
        d.mkdir()
        (d / "manifest.toml").write_text(HELLO_TOML.replace('exp_id = "hello"', f'exp_id = "{exp_id}"'))
        (d / "index.js").write_text("export default () => {};")
    (tmp_path / "battery.toml").write_text(
        f'''[battery]
name = "study2026"
counterbalance = "fixed"

[[experiments]]
exp_id = "flanker"
path = "./flanker"

[[experiments]]
exp_id = "stroop"
path = "./stroop"
'''
    )
    # Mock subprocess.run so we don't actually invoke docker
    with patch("expdeploy.cli.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(
            app,
            [
                "build", str(tmp_path / "battery.toml"),
                "--tag", "ghcr.io/lobennett/study2026:test",
                "--engine", "podman",
                "--no-push",
            ],
        )
    assert result.exit_code == 0, result.stdout
    dockerfile = tmp_path / "study.Dockerfile"
    assert dockerfile.exists()
    body = dockerfile.read_text()
    assert "FROM ghcr.io/lobennett/expdeploy:" in body
    assert "COPY ./flanker" in body
    assert "COPY ./stroop" in body
    assert "COPY ./battery.toml" in body


def test_build_invokes_engine(tmp_path):
    d = tmp_path / "exp"
    d.mkdir()
    (d / "manifest.toml").write_text(HELLO_TOML.replace('exp_id = "hello"', 'exp_id = "single"'))
    (d / "index.js").write_text("export default () => {};")
    (tmp_path / "battery.toml").write_text(
        '''[battery]
name = "x"
counterbalance = "fixed"

[[experiments]]
exp_id = "single"
path = "./exp"
'''
    )
    with patch("expdeploy.cli.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(
            app,
            ["build", str(tmp_path / "battery.toml"), "--tag", "t:1", "--engine", "podman", "--no-push"],
        )
    assert result.exit_code == 0
    # Confirm the engine got called with build + -t
    calls = [c.args[0] for c in mock_run.call_args_list]
    build_calls = [c for c in calls if "build" in c]
    assert build_calls, "expected at least one engine build call"
    assert any("t:1" in c for c in build_calls)
```

- [ ] **Step 2: Add `build` command to `cli.py`**

```python
import hashlib
import subprocess


@app.command()
def build(
    target: Annotated[Path, typer.Argument(exists=True, help="Path to battery.toml or experiment dir")],
    tag: Annotated[str, typer.Option("--tag", help="OCI image tag, e.g. ghcr.io/you/study:2026-05-17")],
    base_tag: Annotated[str, typer.Option("--base-tag", help="Base image tag to FROM")] = "ghcr.io/lobennett/expdeploy:latest",
    engine: Annotated[str, typer.Option("--engine", help="docker | podman")] = "docker",
    push: Annotated[bool, typer.Option("--push/--no-push")] = False,
    output: Annotated[Path | None, typer.Option("--output", help="Where to write study.Dockerfile (default: next to target)")] = None,
) -> None:
    """Build a study-specific OCI image with experiments baked in."""
    target = target.resolve()
    if target.is_file() and target.suffix == ".toml":
        battery = load_battery(target)
        battery_dir = target.parent
        copies = [(e.exp_id, Path(e.path) if Path(e.path).is_absolute() else (battery_dir / e.path).resolve()) for e in battery.experiments]
        battery_file = target.name
    elif target.is_dir() and (target / "manifest.toml").exists():
        loaded = ExperimentLoader().load(target)
        battery = None
        copies = [(loaded.manifest.experiment.exp_id, target)]
        battery_file = None
        battery_dir = target.parent
    else:
        typer.echo(f"{target} is neither battery.toml nor an experiment dir", err=True)
        raise typer.Exit(code=2)

    # Validate each experiment
    for _eid, p in copies:
        ExperimentLoader().load(p)

    # Compute manifest hash (content provenance label)
    h = hashlib.sha256()
    for _eid, p in copies:
        for f in sorted(p.rglob("*")):
            if f.is_file():
                h.update(f.read_bytes())
    if battery_file:
        h.update((battery_dir / battery_file).read_bytes())
    manifest_hash = h.hexdigest()[:16]

    # Build the Dockerfile body
    lines = [f"FROM {base_tag}"]
    for eid, p in copies:
        # Use COPY <relative-to-Dockerfile> /experiments/<eid>
        rel = p.relative_to(battery_dir) if p.is_relative_to(battery_dir) else p
        lines.append(f"COPY {rel} /experiments/{eid}")
    if battery_file:
        lines.append(f"COPY {battery_file} /experiments/{battery_file}")
        lines.append(f'ENV EXPDEPLOY_BATTERY=/experiments/{battery_file}')
        cmd = f"CMD [\"run\", \"/experiments/{battery_file}\"]"
    else:
        eid = copies[0][0]
        cmd = f"CMD [\"run\", \"/experiments/{eid}\"]"
    lines.append(f'LABEL org.expdeploy.manifest_hash="{manifest_hash}"')
    lines.append(f'LABEL org.expdeploy.deploy_version="{__version__}"')
    lines.append(cmd)

    dockerfile_path = (output if output else (battery_dir / "study.Dockerfile")).resolve()
    dockerfile_path.write_text("\n".join(lines) + "\n")
    typer.echo(f"Wrote {dockerfile_path}")

    # Invoke the engine
    build_cmd = [engine, "build", "-f", str(dockerfile_path), "-t", tag, str(battery_dir)]
    typer.echo(" ".join(build_cmd))
    proc = subprocess.run(build_cmd, check=False)
    if proc.returncode != 0:
        typer.echo(f"{engine} build failed (exit {proc.returncode})", err=True)
        raise typer.Exit(code=proc.returncode)

    if push:
        push_cmd = [engine, "push", tag]
        typer.echo(" ".join(push_cmd))
        proc = subprocess.run(push_cmd, check=False)
        if proc.returncode != 0:
            typer.echo(f"{engine} push failed (exit {proc.returncode})", err=True)
            raise typer.Exit(code=proc.returncode)

    typer.echo(f"Built {tag}")
```

- [ ] **Step 3: Run tests; expect 101 passed**

- [ ] **Step 4: Manual smoke-build the example mini_battery**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/expdeploy
uv run expdeploy build ./examples/mini_battery/battery.toml \
  --tag expdeploy-mini-battery:local \
  --engine podman \
  --no-push
```

Expected: writes `examples/mini_battery/study.Dockerfile`, builds the image. Optional: `podman run --rm expdeploy-mini-battery:local --help`.

Clean up: `git checkout -- examples/mini_battery/study.Dockerfile` (don't commit the generated file).

- [ ] **Step 5: Commit**

```bash
git add src/expdeploy/cli.py tests/unit/test_cli.py
git commit -m "Add 'expdeploy build' command (generates study.Dockerfile + builds OCI image)"
```

---

## Phase D — Documentation site

### Task 12: mkdocs-material scaffold

**Files:**
- Modify: `pyproject.toml` (`[docs]` extra)
- Create: `mkdocs.yml`
- Create: `docs/index.md`
- Create: `docs/getting-started.md`
- Create: `docs/cli-reference.md`
- Create: `docs/manifest.md`
- Create: `docs/storage.md`
- Create: `docs/container.md`

- [ ] **Step 1: Add `[docs]` extra to pyproject.toml**

```toml
docs = [
  "mkdocs>=1.6",
  "mkdocs-material>=9.5",
  "mkdocs-typer>=0.0.3",
]
```

`mkdocs-typer` auto-generates the CLI reference page from the Typer app.

- [ ] **Step 2: Sync and verify**

```bash
uv sync --extra dev --extra docs
uv run mkdocs --version
```

Expected: prints mkdocs version.

- [ ] **Step 3: Write `mkdocs.yml` at the repo root**

```yaml
site_name: expdeploy
site_description: Modern Python deploy tool for jsPsych v8 experiments
site_url: https://lobennett.github.io/expdeploy/
repo_url: https://github.com/lobennett/expdeploy
repo_name: lobennett/expdeploy
edit_uri: edit/main/docs/

theme:
  name: material
  features:
    - navigation.sections
    - navigation.tabs
    - content.code.copy
    - content.code.annotate
  palette:
    - scheme: default
      primary: indigo
      toggle:
        icon: material/brightness-7
        name: Dark mode
    - scheme: slate
      primary: indigo
      toggle:
        icon: material/brightness-4
        name: Light mode

nav:
  - Home: index.md
  - Getting started: getting-started.md
  - Experiment manifest: manifest.md
  - Storage adapters: storage.md
  - Container: container.md
  - CLI reference: cli-reference.md

markdown_extensions:
  - admonition
  - attr_list
  - md_in_html
  - pymdownx.details
  - pymdownx.highlight:
      anchor_linenums: true
  - pymdownx.inlinehilite
  - pymdownx.snippets
  - pymdownx.superfences
  - tables
  - toc:
      permalink: true
```

- [ ] **Step 4: Write `docs/index.md`**

```markdown
# expdeploy

A modern Python deploy tool for [jsPsych v8](https://www.jspsych.org/) experiments.

**Status: v0.1.0** — lab-ready.

## What it does

- Serves jsPsych v8 experiments locally with **zero Node.js dependency** for experimenters.
- Authoring in canonical ESM (`import { initJsPsych } from 'jspsych'`) with local imports working out of the box.
- **BIDS-compatible** filesystem layout for fMRI and behavioral data.
- **Batteries** of experiments with four counterbalance schemes (fixed, Latin square, seeded random, user-supplied).
- **Local-first** storage with optional Supabase mirror, replayable via `expdeploy sync`.
- **Reproducibility**: layered OCI images via `expdeploy build` — a study image freezes deploy version, jsPsych version, every experiment file, and every Python dep.

## Quick install

```bash
uv tool install expdeploy
expdeploy run ./examples/hello_world --subject 01
```

→ [Getting started](getting-started.md)
```

- [ ] **Step 5: Write the remaining pages**

For brevity, each page is a sketch — Phase D is a content-light pass that proves the site builds; expanding content can happen in v0.2.

`docs/getting-started.md`:

```markdown
# Getting started

## Install

The package will be available on PyPI after the v0.1.0 release:

```bash
uv tool install expdeploy
```

For development:

```bash
git clone https://github.com/lobennett/expdeploy.git
cd expdeploy
uv sync --extra dev
```

## Run the hello-world

```bash
expdeploy run ./examples/hello_world --subject 01 --port 8080
```

This opens `http://localhost:8080` in your browser. Press any key on the stimulus and you'll see a `Saved.` confirmation. The raw JSON lands at `./data/raw/sub-01/sub-01_task-hello_beh.json`; an entry appears in `./data/catalog.sqlite`.

## Inspect runs

```bash
expdeploy status --data-dir ./data
```

## Run a battery

```bash
expdeploy run ./examples/mini_battery/battery.toml --subject 0
```

Or inline:

```bash
expdeploy run \
  --exps ./flanker,./stroop,./nback \
  --counterbalance latin_square \
  --subject 01
```
```

`docs/manifest.md`:

```markdown
# Experiment manifest

Each experiment is a folder containing `manifest.toml`, `index.js` (the ESM entry point), and optionally `style.css`, `assets/`, `lib/`.

## Minimal manifest.toml

```toml
[experiment]
exp_id = "flanker"
name = "Flanker"
version = "1.0.0"
entry = "index.js"

[jspsych]
version = "8.2.3"
plugins = ["@jspsych/plugin-html-keyboard-response@2.1.0"]
```

## BIDS-aware manifest

```toml
[bids]
type = "fmri"        # or "behavioral"
task = "flanker"     # BIDS task label: alphanumeric only

[bids.columns.trial_type]
Description = "Congruency of flanker."
Levels = { congruent = "Congruent", incongruent = "Incongruent" }
```

When the `[bids]` block is present, expdeploy writes a BIDS-compliant `events.tsv` (or `_beh.tsv`) under `data/bids/sub-XX/[ses-Y/]{func,beh}/`, plus a `_events.json` sidecar describing each column.

## `index.js`

```javascript
import { initJsPsych } from 'jspsych';
import htmlKeyboardResponse from '@jspsych/plugin-html-keyboard-response';

export default function build() {
  const startedAt = new Date().toISOString();
  const jsPsych = initJsPsych({
    on_finish: () => {
      window.expdeploy.submit({
        exp_id: window.expdeploy.expId,
        subject_id: window.expdeploy.subjectId,
        started_at: startedAt,
        ended_at: new Date().toISOString(),
        trials: jsPsych.data.get().values(),
        status: "finished",
      });
    },
  });
  jsPsych.run([
    { type: htmlKeyboardResponse, stimulus: "<p>Press any key.</p>" },
  ]);
}
```

## `window.expdeploy` runtime globals

- `expId` / `subjectId` / `sessionNum` / `runNum` / `groupIndex` / `deployVersion` — injected by the server
- `vars` — values passed via `--vars '{"...": ...}'` on the CLI
- `submit(payload)` — POSTs trial data to `/api/data`; returns a Promise that resolves with `{ok, path}` or rejects on error
```

`docs/storage.md`:

```markdown
# Storage adapters

Each completed run writes to up to three places:

1. **FSAdapter (always on)** — raw JSON + BIDS layout (if `[bids]` is set)
2. **SQLiteCatalog (always on)** — local index of runs at `data/catalog.sqlite`
3. **Remote adapters (optional)** — currently `supabase`; future: firebase, mongo, s3

## Filesystem layout

```
data/
├── catalog.sqlite
├── raw/
│   └── sub-01/
│       └── ses-01/
│           └── sub-01_ses-01_task-flanker_run-01_beh.json
└── bids/                              # only if [bids] in manifest
    ├── dataset_description.json
    ├── participants.tsv
    └── sub-01/
        └── ses-01/
            ├── func/                  # fMRI
            │   ├── ..._events.tsv
            │   └── ..._events.json    # sidecar
            └── beh/                   # behavioral
```

## Supabase adapter

Install the extra:

```bash
uv tool install 'expdeploy[supabase]'
```

Configure via env vars:

```
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=eyJ...   # never the anon key
export SUPABASE_SCHEMA=expdeploy           # optional
export SUPABASE_BUCKET=expdeploy-raw       # optional
```

Apply the schema:

```bash
expdeploy supabase migrate
```

If the project doesn't have the `exec_sql` RPC, run the SQL at `src/expdeploy/storage/supabase_schema.sql` via the Supabase SQL editor manually.

Mirror runs to Supabase:

```bash
expdeploy run ./examples/hello_world --subject 01 --remote supabase
```

Replay any failed remote writes:

```bash
expdeploy sync --adapter supabase
```

## Security note

The Supabase service role key bypasses RLS — guard it like a database password. Don't commit it; use environment variables or a secret manager. Participants don't authenticate against Supabase; the deploy server is the trusted writer.
```

`docs/container.md`:

```markdown
# Container

The OCI image lives at `ghcr.io/lobennett/expdeploy:<version>` (multi-arch: linux/amd64 + linux/arm64).

## Day-to-day dev (bind-mount)

```bash
podman run --rm -p 8080:8080 \
  -v $PWD/experiments:/experiments:ro \
  -v $PWD/data:/data \
  ghcr.io/lobennett/expdeploy:latest \
  run /experiments/flanker --subject 01 --data-dir /data
```

## Study image (reproducible scientific artifact)

`expdeploy build` produces an image with experiments baked in. This is the image you cite in your paper.

```bash
expdeploy build ./battery.toml \
  --tag ghcr.io/your-lab/study-2026:2026-05-17 \
  --engine podman \
  --push
```

The generated `study.Dockerfile` is written next to the battery file and is gitable for transparency. The image carries OCI labels:

- `org.expdeploy.manifest_hash` — content hash of every experiment file + battery.toml
- `org.expdeploy.deploy_version` — `expdeploy` version that built the image

## Apptainer / Singularity

```bash
apptainer pull docker://ghcr.io/lobennett/expdeploy:latest
apptainer run --bind ./experiments:/experiments --bind ./data:/data \
  expdeploy.sif run /experiments/battery.toml --subject 01
```
```

`docs/cli-reference.md`:

```markdown
# CLI reference

::: mkdocs-typer
    :module: expdeploy.cli
    :command: app
```

If `mkdocs-typer` isn't compatible with the current Typer version, replace the directive with hand-written sections per subcommand for v0.1.0 (each can be cribbed from `expdeploy <cmd> --help`).

- [ ] **Step 6: Build the site locally**

```bash
uv run mkdocs build
ls site/index.html
```

Expected: `site/index.html` exists, build is clean.

- [ ] **Step 7: Optional preview**

```bash
uv run mkdocs serve -a 127.0.0.1:8000 &
sleep 2
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:8000/
pkill -f "mkdocs serve"
```

- [ ] **Step 8: Add `site/` to `.gitignore`**

Edit `.gitignore`, append:

```
# mkdocs build output
site/
```

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml uv.lock mkdocs.yml docs/index.md docs/getting-started.md docs/manifest.md docs/storage.md docs/container.md docs/cli-reference.md .gitignore
git commit -m "Add mkdocs-material docs site (index + getting-started + manifest + storage + container + CLI ref)"
```

---

## Phase E — Release CI

### Task 13: GitHub Pages workflow for docs

**Files:**
- Create: `.github/workflows/docs.yml`

- [ ] **Step 1: Write `.github/workflows/docs.yml`**

```yaml
name: Docs

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          version: "0.5.x"
      - run: uv python install 3.12
      - run: uv sync --extra docs
      - run: uv run mkdocs build --strict
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/docs.yml
git commit -m "CI: build + deploy mkdocs site to GitHub Pages on push to main"
```

Note: GitHub Pages setup must be enabled in the repo settings (Source: GitHub Actions). The user should do that once the PR merges.

---

### Task 14: Multi-arch container release CI

**Files:**
- Create: `.github/workflows/container.yml`

- [ ] **Step 1: Write `.github/workflows/container.yml`**

```yaml
name: Container

on:
  push:
    tags: ['v*']
  workflow_dispatch:

permissions:
  contents: read
  packages: write

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository_owner }}/expdeploy
          tags: |
            type=ref,event=tag
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=raw,value=latest
      - uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/container.yml
git commit -m "CI: publish multi-arch OCI image to GHCR on v* tags"
```

---

### Task 15: PyPI release CI

**Files:**
- Create: `.github/workflows/release.yml`

Uses PyPI Trusted Publishing (no API tokens; OIDC).

- [ ] **Step 1: Write `.github/workflows/release.yml`**

```yaml
name: Release

on:
  push:
    tags: ['v*']
  workflow_dispatch:

permissions:
  contents: read
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          version: "0.5.x"
      - run: uv python install 3.12
      - run: uv sync --extra dev
      - run: uv build
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
  publish:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: pypi
      url: https://pypi.org/p/expdeploy
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@release/v1
        with:
          packages-dir: dist/
```

Note: requires a Trusted Publisher to be configured at https://pypi.org/manage/account/publishing/ pointing to this repo + workflow. The user must do that out-of-band before the first release fires.

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "CI: publish PyPI wheels via Trusted Publishing on v* tags"
```

---

### Task 16: CONTRIBUTING.md

**Files:**
- Create: `CONTRIBUTING.md`

- [ ] **Step 1: Write `CONTRIBUTING.md`**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add CONTRIBUTING.md
git commit -m "Add CONTRIBUTING.md"
```

---

## Phase F — Release

### Task 17: Final local verification

- [ ] **Step 1: Lint clean**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/expdeploy
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 2: Type clean**

```bash
uv run mypy src/expdeploy
```

- [ ] **Step 3: All tests pass**

```bash
uv run pytest -v
```

Expected: 101+ tests.

- [ ] **Step 4: Wheel builds**

```bash
uv build
ls dist/
```

Expected: `expdeploy-0.1.0a0-py3-none-any.whl` + sdist. (Version will be bumped to 0.1.0 in Task 19.)

- [ ] **Step 5: Container smoke (already verified in Task 10, just confirm one more time)**

```bash
podman build -t expdeploy:final-check .
podman run --rm expdeploy:final-check version
```

- [ ] **Step 6: Docs build clean**

```bash
uv run mkdocs build --strict
```

`--strict` makes warnings fatal — confirms no broken links.

- [ ] **Step 7: No commit — verification only.**

---

### Task 18: Open PR

- [ ] **Step 1: Push the branch**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/expdeploy
git push -u origin feat/plan-3-supabase-container-docs
```

- [ ] **Step 2: Open PR**

```bash
gh pr create --base main --head feat/plan-3-supabase-container-docs \
  --title "Plan 3: Supabase + container + docs + release CI" \
  --body "$(cat <<'EOF'
## Summary
- Adds `SupabaseAdapter` (Postgres + storage bucket) under `expdeploy[supabase]` extra.
- Adds `expdeploy supabase` subcommands: `migrate`, `test-connection`, `drop`.
- Real `expdeploy sync` replays failed remote writes via the SQLite `remote_sync` table.
- App `--remote supabase` mirrors writes after FS+SQLite (best-effort; non-blocking on remote failure).
- Adds slim multi-arch OCI base image (`Dockerfile`) + `.dockerignore`; smoke-tested with podman.
- Adds `expdeploy build` to generate a study `study.Dockerfile` + invoke the engine; OCI labels record `manifest_hash` + `deploy_version`.
- Adds mkdocs-material docs site (home, getting started, manifest, storage, container, CLI reference).
- Adds three GitHub Actions workflows: Pages deploy on push to main; multi-arch container publish on v* tags; PyPI wheel publish on v* tags via Trusted Publishing.
- Carries over four cleanups: drops dead `tomli` conditional dep, restores stderr for CLI errors, fixes BIDS sidecar PascalCase (`Description`/`Levels`), dedupes core across plugin bundles via esbuild `--external:jspsych`.

## Test plan
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src/expdeploy && uv run pytest -v` all green.
- [ ] `podman build .` + `podman run --rm expdeploy:local version` works.
- [ ] `uv run mkdocs build --strict` clean.
- [ ] CI matrix green (Ubuntu+macOS × Python 3.11+3.12).
- [ ] Manual: `expdeploy run examples/mini_battery/battery.toml --subject 0 --remote supabase` with `SUPABASE_*` env vars set — TBD post-merge once Supabase project provisioned.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Watch CI**

```bash
gh pr checks
```

Expected: all green within ~10 min.

---

### Task 19: Bump version to 0.1.0 and tag the release

After PR #2 is merged to main:

- [ ] **Step 1: Bump version**

In `pyproject.toml`: change `version = "0.1.0a0"` to `version = "0.1.0"`.
In `src/expdeploy/__init__.py`: change `__version__ = "0.1.0a0"` to `__version__ = "0.1.0"`.

- [ ] **Step 2: Commit + tag**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/expdeploy
git checkout main && git pull
git checkout -b release/v0.1.0
# edit version files...
git add pyproject.toml src/expdeploy/__init__.py
git commit -m "Release v0.1.0"
git push -u origin release/v0.1.0
gh pr create --base main --title "Release v0.1.0" --body "Version bump for first stable release."
```

After that PR merges:

```bash
git checkout main && git pull
git tag -a v0.1.0 -m "expdeploy v0.1.0 — lab-ready release"
git push origin v0.1.0
```

The tag push triggers the **container** and **release** workflows. PyPI Trusted Publishing must be configured at https://pypi.org/manage/account/publishing/ first (one-time setup).

- [ ] **Step 3: Verify**

```bash
gh run list --workflow=container.yml --limit=1
gh run list --workflow=release.yml --limit=1
```

Both should be running / green. After they complete:

- `ghcr.io/lobennett/expdeploy:v0.1.0` + `:0.1.0` + `:latest` published (multi-arch).
- `expdeploy==0.1.0` on PyPI.

---

## Summary of what Plan 3 produces

After Task 19:

- **Remote sync**: Supabase adapter installable via `pip install expdeploy[supabase]`; works through `--remote supabase` flag; `expdeploy sync` replays failures.
- **Container**: Multi-arch OCI base image at `ghcr.io/lobennett/expdeploy:0.1.0`; `expdeploy build` produces study-specific reproducible images.
- **Docs**: mkdocs-material site live at https://lobennett.github.io/expdeploy/.
- **PyPI**: `expdeploy==0.1.0` published.
- **CI**: Pages deploy on main; container + PyPI publish on v* tags.
- **Cleanups**: BIDS spec-compliant sidecar JSON, stderr for CLI errors, smaller plugin bundles (~250KB savings via esbuild dedup), no dead `tomli` dep.

**Plan 3 is the final plan.** After Task 19, expdeploy is at v0.1.0 stable — a real, runnable, tested, containerized, documented, published, distributable lab tool.

## Open questions to flag at PR review

1. **Supabase `exec_sql` RPC** — many projects don't have this by default. `expdeploy supabase migrate` falls back to "run the SQL via the dashboard manually." Worth documenting prominently.
2. **PyPI Trusted Publishing** — requires one-time setup at PyPI. The release workflow will fail until that's configured.
3. **GitHub Pages** — must be enabled in the repo's Pages settings (Source: GitHub Actions) before docs deploy succeeds.
4. **mkdocs-typer compatibility** — if it doesn't work with the current Typer version, the CLI reference page degrades to a placeholder; replace with hand-written sections.
