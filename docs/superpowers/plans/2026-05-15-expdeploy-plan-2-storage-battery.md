# expdeploy — Plan 2: Storage, Battery & Counterbalance

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the Plan-1 v0.1-alpha into a v0.1-beta that can run a real battery of experiments with full BIDS-compliant data output, a queryable SQLite catalog, four counterbalance schemes, and a richer CLI (`init`, `status`, `sync` stub). Continues to satisfy all Plan-1 acceptance criteria plus new ones for batteries.

**Architecture:** Layered on top of Plan 1's package. `RunRecord` gets enriched fields (ULID, timestamps, status, group_index, battery_id, etc.). `FSAdapter` splits raw-JSON writes from BIDS-layout writes. `SQLiteCatalog` joins as a second always-on adapter. `RunSession` (file-locked per-subject state) and `BatteryOrchestrator` (manifest + counterbalance + session) are introduced. FastAPI app gains state endpoints and switches from a static `subject_id` config to an orchestrator-driven "which experiment next" lookup. CLI gains `init`, `status`, and `sync`.

**Tech Stack:** Same as Plan 1 (Python 3.11+, FastAPI, Pydantic v2, Typer, Jinja2, filelock, pytest, Playwright, ruff, mypy) plus `python-ulid` for run IDs and `sqlite3` (stdlib).

**Source spec:** `docs/superpowers/specs/2026-05-14-expdeploy-design.md` — Plan 2 maps to spec sections §3 (architecture), §4 (manifest + battery), §5 (storage with BIDS), §6 (counterbalancing), §7 (sessions + state endpoints), §8 (CLI).

**Repo:** `/Users/lobennett/grants/r01_rdoc/projects/expdeploy/` (already cloned; main branch up to date with `github.com/lobennett/expdeploy`).

**Branching:** Work on a feature branch `feat/plan-2-storage-battery`. Each task commits to that branch. At the end of Plan 2, open a PR against `main`.

---

## Phase A — Bootstrap the feature branch + add ulid

### Task 1: Create feature branch + add python-ulid dep

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Create the branch**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/expdeploy
git checkout main
git pull
git checkout -b feat/plan-2-storage-battery
```

- [ ] **Step 2: Add `python-ulid` to `[project] dependencies`**

Open `pyproject.toml`. Inside `[project] dependencies = [ ... ]`, add a new line after `"rich>=13.7",`:

```toml
"python-ulid>=2.7",
```

(Keep the existing entries; just insert this one.)

- [ ] **Step 3: Sync + sanity-check**

```bash
uv sync --extra dev
uv run python -c "from ulid import ULID; print(ULID())"
```

Expected: prints a 26-character ULID like `01HXXXXX...`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "Add python-ulid dep for run identifiers"
```

---

## Phase B — Enrich the RunRecord model

### Task 2: Expand `RunRecord` with new fields; update tests

**Files:**
- Modify: `src/expdeploy/storage/base.py`
- Modify: `tests/unit/test_fs.py` (existing tests still need to construct valid `RunRecord`s)

- [ ] **Step 1: Update `tests/unit/test_fs.py` to pass the new fields**

In `tests/unit/test_fs.py`, find the `_record` helper. Replace it with the version below; do not change the call sites (the helper's defaults preserve existing test behavior):

```python
from datetime import UTC, datetime


def _record(
    exp_id: str = "hello",
    subject_id: str = "01",
    session_num: str | None = None,
    run_num: str | None = None,
    trials: list | None = None,
) -> RunRecord:
    return RunRecord(
        exp_id=exp_id,
        subject_id=subject_id,
        session_num=session_num,
        run_num=run_num,
        started_at=datetime(2026, 5, 15, 10, 0, 0, tzinfo=UTC),
        ended_at=datetime(2026, 5, 15, 10, 1, 0, tzinfo=UTC),
        status="finished",
        trials=(trials if trials is not None else [
            {"trial_type": "html-keyboard-response", "rt": 250},
        ]),
        raw_payload={"trials": trials if trials is not None else [
            {"trial_type": "html-keyboard-response", "rt": 250},
        ]},
    )
```

Also: in the test `test_save_with_session_and_run`, update the direct `RunRecord(...)` constructor call to include the new required fields (`started_at`, `ended_at`, `status`, `trials`). Use the same shape as `_record`.

- [ ] **Step 2: Run tests; they will fail because `RunRecord` doesn't yet accept the new fields**

```bash
uv run pytest tests/unit/test_fs.py -v
```

Expected: validation errors like `extra inputs are not permitted` (started_at, ended_at, status, trials).

- [ ] **Step 3: Update `src/expdeploy/storage/base.py`**

Replace the `RunRecord` class with the enriched version below. Keep `SaveResult` and `StorageAdapter` unchanged.

```python
"""Storage adapter protocol and common types."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field
from ulid import ULID


_LABEL_RE = re.compile(r"^[a-zA-Z0-9-]+$")

RunStatus = Literal["started", "finished", "aborted", "declined"]


def _new_run_id() -> str:
    return str(ULID())


class RunRecord(BaseModel):
    """One completed experiment run; what an adapter saves."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=_new_run_id, max_length=64)
    exp_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$", max_length=128)
    exp_version: str | None = None
    subject_id: str = Field(pattern=r"^[a-zA-Z0-9-]+$", max_length=64)
    session_num: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9-]+$", max_length=32)
    run_num: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9-]+$", max_length=32)
    battery_id: str | None = Field(default=None, max_length=64)
    group_index: int | None = Field(default=None, ge=0)
    started_at: datetime
    ended_at: datetime
    status: RunStatus
    trials: list[dict[str, Any]] = Field(default_factory=list)
    interaction_data: list[dict[str, Any]] = Field(default_factory=list)
    jspsych_version: str | None = None
    deploy_version: str | None = None
    client_user_agent: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SaveResult:
    ok: bool
    path: str
    error: str | None = None


@runtime_checkable
class StorageAdapter(Protocol):
    name: str

    def save(self, record: RunRecord) -> SaveResult: ...
```

- [ ] **Step 4: Run tests; they should pass**

```bash
uv run pytest tests/unit/test_fs.py -v
```

Expected: `5 passed`.

- [ ] **Step 5: Run *all* tests**

```bash
uv run pytest -v
```

Expected: some integration tests will fail because the FastAPI `app.py` constructs `RunRecord` with the OLD field set (no `started_at`/`ended_at`/`status`/`trials`). That's expected — Task 3 fixes the app. For now, just confirm only `tests/integration/test_app.py` fails and the rest pass.

- [ ] **Step 6: Commit**

```bash
git add src/expdeploy/storage/base.py tests/unit/test_fs.py
git commit -m "Enrich RunRecord with run_id, timestamps, status, group_index, battery_id"
```

---

### Task 3: Update FastAPI app to populate enriched RunRecord; update integration tests

**Files:**
- Modify: `src/expdeploy/app.py`
- Modify: `tests/integration/test_app.py`

- [ ] **Step 1: Update `test_post_data_writes_file` in `tests/integration/test_app.py`**

The test currently POSTs a payload with only `exp_id`, `subject_id`, `trials`, `status`. The handler needs to construct a `RunRecord` from this, supplying defaults for the new required fields (`started_at`, `ended_at`). Update the test to also assert the saved JSON contains `run_id`, `started_at`, `ended_at`:

```python
def test_post_data_writes_file(app_client):
    client, _data_dir = app_client
    payload = {
        "exp_id": "hello",
        "subject_id": "01",
        "trials": [{"trial_type": "html-keyboard-response", "rt": 432}],
        "status": "finished",
        "started_at": "2026-05-15T10:00:00+00:00",
        "ended_at": "2026-05-15T10:01:00+00:00",
    }
    response = client.post("/api/data", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    saved_path = Path(body["path"])
    assert saved_path.exists()
    saved = json.loads(saved_path.read_text())
    assert saved["trials"][0]["rt"] == 432
    assert saved["run_id"]  # ULID present
    assert saved["status"] == "finished"
```

Also update `test_post_data_rejects_invalid_subject` to include the required fields (the test expects a 422 — but now it could 422 for missing started_at/ended_at *before* the subject check. To keep the original intent, supply valid timestamps):

```python
def test_post_data_rejects_invalid_subject(app_client):
    client, _ = app_client
    payload = {
        "exp_id": "hello",
        "subject_id": "../oops",
        "trials": [],
        "status": "finished",
        "started_at": "2026-05-15T10:00:00+00:00",
        "ended_at": "2026-05-15T10:01:00+00:00",
    }
    response = client.post("/api/data", json=payload)
    assert response.status_code == 422
```

- [ ] **Step 2: Update `examples/hello_world/index.js` to send the new fields**

Find the `payload` object in `examples/hello_world/index.js`. Add `started_at` and `ended_at` fields:

```js
const startedAt = window.__expdeployStartTime || new Date().toISOString();
// ...
const payload = {
  exp_id: window.expdeploy.expId,
  subject_id: window.expdeploy.subjectId,
  session_num: window.expdeploy.sessionNum,
  run_num: window.expdeploy.runNum,
  deploy_version: window.expdeploy.deployVersion,
  started_at: startedAt,
  ended_at: new Date().toISOString(),
  trials: jsPsych.data.get().values(),
  status: "finished",
};
```

And at the top of `build()`, before `initJsPsych(...)`, add:

```js
window.__expdeployStartTime = new Date().toISOString();
```

- [ ] **Step 3: Update `src/expdeploy/app.py`**

The `post_data` handler currently does `RunRecord(exp_id=..., subject_id=..., raw_payload=payload)`. Update it to pass through the trial-level fields. Replace the body of `post_data`:

```python
@app.post("/api/data")
def post_data(payload: dict[str, Any]) -> JSONResponse:
    try:
        record = RunRecord(
            exp_id=payload.get("exp_id", exp_id),
            subject_id=payload.get("subject_id") or config.subject_id,
            session_num=payload.get("session_num") or config.session_num,
            run_num=payload.get("run_num") or config.run_num,
            started_at=payload["started_at"],
            ended_at=payload["ended_at"],
            status=payload.get("status", "finished"),
            trials=payload.get("trials", []),
            interaction_data=payload.get("interaction_data", []),
            jspsych_version=payload.get("jspsych_version"),
            deploy_version=payload.get("deploy_version"),
            client_user_agent=payload.get("client_user_agent"),
            raw_payload=payload,
        )
    except Exception as exc:  # Pydantic ValidationError or KeyError on missing started_at/ended_at
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = config.storage.save(record)
    if not result.ok:
        raise HTTPException(status_code=500, detail=result.error or "save failed")
    return JSONResponse({"ok": True, "path": result.path})
```

- [ ] **Step 4: Update `FSAdapter.save` to serialize the full record**

In `src/expdeploy/storage/fs.py`, find the `save` method. Replace its `payload` construction so it dumps the entire RunRecord, not just the `raw_payload`:

```python
def save(self, record: RunRecord) -> SaveResult:
    try:
        filename = self._make_filename(
            exp_id=record.exp_id,
            subject_id=record.subject_id,
            session_num=record.session_num,
            run_num=record.run_num,
        )
        subject_dir = self.data_dir / "raw" / f"sub-{record.subject_id}"
        if record.session_num is not None:
            subject_dir = subject_dir / f"ses-{record.session_num}"
        subject_dir.mkdir(parents=True, exist_ok=True)
        path = subject_dir / filename
        payload = {
            "saved_at_utc": datetime.now(UTC).isoformat(),
            **record.model_dump(mode="json"),
        }
        # Atomic write
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
        tmp.replace(path)
    except Exception as exc:  # noqa: BLE001
        return SaveResult(ok=False, path="", error=str(exc))
    return SaveResult(ok=True, path=str(path))
```

`model_dump(mode="json")` produces JSON-serializable output (datetimes become ISO strings, etc.).

- [ ] **Step 5: Update existing `test_save_writes_raw_json` to assert against the new structure**

In `tests/unit/test_fs.py`, the test currently does:
```python
payload = json.loads(saved.read_text())
assert payload["trials"][0]["rt"] == 250
```

The saved JSON now has the RunRecord schema flat-merged: `run_id`, `exp_id`, `subject_id`, `trials`, etc. The `trials` field still works because `_record` puts the trials list into `trials=`. Keep the assertion.

- [ ] **Step 6: Run all tests**

```bash
uv run pytest -v
```

Expected: 36 tests, all pass.

- [ ] **Step 7: Run the e2e to catch any browser-side regression**

```bash
uv run pytest tests/e2e -v -m e2e
```

Expected: `1 passed`. (The browser test sends real start/end times now from `index.js`.)

- [ ] **Step 8: Commit**

```bash
git add src/expdeploy/app.py src/expdeploy/storage/fs.py tests/integration/test_app.py tests/unit/test_fs.py examples/hello_world/index.js
git commit -m "Wire enriched RunRecord through app + adapter + hello-world example"
```

---

## Phase C — SQLite catalog

### Task 4: Add `SQLiteCatalog` adapter with schema migrations

**Files:**
- Create: `src/expdeploy/storage/sqlite.py`
- Create: `tests/unit/test_sqlite.py`

- [ ] **Step 1: Write the failing test `tests/unit/test_sqlite.py`**

```python
"""Tests for expdeploy.storage.sqlite.SQLiteCatalog."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from expdeploy.storage.base import RunRecord
from expdeploy.storage.sqlite import SQLiteCatalog


def _record(**overrides) -> RunRecord:
    fields = dict(
        exp_id="hello",
        subject_id="01",
        started_at=datetime(2026, 5, 15, 10, 0, 0, tzinfo=UTC),
        ended_at=datetime(2026, 5, 15, 10, 1, 0, tzinfo=UTC),
        status="finished",
        trials=[{"trial_type": "html-keyboard-response", "rt": 250}],
        jspsych_version="8.2.3",
        deploy_version="0.1.0a0",
    )
    fields.update(overrides)
    return RunRecord(**fields)


def test_init_creates_schema(tmp_path):
    catalog = SQLiteCatalog(db_path=tmp_path / "catalog.sqlite")
    catalog.init_schema()
    conn = sqlite3.connect(catalog.db_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"runs", "batteries", "remote_sync"} <= tables


def test_init_schema_is_idempotent(tmp_path):
    catalog = SQLiteCatalog(db_path=tmp_path / "catalog.sqlite")
    catalog.init_schema()
    catalog.init_schema()  # second call must not error
    conn = sqlite3.connect(catalog.db_path)
    n = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    conn.close()
    assert n == 0


def test_save_inserts_run(tmp_path):
    catalog = SQLiteCatalog(db_path=tmp_path / "catalog.sqlite")
    catalog.init_schema()
    result = catalog.save(_record(subject_id="01"))
    assert result.ok is True
    conn = sqlite3.connect(catalog.db_path)
    row = conn.execute(
        "SELECT run_id, exp_id, subject_id, status FROM runs WHERE subject_id='01'"
    ).fetchone()
    conn.close()
    assert row is not None
    run_id, exp_id, subject_id, status = row
    assert len(run_id) == 26  # ULID length
    assert exp_id == "hello"
    assert subject_id == "01"
    assert status == "finished"


def test_save_is_idempotent_on_same_run_id(tmp_path):
    catalog = SQLiteCatalog(db_path=tmp_path / "catalog.sqlite")
    catalog.init_schema()
    rec = _record()
    catalog.save(rec)
    catalog.save(rec)  # upsert on run_id; should not raise
    conn = sqlite3.connect(catalog.db_path)
    n = conn.execute("SELECT COUNT(*) FROM runs WHERE run_id=?", (rec.run_id,)).fetchone()[0]
    conn.close()
    assert n == 1


def test_recent_runs_returns_in_descending_order(tmp_path):
    catalog = SQLiteCatalog(db_path=tmp_path / "catalog.sqlite")
    catalog.init_schema()
    catalog.save(_record(subject_id="01", started_at=datetime(2026, 5, 14, tzinfo=UTC),
                          ended_at=datetime(2026, 5, 14, 0, 5, tzinfo=UTC)))
    catalog.save(_record(subject_id="02", started_at=datetime(2026, 5, 15, tzinfo=UTC),
                          ended_at=datetime(2026, 5, 15, 0, 5, tzinfo=UTC)))
    rows = catalog.recent_runs(limit=10)
    assert [r["subject_id"] for r in rows] == ["02", "01"]


def test_runs_for_subject_filters_correctly(tmp_path):
    catalog = SQLiteCatalog(db_path=tmp_path / "catalog.sqlite")
    catalog.init_schema()
    catalog.save(_record(subject_id="01"))
    catalog.save(_record(subject_id="02"))
    catalog.save(_record(subject_id="01"))
    rows = catalog.runs_for_subject("01")
    assert len(rows) == 2
    assert all(r["subject_id"] == "01" for r in rows)
```

- [ ] **Step 2: Run; expect ModuleNotFoundError**

```bash
uv run pytest tests/unit/test_sqlite.py -v
```

- [ ] **Step 3: Implement `src/expdeploy/storage/sqlite.py`**

```python
"""SQLite catalog adapter — always-on local index of runs."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from expdeploy.storage.base import RunRecord, SaveResult


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  exp_id TEXT NOT NULL,
  exp_version TEXT,
  subject_id TEXT NOT NULL,
  session_num TEXT,
  run_num TEXT,
  battery_id TEXT,
  group_index INTEGER,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  status TEXT NOT NULL,
  trials_json TEXT,
  interaction_data_json TEXT,
  jspsych_version TEXT,
  deploy_version TEXT,
  client_user_agent TEXT
);

CREATE TABLE IF NOT EXISTS batteries (
  battery_id TEXT PRIMARY KEY,
  name TEXT,
  manifest_hash TEXT,
  counterbalance TEXT,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS remote_sync (
  run_id TEXT REFERENCES runs(run_id),
  adapter TEXT NOT NULL,
  status TEXT NOT NULL,
  attempted_at TEXT,
  remote_uri TEXT,
  error TEXT,
  PRIMARY KEY (run_id, adapter)
);

CREATE INDEX IF NOT EXISTS idx_runs_subject ON runs(subject_id, session_num, run_num);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at);
CREATE INDEX IF NOT EXISTS idx_remote_sync_status ON remote_sync(status, adapter);
"""


class SQLiteCatalog:
    name = "sqlite"

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def save(self, record: RunRecord) -> SaveResult:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO runs (
                        run_id, exp_id, exp_version, subject_id, session_num, run_num,
                        battery_id, group_index, started_at, ended_at, status,
                        trials_json, interaction_data_json,
                        jspsych_version, deploy_version, client_user_agent
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        status = excluded.status,
                        ended_at = excluded.ended_at,
                        trials_json = excluded.trials_json,
                        interaction_data_json = excluded.interaction_data_json
                    """,
                    (
                        record.run_id,
                        record.exp_id,
                        record.exp_version,
                        record.subject_id,
                        record.session_num,
                        record.run_num,
                        record.battery_id,
                        record.group_index,
                        record.started_at.isoformat(),
                        record.ended_at.isoformat(),
                        record.status,
                        json.dumps(record.trials),
                        json.dumps(record.interaction_data),
                        record.jspsych_version,
                        record.deploy_version,
                        record.client_user_agent,
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            return SaveResult(ok=False, path=str(self.db_path), error=str(exc))
        return SaveResult(ok=True, path=str(self.db_path))

    def recent_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def runs_for_subject(self, subject_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs WHERE subject_id = ? ORDER BY started_at DESC",
                (subject_id,),
            ).fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 4: Run; expect all SQLite tests to pass**

```bash
uv run pytest tests/unit/test_sqlite.py -v
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/expdeploy/storage/sqlite.py tests/unit/test_sqlite.py
git commit -m "Add SQLiteCatalog adapter with schema migrations and query helpers"
```

---

## Phase D — BIDS-aware filesystem layout

### Task 5: Split `FSAdapter` into raw write + BIDS write; add `dataset_description.json` + `participants.tsv` writes

**Files:**
- Modify: `src/expdeploy/storage/fs.py`
- Modify: `tests/unit/test_fs.py` (add new BIDS-specific tests)

The plan adds three responsibilities to `FSAdapter`:
1. Always-on raw JSON write (existing behavior, keep working).
2. If the loaded experiment's manifest has a `[bids]` block, also write `events.tsv` + `events.json` sidecar under `bids/sub-X/[ses-Y/]{func,beh}/`.
3. Maintain `bids/dataset_description.json` (idempotent on first write) and `bids/participants.tsv` (append-on-first-encounter, file-locked).

`FSAdapter.save(record)` will continue to do the raw write. A new method `save_bids(record, manifest)` will be invoked separately by the app when the experiment has BIDS configured. We keep them separate so adapters that only do raw FS don't need BIDS logic.

- [ ] **Step 1: Add the failing tests to `tests/unit/test_fs.py`**

Append these tests (also add `from expdeploy.manifest import ExperimentManifest` and `import tomllib` to the imports if not already there):

```python
import tomllib

from expdeploy.manifest import ExperimentManifest


BIDS_FMRI_MANIFEST = """
[experiment]
exp_id = "flanker"
name = "Flanker"
version = "1.0.0"
entry = "index.js"

[jspsych]
version = "8.2.3"
plugins = []

[bids]
type = "fmri"
task = "flanker"

[bids.columns.trial_type]
description = "Congruency of flanker."
levels = { congruent = "Congruent", incongruent = "Incongruent" }
"""


def _bids_manifest() -> ExperimentManifest:
    return ExperimentManifest.model_validate(tomllib.loads(BIDS_FMRI_MANIFEST))


def test_save_bids_writes_events_tsv(tmp_path):
    adapter = FSAdapter(data_dir=tmp_path)
    record = _record(
        exp_id="flanker",
        subject_id="01",
        session_num="1",
        run_num="1",
        trials=[
            {"trial_type": "congruent", "rt": 412, "onset": 1.5, "duration": 0.8},
            {"trial_type": "incongruent", "rt": 489, "onset": 3.2, "duration": 0.8},
        ],
    )
    result = adapter.save_bids(record, _bids_manifest())
    assert result.ok is True
    events_path = Path(result.path)
    assert events_path.name == "sub-01_ses-1_task-flanker_run-1_events.tsv"
    assert events_path.parent.parts[-1] == "func"
    content = events_path.read_text()
    # Header + 2 rows
    assert content.startswith("onset\tduration\ttrial_type")
    assert "congruent" in content
    assert "incongruent" in content


def test_save_bids_writes_json_sidecar(tmp_path):
    adapter = FSAdapter(data_dir=tmp_path)
    record = _record(
        exp_id="flanker",
        subject_id="01",
        trials=[{"trial_type": "congruent", "rt": 412, "onset": 1.5, "duration": 0.8}],
    )
    adapter.save_bids(record, _bids_manifest())
    sidecar = tmp_path / "bids" / "sub-01" / "func" / "sub-01_task-flanker_events.json"
    assert sidecar.exists()
    data = json.loads(sidecar.read_text())
    assert data["trial_type"]["description"] == "Congruency of flanker."
    assert data["trial_type"]["Levels"]["congruent"] == "Congruent"


def test_save_bids_writes_dataset_description(tmp_path):
    adapter = FSAdapter(data_dir=tmp_path)
    record = _record(exp_id="flanker", subject_id="01")
    adapter.save_bids(record, _bids_manifest())
    dd = tmp_path / "bids" / "dataset_description.json"
    assert dd.exists()
    data = json.loads(dd.read_text())
    assert data["BIDSVersion"] == "1.9.0"
    assert data["DatasetType"] == "raw"


def test_save_bids_appends_participants_tsv(tmp_path):
    adapter = FSAdapter(data_dir=tmp_path)
    adapter.save_bids(_record(subject_id="01"), _bids_manifest())
    adapter.save_bids(_record(subject_id="02"), _bids_manifest())
    adapter.save_bids(_record(subject_id="01"), _bids_manifest())  # duplicate
    p = tmp_path / "bids" / "participants.tsv"
    lines = p.read_text().strip().split("\n")
    # Header + 2 unique subjects
    assert lines[0].startswith("participant_id")
    rows = lines[1:]
    assert sorted(rows) == ["sub-01", "sub-02"]


def test_save_bids_behavioral_uses_beh_dir(tmp_path):
    behavioral_manifest = ExperimentManifest.model_validate(
        tomllib.loads(BIDS_FMRI_MANIFEST.replace('type = "fmri"', 'type = "behavioral"'))
    )
    adapter = FSAdapter(data_dir=tmp_path)
    record = _record(
        exp_id="flanker",
        subject_id="01",
        session_num="1",
        run_num="1",
        trials=[{"trial_type": "congruent", "rt": 412}],
    )
    result = adapter.save_bids(record, behavioral_manifest)
    events_path = Path(result.path)
    assert events_path.parent.parts[-1] == "beh"
    assert events_path.name.endswith("_beh.tsv")
```

- [ ] **Step 2: Run; expect failures (no `save_bids` method)**

```bash
uv run pytest tests/unit/test_fs.py -v
```

- [ ] **Step 3: Update `src/expdeploy/storage/fs.py`**

Add the `save_bids` method + helpers. The full new file:

```python
"""Filesystem storage adapter — raw JSON always; BIDS layout when manifest declares it."""

from __future__ import annotations

import csv
import json
import re
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any

from filelock import FileLock

from expdeploy.manifest import BidsConfig, ExperimentManifest
from expdeploy.storage.base import RunRecord, SaveResult


_LABEL_RE = re.compile(r"^[a-zA-Z0-9-]+$")
BIDS_VERSION = "1.9.0"


class FSAdapter:
    """Saves raw run JSON to disk; optionally writes a BIDS-flavored mirror."""

    name = "fs"

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir).resolve()

    # ---- raw JSON write (unchanged from Plan 1) -------------------------------

    @staticmethod
    def _validate(field: str, value: str | None) -> None:
        if value is not None and not _LABEL_RE.match(value):
            msg = f"{field} {value!r} must match {_LABEL_RE.pattern}"
            raise ValueError(msg)

    @classmethod
    def _make_filename(
        cls,
        *,
        exp_id: str,
        subject_id: str,
        session_num: str | None,
        run_num: str | None,
        suffix: str = "_beh",
        ext: str = ".json",
    ) -> str:
        cls._validate("exp_id", exp_id)
        cls._validate("subject_id", subject_id)
        cls._validate("session_num", session_num)
        cls._validate("run_num", run_num)
        parts = [f"sub-{subject_id}"]
        if session_num is not None:
            parts.append(f"ses-{session_num}")
        parts.append(f"task-{exp_id}")
        if run_num is not None:
            parts.append(f"run-{run_num}")
        return "_".join(parts) + suffix + ext

    def save(self, record: RunRecord) -> SaveResult:
        try:
            filename = self._make_filename(
                exp_id=record.exp_id,
                subject_id=record.subject_id,
                session_num=record.session_num,
                run_num=record.run_num,
            )
            subject_dir = self.data_dir / "raw" / f"sub-{record.subject_id}"
            if record.session_num is not None:
                subject_dir = subject_dir / f"ses-{record.session_num}"
            subject_dir.mkdir(parents=True, exist_ok=True)
            path = subject_dir / filename
            payload = {
                "saved_at_utc": datetime.now(UTC).isoformat(),
                **record.model_dump(mode="json"),
            }
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
            tmp.replace(path)
        except Exception as exc:  # noqa: BLE001
            return SaveResult(ok=False, path="", error=str(exc))
        return SaveResult(ok=True, path=str(path))

    # ---- BIDS layout writes ---------------------------------------------------

    def save_bids(self, record: RunRecord, manifest: ExperimentManifest) -> SaveResult:
        if manifest.bids is None:
            return SaveResult(ok=False, path="", error="manifest has no [bids] block")
        try:
            bids_root = self.data_dir / "bids"
            bids_root.mkdir(parents=True, exist_ok=True)
            self._ensure_dataset_description(bids_root, manifest)
            self._append_participant(bids_root, record.subject_id)
            events_path = self._write_events_tsv(bids_root, record, manifest.bids)
            self._write_events_sidecar(bids_root, record, manifest.bids)
        except Exception as exc:  # noqa: BLE001
            return SaveResult(ok=False, path="", error=str(exc))
        return SaveResult(ok=True, path=str(events_path))

    def _ensure_dataset_description(
        self, bids_root: Path, manifest: ExperimentManifest
    ) -> None:
        path = bids_root / "dataset_description.json"
        if path.exists():
            return
        dd = {
            "Name": manifest.experiment.name,
            "BIDSVersion": BIDS_VERSION,
            "DatasetType": "raw",
            "Authors": list(manifest.experiment.metadata.contributors),
        }
        path.write_text(json.dumps(dd, indent=2, sort_keys=True) + "\n")

    def _append_participant(self, bids_root: Path, subject_id: str) -> None:
        path = bids_root / "participants.tsv"
        lock = FileLock(str(path) + ".lock")
        participant = f"sub-{subject_id}"
        with lock:
            existing: list[str] = []
            if path.exists():
                existing = path.read_text().splitlines()
            header_present = bool(existing) and existing[0].startswith("participant_id")
            rows_existing = set(existing[1:]) if header_present else set(existing)
            if participant in rows_existing:
                return
            with path.open("a") as f:
                if not header_present:
                    f.write("participant_id\n")
                f.write(participant + "\n")

    def _events_dir_for(self, bids_root: Path, record: RunRecord, bids: BidsConfig) -> Path:
        subject_dir = bids_root / f"sub-{record.subject_id}"
        if record.session_num is not None:
            subject_dir = subject_dir / f"ses-{record.session_num}"
        modality = "func" if bids.type == "fmri" else "beh"
        events_dir = subject_dir / modality
        events_dir.mkdir(parents=True, exist_ok=True)
        return events_dir

    def _write_events_tsv(
        self, bids_root: Path, record: RunRecord, bids: BidsConfig
    ) -> Path:
        events_dir = self._events_dir_for(bids_root, record, bids)
        suffix = "_events" if bids.type == "fmri" else "_beh"
        ext = ".tsv"
        filename = self._make_filename(
            exp_id=record.exp_id,
            subject_id=record.subject_id,
            session_num=record.session_num,
            run_num=record.run_num,
            suffix=suffix,
            ext=ext,
        )
        path = events_dir / filename

        # BIDS-mandated columns first; remaining trial columns appended
        bids_cols = ["onset", "duration", "trial_type"]
        all_cols: list[str] = list(bids_cols)
        for trial in record.trials:
            for k in trial.keys():
                if k not in all_cols:
                    all_cols.append(k)

        buf = StringIO()
        writer = csv.DictWriter(buf, fieldnames=all_cols, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for trial in record.trials:
            row = {col: trial.get(col, "n/a") for col in all_cols}
            writer.writerow(row)
        path.write_text(buf.getvalue())
        return path

    def _write_events_sidecar(
        self, bids_root: Path, record: RunRecord, bids: BidsConfig
    ) -> None:
        if not bids.columns:
            return
        events_dir = self._events_dir_for(bids_root, record, bids)
        suffix = "_events" if bids.type == "fmri" else "_beh"
        filename = self._make_filename(
            exp_id=record.exp_id,
            subject_id=record.subject_id,
            session_num=record.session_num,
            run_num=None,  # sidecar is per-task, not per-run
            suffix=suffix,
            ext=".json",
        )
        path = events_dir / filename
        if path.exists():
            return  # sidecar is task-level; first writer wins
        sidecar: dict[str, Any] = {}
        for col_name, col in bids.columns.items():
            sidecar[col_name] = {
                "Description": col.description,
            }
            if col.levels:
                sidecar[col_name]["Levels"] = dict(col.levels)
        path.write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n")
```

- [ ] **Step 4: Run all tests**

```bash
uv run pytest -v
```

Expected: 36 + new tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/expdeploy/storage/fs.py tests/unit/test_fs.py
git commit -m "Add BIDS layout writes: events.tsv, sidecar, dataset_description, participants"
```

---

## Phase E — Counterbalance strategies

### Task 6: Add `CounterbalanceStrategy` Protocol + Fixed + LatinSquare strategies

**Files:**
- Create: `src/expdeploy/battery/__init__.py` (empty)
- Create: `src/expdeploy/battery/counterbalance.py`
- Create: `tests/unit/test_counterbalance.py`

- [ ] **Step 1: Write `tests/unit/test_counterbalance.py`**

```python
"""Tests for expdeploy.battery.counterbalance — 4 strategies."""

from __future__ import annotations

import pytest

from expdeploy.battery.counterbalance import (
    FixedStrategy,
    LatinSquareStrategy,
)


EXPS = ["flanker", "stroop", "nback"]


def test_fixed_returns_input_verbatim():
    s = FixedStrategy()
    assert s.order_for("01", EXPS) == EXPS
    assert s.order_for("any", EXPS) == EXPS


def test_fixed_does_not_mutate_input():
    s = FixedStrategy()
    out = s.order_for("01", EXPS)
    out.append("extra")
    assert EXPS == ["flanker", "stroop", "nback"]


def test_latin_square_rotates_by_subject():
    s = LatinSquareStrategy()
    o0 = s.order_for("0", EXPS)
    o1 = s.order_for("1", EXPS)
    o2 = s.order_for("2", EXPS)
    # First experiment must differ across rows
    firsts = {o0[0], o1[0], o2[0]}
    assert len(firsts) == 3  # all unique


def test_latin_square_is_deterministic():
    s = LatinSquareStrategy()
    a = s.order_for("5", EXPS)
    b = s.order_for("5", EXPS)
    assert a == b


def test_latin_square_wraps_at_k():
    s = LatinSquareStrategy()
    # Subject K and subject 0 should match (modulo K)
    a = s.order_for("0", EXPS)
    b = s.order_for(str(len(EXPS)), EXPS)
    assert a == b


def test_latin_square_rejects_non_int_subject():
    s = LatinSquareStrategy()
    with pytest.raises(ValueError):
        s.order_for("pilot_a", EXPS)


def test_strategy_name_attr_present():
    assert FixedStrategy().name == "fixed"
    assert LatinSquareStrategy().name == "latin_square"
```

- [ ] **Step 2: Run; expect import error**

```bash
uv run pytest tests/unit/test_counterbalance.py -v
```

- [ ] **Step 3: Write `src/expdeploy/battery/counterbalance.py`**

```python
"""Counterbalance strategies — 4 implementations of CounterbalanceStrategy."""

from __future__ import annotations

import csv
import random
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class CounterbalanceStrategy(Protocol):
    name: str

    def order_for(self, subject_id: str, experiments: list[str]) -> list[str]: ...


class FixedStrategy:
    name = "fixed"

    def order_for(self, subject_id: str, experiments: list[str]) -> list[str]:
        return list(experiments)


class LatinSquareStrategy:
    """Balanced K×K Latin square; subject row = int(subject_id) mod K."""

    name = "latin_square"

    def order_for(self, subject_id: str, experiments: list[str]) -> list[str]:
        try:
            n = int(subject_id)
        except ValueError as exc:
            msg = (
                f"latin_square requires integer-parseable subject_id; got {subject_id!r}"
            )
            raise ValueError(msg) from exc
        k = len(experiments)
        row = n % k
        # Williams-style Latin square: position j of row i = (i + j) mod K
        return [experiments[(row + j) % k] for j in range(k)]


class SeededRandomStrategy:
    """Per-subject deterministic shuffle. Seed derived from subject_id."""

    name = "seeded_random"

    def order_for(self, subject_id: str, experiments: list[str]) -> list[str]:
        rng = random.Random(subject_id)  # noqa: S311 — not security-sensitive
        out = list(experiments)
        rng.shuffle(out)
        return out


class UserSuppliedStrategy:
    """Reads order_csv; rows are subject_id, pos_1, pos_2, ..."""

    name = "user_supplied"

    def __init__(self, order_csv: Path) -> None:
        self.order_csv = Path(order_csv)
        self._cache: dict[str, list[str]] | None = None

    def _load(self) -> dict[str, list[str]]:
        if self._cache is not None:
            return self._cache
        out: dict[str, list[str]] = {}
        with self.order_csv.open() as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header is None or len(header) < 2:
                msg = f"order_csv {self.order_csv} missing header / columns"
                raise ValueError(msg)
            for row in reader:
                if not row:
                    continue
                subject = row[0]
                out[subject] = [c for c in row[1:] if c]
        self._cache = out
        return out

    def order_for(self, subject_id: str, experiments: list[str]) -> list[str]:
        loaded = self._load()
        if subject_id not in loaded:
            msg = f"subject_id {subject_id!r} not in {self.order_csv}"
            raise KeyError(msg)
        return loaded[subject_id]
```

- [ ] **Step 4: Run; expect 7 passed for Fixed + LatinSquare tests; SeededRandom + UserSupplied tests come in Task 7**

```bash
uv run pytest tests/unit/test_counterbalance.py -v
```

Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/expdeploy/battery/ tests/unit/test_counterbalance.py
git commit -m "Add CounterbalanceStrategy Protocol + Fixed + LatinSquare strategies"
```

---

### Task 7: Add SeededRandom + UserSupplied strategy tests

**Files:**
- Modify: `tests/unit/test_counterbalance.py`

- [ ] **Step 1: Append new tests**

```python
from expdeploy.battery.counterbalance import SeededRandomStrategy, UserSuppliedStrategy


def test_seeded_random_is_deterministic_per_subject():
    s = SeededRandomStrategy()
    assert s.order_for("01", EXPS) == s.order_for("01", EXPS)


def test_seeded_random_differs_across_subjects():
    s = SeededRandomStrategy()
    orders = {tuple(s.order_for(sid, EXPS)) for sid in ["01", "02", "03", "04", "05", "06"]}
    # Most subjects should get distinct orders; collision is possible but unlikely
    assert len(orders) >= 2


def test_user_supplied_returns_csv_row(tmp_path):
    csv_path = tmp_path / "orders.csv"
    csv_path.write_text(
        "subject_id,pos_1,pos_2,pos_3\n"
        "01,nback,flanker,stroop\n"
        "02,stroop,nback,flanker\n"
    )
    s = UserSuppliedStrategy(order_csv=csv_path)
    assert s.order_for("01", EXPS) == ["nback", "flanker", "stroop"]
    assert s.order_for("02", EXPS) == ["stroop", "nback", "flanker"]


def test_user_supplied_missing_subject_raises(tmp_path):
    csv_path = tmp_path / "orders.csv"
    csv_path.write_text("subject_id,pos_1\n01,nback\n")
    s = UserSuppliedStrategy(order_csv=csv_path)
    with pytest.raises(KeyError):
        s.order_for("99", EXPS)
```

- [ ] **Step 2: Run; expect 11 passed total**

```bash
uv run pytest tests/unit/test_counterbalance.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_counterbalance.py
git commit -m "Add SeededRandom + UserSupplied counterbalance strategy tests"
```

---

## Phase F — Battery manifest

### Task 8: Add `BatteryManifest` Pydantic model + `load_battery`

**Files:**
- Modify: `src/expdeploy/manifest.py`
- Create: `tests/unit/test_battery_manifest.py`

- [ ] **Step 1: Write `tests/unit/test_battery_manifest.py`**

```python
"""Tests for the BatteryManifest Pydantic model + load_battery."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from expdeploy.manifest import BatteryManifest, load_battery


BATTERY_TOML = """
[battery]
name = "RDoC mini battery"
counterbalance = "latin_square"

[[experiments]]
exp_id = "flanker"
path = "./flanker"

[[experiments]]
exp_id = "stroop"
path = "./stroop"

[breaks]
between_each = { duration_seconds = 30, message = "Rest." }
"""


def test_battery_manifest_parses():
    data = tomllib.loads(BATTERY_TOML)
    m = BatteryManifest.model_validate(data)
    assert m.battery.name == "RDoC mini battery"
    assert m.battery.counterbalance == "latin_square"
    assert len(m.experiments) == 2
    assert m.experiments[0].exp_id == "flanker"
    assert m.experiments[0].path == "./flanker"
    assert m.breaks is not None
    assert m.breaks.between_each.duration_seconds == 30


def test_battery_rejects_unknown_counterbalance():
    bad = BATTERY_TOML.replace('"latin_square"', '"random"')
    with pytest.raises(Exception):
        BatteryManifest.model_validate(tomllib.loads(bad))


def test_load_battery_from_disk(tmp_path):
    p = tmp_path / "battery.toml"
    p.write_text(BATTERY_TOML)
    m = load_battery(p)
    assert m.battery.counterbalance == "latin_square"


def test_load_battery_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_battery(tmp_path / "nope.toml")
```

- [ ] **Step 2: Run; expect ImportError on BatteryManifest**

```bash
uv run pytest tests/unit/test_battery_manifest.py -v
```

- [ ] **Step 3: Extend `src/expdeploy/manifest.py`**

Append to the existing file (after `load_manifest`):

```python
from typing import Literal


CounterbalanceName = Literal["fixed", "latin_square", "seeded_random", "user_supplied"]


class BatteryBreakConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_seconds: int = Field(ge=0)
    message: str = ""


class BatteryBreaks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    between_each: BatteryBreakConfig | None = None


class BatteryInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    counterbalance: CounterbalanceName = "fixed"
    order_csv: str | None = None


class BatteryExperimentRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exp_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$", max_length=128)
    path: str


class BatteryManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    battery: BatteryInfo
    experiments: list[BatteryExperimentRef]
    breaks: BatteryBreaks | None = None


def load_battery(path: Path) -> BatteryManifest:
    """Read a battery.toml from disk and return a validated BatteryManifest."""
    with path.open("rb") as fp:
        data = tomllib.load(fp)
    return BatteryManifest.model_validate(data)
```

- [ ] **Step 4: Run; expect 4 passed**

```bash
uv run pytest tests/unit/test_battery_manifest.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/expdeploy/manifest.py tests/unit/test_battery_manifest.py
git commit -m "Add BatteryManifest + load_battery"
```

---

## Phase G — Run session

### Task 9: Add file-locked `RunSession` per-subject state

**Files:**
- Create: `src/expdeploy/session.py`
- Create: `tests/unit/test_session.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for expdeploy.session.RunSession."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from expdeploy.session import RunSession


def test_initialize_writes_state(tmp_path):
    s = RunSession(state_dir=tmp_path, subject_id="01")
    s.initialize(battery_id="battery-abc", order=["flanker", "stroop", "nback"])
    p = tmp_path / "sub-01.json"
    assert p.exists()
    data = json.loads(p.read_text())
    assert data["subject_id"] == "01"
    assert data["battery_id"] == "battery-abc"
    assert data["order"] == ["flanker", "stroop", "nback"]
    assert data["completed"] == []


def test_current_returns_next_incomplete(tmp_path):
    s = RunSession(state_dir=tmp_path, subject_id="01")
    s.initialize(battery_id="b", order=["flanker", "stroop"])
    assert s.current() == "flanker"


def test_advance_marks_completed_and_advances(tmp_path):
    s = RunSession(state_dir=tmp_path, subject_id="01")
    s.initialize(battery_id="b", order=["flanker", "stroop"])
    s.advance()
    assert s.current() == "stroop"


def test_current_returns_none_when_complete(tmp_path):
    s = RunSession(state_dir=tmp_path, subject_id="01")
    s.initialize(battery_id="b", order=["flanker"])
    s.advance()
    assert s.current() is None


def test_reset_clears_state(tmp_path):
    s = RunSession(state_dir=tmp_path, subject_id="01")
    s.initialize(battery_id="b", order=["flanker", "stroop"])
    s.advance()
    s.reset()
    # After reset, initialize() must be called again
    with pytest.raises(RuntimeError):
        s.current()


def test_initialize_is_idempotent_for_same_battery(tmp_path):
    s = RunSession(state_dir=tmp_path, subject_id="01")
    s.initialize(battery_id="b", order=["flanker", "stroop"])
    s.advance()
    # Re-initialize with same battery_id; order/progress preserved
    s.initialize(battery_id="b", order=["flanker", "stroop"])
    assert s.current() == "stroop"
    assert s.completed() == ["flanker"]


def test_initialize_resets_on_different_battery(tmp_path):
    s = RunSession(state_dir=tmp_path, subject_id="01")
    s.initialize(battery_id="b1", order=["flanker", "stroop"])
    s.advance()
    s.initialize(battery_id="b2", order=["flanker", "nback"])
    assert s.current() == "flanker"
    assert s.completed() == []
```

- [ ] **Step 2: Run; expect ModuleNotFoundError**

```bash
uv run pytest tests/unit/test_session.py -v
```

- [ ] **Step 3: Write `src/expdeploy/session.py`**

```python
"""File-locked per-subject run session state."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from filelock import FileLock


class RunSession:
    """Tracks one subject's progress through a battery.

    State is persisted to `state_dir/sub-<subject_id>.json` and protected by
    a file lock so concurrent web requests can't race.
    """

    def __init__(self, state_dir: Path, subject_id: str) -> None:
        self.state_dir = Path(state_dir).resolve()
        self.subject_id = subject_id
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._path = self.state_dir / f"sub-{subject_id}.json"
        self._lock = FileLock(str(self._path) + ".lock")

    def _read(self) -> dict | None:
        if not self._path.exists():
            return None
        return json.loads(self._path.read_text())

    def _write(self, state: dict) -> None:
        fd, tmpname = tempfile.mkstemp(prefix=f"sub-{self.subject_id}-", dir=str(self.state_dir))
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f, indent=2, sort_keys=True)
            os.replace(tmpname, self._path)
        except Exception:
            if os.path.exists(tmpname):
                os.unlink(tmpname)
            raise

    def initialize(self, *, battery_id: str, order: list[str]) -> None:
        """Create state if missing, or preserve if same battery_id; reset otherwise."""
        with self._lock:
            existing = self._read()
            if existing is not None and existing.get("battery_id") == battery_id:
                return  # preserve progress
            state = {
                "subject_id": self.subject_id,
                "battery_id": battery_id,
                "order": list(order),
                "completed": [],
            }
            self._write(state)

    def current(self) -> str | None:
        with self._lock:
            state = self._read()
            if state is None:
                msg = f"session not initialized for sub-{self.subject_id}"
                raise RuntimeError(msg)
            remaining = [e for e in state["order"] if e not in state["completed"]]
            return remaining[0] if remaining else None

    def advance(self) -> None:
        with self._lock:
            state = self._read()
            if state is None:
                msg = f"session not initialized for sub-{self.subject_id}"
                raise RuntimeError(msg)
            remaining = [e for e in state["order"] if e not in state["completed"]]
            if not remaining:
                return
            state["completed"].append(remaining[0])
            self._write(state)

    def completed(self) -> list[str]:
        with self._lock:
            state = self._read()
            if state is None:
                return []
            return list(state["completed"])

    def reset(self) -> None:
        with self._lock:
            if self._path.exists():
                self._path.unlink()
```

- [ ] **Step 4: Run; expect 7 passed**

```bash
uv run pytest tests/unit/test_session.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/expdeploy/session.py tests/unit/test_session.py
git commit -m "Add file-locked RunSession for per-subject battery state"
```

---

## Phase H — Battery orchestrator

### Task 10: Add `BatteryOrchestrator`

**Files:**
- Create: `src/expdeploy/battery/orchestrator.py`
- Create: `tests/unit/test_battery_orchestrator.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for expdeploy.battery.orchestrator.BatteryOrchestrator."""

from __future__ import annotations

import hashlib

import pytest

from expdeploy.battery.counterbalance import FixedStrategy, LatinSquareStrategy
from expdeploy.battery.orchestrator import BatteryOrchestrator
from expdeploy.manifest import BatteryInfo, BatteryManifest, BatteryExperimentRef
from expdeploy.session import RunSession


def _battery(experiments: list[str], counterbalance: str = "fixed") -> BatteryManifest:
    return BatteryManifest(
        battery=BatteryInfo(name="b", counterbalance=counterbalance),  # type: ignore[arg-type]
        experiments=[
            BatteryExperimentRef(exp_id=e, path=f"./{e}") for e in experiments
        ],
    )


def test_orchestrator_returns_first_in_order(tmp_path):
    session = RunSession(state_dir=tmp_path, subject_id="01")
    o = BatteryOrchestrator(
        manifest=_battery(["flanker", "stroop", "nback"]),
        strategy=FixedStrategy(),
        session=session,
    )
    o.start()
    assert o.next_experiment().exp_id == "flanker"


def test_orchestrator_advances_through_battery(tmp_path):
    session = RunSession(state_dir=tmp_path, subject_id="01")
    o = BatteryOrchestrator(
        manifest=_battery(["flanker", "stroop"]),
        strategy=FixedStrategy(),
        session=session,
    )
    o.start()
    assert o.next_experiment().exp_id == "flanker"
    o.advance()
    assert o.next_experiment().exp_id == "stroop"
    o.advance()
    assert o.next_experiment() is None


def test_orchestrator_uses_strategy_for_order(tmp_path):
    session = RunSession(state_dir=tmp_path, subject_id="1")  # row 1 of latin square
    o = BatteryOrchestrator(
        manifest=_battery(["flanker", "stroop", "nback"]),
        strategy=LatinSquareStrategy(),
        session=session,
    )
    o.start()
    # Row 1 of Williams square: (1+j) mod 3 → stroop, nback, flanker
    assert o.next_experiment().exp_id == "stroop"


def test_orchestrator_battery_id_is_stable(tmp_path):
    m = _battery(["flanker", "stroop"])
    session = RunSession(state_dir=tmp_path, subject_id="01")
    o = BatteryOrchestrator(manifest=m, strategy=FixedStrategy(), session=session)
    o.start()
    bid_1 = o.battery_id
    o2 = BatteryOrchestrator(manifest=m, strategy=FixedStrategy(), session=RunSession(state_dir=tmp_path, subject_id="02"))
    o2.start()
    assert bid_1 == o2.battery_id  # battery_id is hash of manifest, not subject-specific
```

- [ ] **Step 2: Run; expect ModuleNotFoundError**

```bash
uv run pytest tests/unit/test_battery_orchestrator.py -v
```

- [ ] **Step 3: Write `src/expdeploy/battery/orchestrator.py`**

```python
"""BatteryOrchestrator — ties manifest + strategy + session."""

from __future__ import annotations

import hashlib
import json

from expdeploy.battery.counterbalance import CounterbalanceStrategy
from expdeploy.manifest import BatteryExperimentRef, BatteryManifest
from expdeploy.session import RunSession


class BatteryOrchestrator:
    def __init__(
        self,
        *,
        manifest: BatteryManifest,
        strategy: CounterbalanceStrategy,
        session: RunSession,
    ) -> None:
        self.manifest = manifest
        self.strategy = strategy
        self.session = session

    @property
    def battery_id(self) -> str:
        """Stable id derived from the manifest. Subject-independent."""
        payload = self.manifest.model_dump(mode="json")
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return digest[:16]

    def start(self) -> None:
        experiments_by_id = {e.exp_id: e for e in self.manifest.experiments}
        order = self.strategy.order_for(
            self.session.subject_id, list(experiments_by_id.keys())
        )
        self.session.initialize(battery_id=self.battery_id, order=order)

    def next_experiment(self) -> BatteryExperimentRef | None:
        current_id = self.session.current()
        if current_id is None:
            return None
        for e in self.manifest.experiments:
            if e.exp_id == current_id:
                return e
        msg = f"current experiment {current_id!r} not in manifest"
        raise LookupError(msg)

    def advance(self) -> None:
        self.session.advance()
```

- [ ] **Step 4: Run; expect 4 passed**

```bash
uv run pytest tests/unit/test_battery_orchestrator.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/expdeploy/battery/orchestrator.py tests/unit/test_battery_orchestrator.py
git commit -m "Add BatteryOrchestrator (manifest + strategy + session)"
```

---

## Phase I — App integration

### Task 11: Update FastAPI app to use BatteryOrchestrator; add /api/state endpoints

**Files:**
- Modify: `src/expdeploy/app.py`
- Modify: `tests/integration/test_app.py` (current single-experiment tests must still pass)

- [ ] **Step 1: Sketch the new `AppConfig`**

The new `AppConfig` carries either a single experiment OR a battery. Replace:

```python
@dataclass(frozen=True, slots=True)
class AppConfig:
    experiment: LoadedExperiment
    vendored_root: Path
    storage: StorageAdapter
    subject_id: str
    session_num: str | None
    run_num: str | None
```

with:

```python
@dataclass(frozen=True, slots=True)
class AppConfig:
    """A single-experiment OR battery deployment config.

    Exactly one of `experiment` or `(battery_manifest, experiments_by_id)` is set.
    """

    vendored_root: Path
    storage: StorageAdapter            # primary always-on (FSAdapter)
    catalog: StorageAdapter | None     # SQLiteCatalog or None
    state_dir: Path                    # for RunSession
    subject_id: str
    session_num: str | None
    run_num: str | None

    # Single-experiment mode
    experiment: LoadedExperiment | None = None

    # Battery mode
    battery_manifest: BatteryManifest | None = None
    experiments_by_id: dict[str, LoadedExperiment] | None = None
    counterbalance_strategy: CounterbalanceStrategy | None = None

    def is_battery(self) -> bool:
        return self.battery_manifest is not None
```

- [ ] **Step 2: Write new tests covering battery mode**

Add to `tests/integration/test_app.py`:

```python
from expdeploy.battery.counterbalance import FixedStrategy
from expdeploy.manifest import BatteryExperimentRef, BatteryInfo, BatteryManifest
from expdeploy.storage.sqlite import SQLiteCatalog


def _two_exp_battery(tmp_path):
    """Build a fixture with two minimal experiments and a battery manifest."""
    exp_a = tmp_path / "ea"
    exp_a.mkdir()
    (exp_a / "manifest.toml").write_text(HELLO_TOML.replace('exp_id = "hello"', 'exp_id = "ea"'))
    (exp_a / "index.js").write_text("export default () => {};")

    exp_b = tmp_path / "eb"
    exp_b.mkdir()
    (exp_b / "manifest.toml").write_text(HELLO_TOML.replace('exp_id = "hello"', 'exp_id = "eb"'))
    (exp_b / "index.js").write_text("export default () => {};")

    battery = BatteryManifest(
        battery=BatteryInfo(name="t", counterbalance="fixed"),
        experiments=[
            BatteryExperimentRef(exp_id="ea", path=str(exp_a)),
            BatteryExperimentRef(exp_id="eb", path=str(exp_b)),
        ],
    )
    return battery, {"ea": ExperimentLoader().load(exp_a), "eb": ExperimentLoader().load(exp_b)}


@pytest.fixture
def battery_client(tmp_path):
    battery, exps = _two_exp_battery(tmp_path)
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
        battery_manifest=battery,
        experiments_by_id=exps,
        counterbalance_strategy=FixedStrategy(),
    )
    app = create_app(config)
    return TestClient(app), data_dir, catalog


def test_battery_get_root_serves_first_experiment(battery_client):
    client, _, _ = battery_client
    response = client.get("/")
    assert response.status_code == 200
    assert "/static/exp/ea/" in response.text


def test_battery_state_endpoint(battery_client):
    client, _, _ = battery_client
    r = client.get("/api/state")
    body = r.json()
    assert body["current"] == "ea"
    assert body["completed"] == []
    assert body["order"] == ["ea", "eb"]


def test_battery_post_data_advances(battery_client):
    client, data_dir, catalog = battery_client
    payload = {
        "exp_id": "ea",
        "subject_id": "01",
        "trials": [],
        "status": "finished",
        "started_at": "2026-05-15T10:00:00+00:00",
        "ended_at": "2026-05-15T10:01:00+00:00",
    }
    r = client.post("/api/data", json=payload)
    assert r.status_code == 200
    # State advanced
    r2 = client.get("/api/state")
    assert r2.json()["current"] == "eb"
    # SQLite has a row
    rows = catalog.recent_runs()
    assert len(rows) == 1
    assert rows[0]["exp_id"] == "ea"


def test_battery_serves_second_experiment_after_first(battery_client):
    client, _, _ = battery_client
    # Complete first
    client.post(
        "/api/data",
        json={
            "exp_id": "ea",
            "subject_id": "01",
            "trials": [],
            "status": "finished",
            "started_at": "2026-05-15T10:00:00+00:00",
            "ended_at": "2026-05-15T10:01:00+00:00",
        },
    )
    response = client.get("/")
    assert "/static/exp/eb/" in response.text


def test_battery_complete_screen_after_all(battery_client):
    client, _, _ = battery_client
    for exp_id in ["ea", "eb"]:
        client.post(
            "/api/data",
            json={
                "exp_id": exp_id,
                "subject_id": "01",
                "trials": [],
                "status": "finished",
                "started_at": "2026-05-15T10:00:00+00:00",
                "ended_at": "2026-05-15T10:01:00+00:00",
            },
        )
    response = client.get("/")
    assert response.status_code == 200
    assert "Battery complete" in response.text or "complete" in response.text.lower()
```

The existing single-experiment fixture `app_client` needs to update to the new `AppConfig` signature too. Modify it:

```python
@pytest.fixture
def app_client(hello_experiment, tmp_path):
    data_dir = tmp_path / "data"
    config = AppConfig(
        vendored_root=_vendored_root(),
        storage=FSAdapter(data_dir=data_dir),
        catalog=None,
        state_dir=tmp_path / "state",
        subject_id="01",
        session_num=None,
        run_num=None,
        experiment=ExperimentLoader().load(hello_experiment),
    )
    app = create_app(config)
    return TestClient(app), data_dir
```

- [ ] **Step 3: Run; expect failures (missing endpoints, no battery support)**

```bash
uv run pytest tests/integration/test_app.py -v
```

- [ ] **Step 4: Update `src/expdeploy/app.py`**

Replace the entire file with:

```python
"""FastAPI app factory and route handlers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from expdeploy import __version__
from expdeploy.battery.counterbalance import CounterbalanceStrategy
from expdeploy.battery.orchestrator import BatteryOrchestrator
from expdeploy.importmap import ImportMapBuilder
from expdeploy.loader import LoadedExperiment
from expdeploy.manifest import BatteryManifest
from expdeploy.renderer import render_experiment_html
from expdeploy.session import RunSession
from expdeploy.storage.base import RunRecord, StorageAdapter


COMPLETE_HTML = """<!DOCTYPE html>
<html><body style="text-align:center;margin-top:4em;font-family:system-ui,sans-serif;">
<h1>Battery complete</h1>
<p>All experiments finished. You may close this tab.</p>
</body></html>
"""


@dataclass(frozen=True, slots=True)
class AppConfig:
    vendored_root: Path
    storage: StorageAdapter
    catalog: StorageAdapter | None
    state_dir: Path
    subject_id: str
    session_num: str | None
    run_num: str | None

    experiment: LoadedExperiment | None = None
    battery_manifest: BatteryManifest | None = None
    experiments_by_id: dict[str, LoadedExperiment] | None = None
    counterbalance_strategy: CounterbalanceStrategy | None = None

    def is_battery(self) -> bool:
        return self.battery_manifest is not None


def create_app(config: AppConfig) -> FastAPI:
    app = FastAPI(title="expdeploy", version=__version__)

    builder = ImportMapBuilder(vendored_root=config.vendored_root)

    # Mount vendored jsPsych once (single version for now).
    if config.is_battery():
        assert config.experiments_by_id is not None
        any_exp = next(iter(config.experiments_by_id.values()))
    else:
        assert config.experiment is not None
        any_exp = config.experiment
    jspsych_version = any_exp.manifest.jspsych.version
    jspsych_dir = config.vendored_root / jspsych_version
    if not jspsych_dir.is_dir():
        msg = f"jsPsych version {jspsych_version} not vendored"
        raise LookupError(msg)
    app.mount(
        f"/static/jspsych/{jspsych_version}",
        StaticFiles(directory=str(jspsych_dir)),
        name="static-jspsych",
    )

    # Mount each experiment dir.
    if config.is_battery():
        assert config.experiments_by_id is not None
        for exp_id, loaded in config.experiments_by_id.items():
            app.mount(
                f"/static/exp/{exp_id}",
                StaticFiles(directory=str(loaded.path)),
                name=f"static-experiment-{exp_id}",
            )
    else:
        assert config.experiment is not None
        exp_id_single = config.experiment.manifest.experiment.exp_id
        app.mount(
            f"/static/exp/{exp_id_single}",
            StaticFiles(directory=str(config.experiment.path)),
            name="static-experiment",
        )

    # Orchestrator (battery mode only)
    orchestrator: BatteryOrchestrator | None = None
    if config.is_battery():
        assert (
            config.battery_manifest is not None
            and config.counterbalance_strategy is not None
        )
        session = RunSession(state_dir=config.state_dir, subject_id=config.subject_id)
        orchestrator = BatteryOrchestrator(
            manifest=config.battery_manifest,
            strategy=config.counterbalance_strategy,
            session=session,
        )
        orchestrator.start()

    def _render_for(loaded: LoadedExperiment) -> str:
        exp_id = loaded.manifest.experiment.exp_id
        import_map = builder.build(
            loaded,
            jspsych_url_prefix=f"/static/jspsych/{jspsych_version}",
            experiment_url_prefix=f"/static/exp/{exp_id}",
        )
        style_url = (
            f"/static/exp/{exp_id}/{loaded.manifest.experiment.style}"
            if loaded.manifest.experiment.style
            else None
        )
        return render_experiment_html(
            exp_id=exp_id,
            experiment_entry_url=f"/static/exp/{exp_id}/{loaded.manifest.experiment.entry}",
            style_url=style_url,
            jspsych_css_url=f"/static/jspsych/{jspsych_version}/jspsych.css",
            import_map=import_map,
            runtime_globals={
                "expId": exp_id,
                "subjectId": config.subject_id,
                "sessionNum": config.session_num,
                "runNum": config.run_num,
                "deployVersion": __version__,
            },
            post_url="/api/data",
        )

    @app.get("/", response_class=HTMLResponse)
    def serve_root() -> HTMLResponse:
        if orchestrator is not None:
            ref = orchestrator.next_experiment()
            if ref is None:
                return HTMLResponse(content=COMPLETE_HTML)
            assert config.experiments_by_id is not None
            loaded = config.experiments_by_id[ref.exp_id]
            return HTMLResponse(content=_render_for(loaded))
        assert config.experiment is not None
        return HTMLResponse(content=_render_for(config.experiment))

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        return {"status": "ready"}

    @app.get("/api/state")
    def get_state() -> JSONResponse:
        if orchestrator is None:
            assert config.experiment is not None
            exp_id = config.experiment.manifest.experiment.exp_id
            return JSONResponse({"current": exp_id, "completed": [], "order": [exp_id]})
        session = orchestrator.session
        return JSONResponse(
            {
                "current": session.current(),
                "completed": session.completed(),
                "order": [e.exp_id for e in orchestrator.manifest.experiments],
                "battery_id": orchestrator.battery_id,
            }
        )

    @app.post("/api/state")
    def update_state(action: dict[str, Any]) -> JSONResponse:
        if orchestrator is None:
            raise HTTPException(status_code=400, detail="not a battery deployment")
        op = action.get("op")
        if op == "reset":
            orchestrator.session.reset()
            orchestrator.start()
        elif op == "skip":
            orchestrator.advance()
        else:
            raise HTTPException(status_code=400, detail=f"unknown op {op!r}")
        return JSONResponse({"current": orchestrator.session.current()})

    @app.post("/api/data")
    def post_data(payload: dict[str, Any]) -> JSONResponse:
        try:
            record = RunRecord(
                exp_id=payload.get("exp_id"),
                subject_id=payload.get("subject_id") or config.subject_id,
                session_num=payload.get("session_num") or config.session_num,
                run_num=payload.get("run_num") or config.run_num,
                battery_id=(orchestrator.battery_id if orchestrator else None),
                started_at=payload["started_at"],
                ended_at=payload["ended_at"],
                status=payload.get("status", "finished"),
                trials=payload.get("trials", []),
                interaction_data=payload.get("interaction_data", []),
                jspsych_version=payload.get("jspsych_version"),
                deploy_version=payload.get("deploy_version"),
                client_user_agent=payload.get("client_user_agent"),
                raw_payload=payload,
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        result = config.storage.save(record)
        if not result.ok:
            raise HTTPException(status_code=500, detail=result.error or "save failed")
        # SQLite catalog write (best-effort but synchronous)
        if config.catalog is not None:
            config.catalog.save(record)
        # BIDS write if applicable
        loaded = _find_loaded(config, record.exp_id)
        if loaded is not None and loaded.manifest.bids is not None and hasattr(
            config.storage, "save_bids"
        ):
            config.storage.save_bids(record, loaded.manifest)  # type: ignore[attr-defined]
        # Advance battery
        if orchestrator is not None:
            orchestrator.advance()
        return JSONResponse({"ok": True, "path": result.path})

    return app


def _find_loaded(config: AppConfig, exp_id: str) -> LoadedExperiment | None:
    if config.experiments_by_id is not None:
        return config.experiments_by_id.get(exp_id)
    if config.experiment is not None and config.experiment.manifest.experiment.exp_id == exp_id:
        return config.experiment
    return None
```

- [ ] **Step 5: Run all tests**

```bash
uv run pytest -v
```

Expected: 50+ tests, all pass.

- [ ] **Step 6: Commit**

```bash
git add src/expdeploy/app.py tests/integration/test_app.py
git commit -m "Wire BatteryOrchestrator into app; add /api/state endpoints; SQLite + BIDS writes"
```

---

## Phase J — CLI integration

### Task 12: Update `expdeploy run` to support battery + new flags

**Files:**
- Modify: `src/expdeploy/cli.py`
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 1: Add CLI tests**

Append to `tests/unit/test_cli.py`:

```python
def test_run_command_with_battery_manifest(tmp_path):
    # Build mini battery: 2 experiments + battery.toml
    for exp_id in ["ea", "eb"]:
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir()
        (exp_dir / "manifest.toml").write_text(
            HELLO_TOML.replace('exp_id = "hello"', f'exp_id = "{exp_id}"')
        )
        (exp_dir / "index.js").write_text("export default () => {};")

    (tmp_path / "battery.toml").write_text(
        f'''
[battery]
name = "test"
counterbalance = "latin_square"

[[experiments]]
exp_id = "ea"
path = "{tmp_path / "ea"}"

[[experiments]]
exp_id = "eb"
path = "{tmp_path / "eb"}"
'''
    )

    with patch("expdeploy.cli.uvicorn") as mock_uvicorn:
        result = runner.invoke(
            app,
            [
                "run", str(tmp_path / "battery.toml"),
                "--subject", "0",
                "--port", "9095",
                "--no-browser",
            ],
        )
    assert result.exit_code == 0, result.stdout
    assert mock_uvicorn.run.called


def test_run_command_with_inline_exps(tmp_path):
    for exp_id in ["ea", "eb"]:
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir()
        (exp_dir / "manifest.toml").write_text(
            HELLO_TOML.replace('exp_id = "hello"', f'exp_id = "{exp_id}"')
        )
        (exp_dir / "index.js").write_text("export default () => {};")

    with patch("expdeploy.cli.uvicorn") as mock_uvicorn:
        result = runner.invoke(
            app,
            [
                "run",
                "--exps", f"{tmp_path / 'ea'},{tmp_path / 'eb'}",
                "--counterbalance", "fixed",
                "--subject", "01",
                "--port", "9096",
                "--no-browser",
            ],
        )
    assert result.exit_code == 0, result.stdout
    assert mock_uvicorn.run.called
```

- [ ] **Step 2: Run; expect failures (no battery/inline support yet)**

- [ ] **Step 3: Update `src/expdeploy/cli.py`**

Replace the body of the `run` command with battery-aware logic. Add helpers:

```python
from expdeploy.battery.counterbalance import (
    CounterbalanceStrategy,
    FixedStrategy,
    LatinSquareStrategy,
    SeededRandomStrategy,
    UserSuppliedStrategy,
)
from expdeploy.manifest import BatteryManifest, load_battery
from expdeploy.storage.sqlite import SQLiteCatalog


def _build_strategy(name: str, order_csv: Path | None) -> CounterbalanceStrategy:
    if name == "fixed":
        return FixedStrategy()
    if name == "latin_square":
        return LatinSquareStrategy()
    if name == "seeded_random":
        return SeededRandomStrategy()
    if name == "user_supplied":
        if order_csv is None:
            msg = "user_supplied counterbalance requires --order-csv or [battery] order_csv"
            raise typer.BadParameter(msg)
        return UserSuppliedStrategy(order_csv=order_csv)
    msg = f"unknown counterbalance {name!r}"
    raise typer.BadParameter(msg)


def _classify_target(path: Path) -> str:
    """Returns 'experiment', 'battery', or raises."""
    if path.is_file() and path.suffix == ".toml":
        return "battery"
    if path.is_dir() and (path / "manifest.toml").exists():
        return "experiment"
    msg = f"{path} is neither an experiment dir nor a battery.toml"
    raise typer.BadParameter(msg)
```

Replace the existing `run(...)` function with:

```python
@app.command()
def run(
    target: Annotated[Path | None, typer.Argument(exists=True, help="Experiment dir or battery.toml")] = None,
    exps: Annotated[str | None, typer.Option("--exps", help="Comma-delimited list of experiment dirs (inline battery)")] = None,
    counterbalance: Annotated[str, typer.Option("--counterbalance", help="fixed | latin_square | seeded_random | user_supplied")] = "fixed",
    order_csv: Annotated[Path | None, typer.Option("--order-csv", help="For --counterbalance user_supplied")] = None,
    subject: Annotated[str, typer.Option("--subject")] = "",
    session: Annotated[str | None, typer.Option("--session")] = None,
    run_num: Annotated[str | None, typer.Option("--run")] = None,
    data_dir: Annotated[Path, typer.Option("--data-dir")] = Path("./data"),
    port: Annotated[int, typer.Option("--port")] = 8080,
    no_browser: Annotated[bool, typer.Option("--no-browser")] = False,
) -> None:
    """Serve an experiment or battery on a local port."""
    if not subject:
        typer.echo("--subject is required")
        raise typer.Exit(code=2)

    if target is None and not exps:
        typer.echo("provide either a target path or --exps a,b,c")
        raise typer.Exit(code=2)
    if target is not None and exps:
        typer.echo("cannot combine target path and --exps")
        raise typer.Exit(code=2)

    if not _port_is_free(port):
        suggestion = _next_free_port(port)
        msg = f"Port {port} is in use."
        if suggestion is not None:
            msg += f" Try --port {suggestion}."
        typer.echo(msg)
        raise typer.Exit(code=2)

    from expdeploy import jspsych_assets

    vendored_root = Path(jspsych_assets.__file__).resolve().parent
    fs = FSAdapter(data_dir=data_dir)
    catalog = SQLiteCatalog(db_path=data_dir / "catalog.sqlite")
    catalog.init_schema()
    state_dir = data_dir / "state"

    if target is not None and _classify_target(target) == "experiment":
        # Single-experiment mode
        experiment = ExperimentLoader().load(target)
        config = AppConfig(
            vendored_root=vendored_root,
            storage=fs,
            catalog=catalog,
            state_dir=state_dir,
            subject_id=subject,
            session_num=session,
            run_num=run_num,
            experiment=experiment,
        )
    else:
        # Battery mode: from manifest OR inline --exps
        if target is not None:
            battery = load_battery(target)
            exp_paths = [(e.exp_id, Path(e.path)) for e in battery.experiments]
        else:
            assert exps is not None
            paths = [Path(p).expanduser().resolve() for p in exps.split(",") if p.strip()]
            experiments_loaded = [(ExperimentLoader().load(p), p) for p in paths]
            battery = BatteryManifest(
                battery=BatteryInfo(name="inline", counterbalance=counterbalance),  # type: ignore[arg-type]
                experiments=[
                    BatteryExperimentRef(
                        exp_id=loaded.manifest.experiment.exp_id, path=str(p)
                    )
                    for loaded, p in experiments_loaded
                ],
            )
            exp_paths = [(loaded.manifest.experiment.exp_id, p) for loaded, p in experiments_loaded]

        experiments_by_id: dict[str, "LoadedExperiment"] = {
            exp_id: ExperimentLoader().load(p) for exp_id, p in exp_paths
        }
        strategy = _build_strategy(
            battery.battery.counterbalance,
            order_csv if order_csv else (Path(battery.battery.order_csv) if battery.battery.order_csv else None),
        )
        config = AppConfig(
            vendored_root=vendored_root,
            storage=fs,
            catalog=catalog,
            state_dir=state_dir,
            subject_id=subject,
            session_num=session,
            run_num=run_num,
            battery_manifest=battery,
            experiments_by_id=experiments_by_id,
            counterbalance_strategy=strategy,
        )

    fastapi_app = create_app(config)
    url = f"http://127.0.0.1:{port}/"
    typer.echo(f"Serving {('battery ' + config.battery_manifest.battery.name) if config.is_battery() else config.experiment.manifest.experiment.exp_id} at {url}")
    if not no_browser:
        webbrowser.open(url)
    uvicorn.run(fastapi_app, host="127.0.0.1", port=port, log_level="info")
```

You'll also need to import `BatteryInfo`, `BatteryExperimentRef`, and `LoadedExperiment` at the top.

- [ ] **Step 4: Run tests; all should pass**

```bash
uv run pytest -v
```

- [ ] **Step 5: Commit**

```bash
git add src/expdeploy/cli.py tests/unit/test_cli.py
git commit -m "CLI run: accept battery.toml + --exps inline + --counterbalance flags"
```

---

### Task 13: Add `expdeploy init` subcommand

**Files:**
- Modify: `src/expdeploy/cli.py`
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 1: Tests**

```python
def test_init_experiment_creates_files(tmp_path):
    target = tmp_path / "newexp"
    result = runner.invoke(app, ["init", "experiment", str(target), "--task", "flanker"])
    assert result.exit_code == 0
    assert (target / "manifest.toml").exists()
    assert (target / "index.js").exists()
    assert (target / "style.css").exists()
    manifest_text = (target / "manifest.toml").read_text()
    assert 'exp_id = "flanker"' in manifest_text


def test_init_battery_creates_battery_toml(tmp_path):
    # Set up two experiments to reference
    for exp_id in ["flanker", "stroop"]:
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir()
        (exp_dir / "manifest.toml").write_text(
            HELLO_TOML.replace('exp_id = "hello"', f'exp_id = "{exp_id}"')
        )
        (exp_dir / "index.js").write_text("export default () => {};")

    out = tmp_path / "my_battery"
    result = runner.invoke(
        app,
        [
            "init", "battery", str(out),
            "--experiments", f"{tmp_path / 'flanker'},{tmp_path / 'stroop'}",
        ],
    )
    assert result.exit_code == 0
    bt = out / "battery.toml"
    assert bt.exists()
    text = bt.read_text()
    assert "flanker" in text
    assert "stroop" in text
```

- [ ] **Step 2: Run; expect failure (no `init` command)**

- [ ] **Step 3: Add `init` subcommand to `cli.py`**

```python
init_app = typer.Typer(help="Scaffold a new experiment or battery.")
app.add_typer(init_app, name="init")


@init_app.command("experiment")
def init_experiment(
    target: Annotated[Path, typer.Argument(help="Directory to create")],
    task: Annotated[str, typer.Option("--task", help="BIDS task label (alphanumeric)")] = "task",
    type_: Annotated[str, typer.Option("--type", help="behavioral | fmri | none")] = "none",
) -> None:
    target.mkdir(parents=True, exist_ok=False)
    manifest_lines = [
        "[experiment]",
        f'exp_id = "{task}"',
        f'name = "{task.capitalize()}"',
        'version = "0.1.0"',
        'entry = "index.js"',
        'style = "style.css"',
        "",
        "[jspsych]",
        'version = "8.2.3"',
        'plugins = ["@jspsych/plugin-html-keyboard-response@2.1.0"]',
    ]
    if type_ in ("behavioral", "fmri"):
        manifest_lines += [
            "",
            "[bids]",
            f'type = "{type_}"',
            f'task = "{task}"',
        ]
    (target / "manifest.toml").write_text("\n".join(manifest_lines) + "\n")
    (target / "index.js").write_text(
        '''import { initJsPsych } from "jspsych";
import htmlKeyboardResponse from "@jspsych/plugin-html-keyboard-response";

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
    { type: htmlKeyboardResponse, stimulus: "<h1>'''
        + task
        + '''</h1><p>Press any key.</p>" },
  ]);
}
'''
    )
    (target / "style.css").write_text(
        "body { font-family: system-ui, sans-serif; text-align: center; margin-top: 4em; }\n"
    )
    typer.echo(f"Created {target}")


@init_app.command("battery")
def init_battery(
    target: Annotated[Path, typer.Argument(help="Directory to create")],
    experiments: Annotated[
        str, typer.Option("--experiments", help="Comma-delimited experiment dirs")
    ],
    counterbalance: Annotated[
        str, typer.Option("--counterbalance")
    ] = "latin_square",
) -> None:
    target.mkdir(parents=True, exist_ok=False)
    paths = [Path(p).expanduser().resolve() for p in experiments.split(",") if p.strip()]
    rows: list[str] = []
    for p in paths:
        loaded = ExperimentLoader().load(p)
        eid = loaded.manifest.experiment.exp_id
        rows.append(f'[[experiments]]\nexp_id = "{eid}"\npath = "{p}"\n')
    body = (
        "[battery]\n"
        f'name = "{target.name}"\n'
        f'counterbalance = "{counterbalance}"\n\n'
        + "\n".join(rows)
    )
    (target / "battery.toml").write_text(body)
    typer.echo(f"Created {target / 'battery.toml'}")
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest -v
```

- [ ] **Step 5: Commit**

```bash
git add src/expdeploy/cli.py tests/unit/test_cli.py
git commit -m "Add 'expdeploy init experiment' and 'expdeploy init battery' subcommands"
```

---

### Task 14: Add `expdeploy status` subcommand

**Files:**
- Modify: `src/expdeploy/cli.py`
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 1: Tests**

```python
def test_status_with_empty_catalog(tmp_path):
    result = runner.invoke(app, ["status", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "no runs" in result.stdout.lower() or "0 runs" in result.stdout


def test_status_lists_runs(tmp_path):
    from datetime import UTC, datetime as dt

    from expdeploy.storage.base import RunRecord
    from expdeploy.storage.sqlite import SQLiteCatalog

    catalog = SQLiteCatalog(db_path=tmp_path / "catalog.sqlite")
    catalog.init_schema()
    catalog.save(
        RunRecord(
            exp_id="flanker",
            subject_id="01",
            started_at=dt(2026, 5, 15, tzinfo=UTC),
            ended_at=dt(2026, 5, 15, 0, 5, tzinfo=UTC),
            status="finished",
        )
    )
    result = runner.invoke(app, ["status", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "flanker" in result.stdout
    assert "01" in result.stdout
```

- [ ] **Step 2: Run; expect command-not-found**

- [ ] **Step 3: Implement**

```python
@app.command()
def status(
    data_dir: Annotated[Path, typer.Option("--data-dir")] = Path("./data"),
    subject: Annotated[str | None, typer.Option("--subject")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 25,
) -> None:
    """Show recent runs from the SQLite catalog."""
    from rich.console import Console
    from rich.table import Table

    catalog = SQLiteCatalog(db_path=data_dir / "catalog.sqlite")
    if not catalog.db_path.exists():
        typer.echo("no runs (catalog not yet created)")
        return
    catalog.init_schema()
    rows = (
        catalog.runs_for_subject(subject)[:limit]
        if subject
        else catalog.recent_runs(limit=limit)
    )
    if not rows:
        typer.echo("no runs")
        return
    table = Table(title=f"Recent runs ({len(rows)})")
    for col in ("started_at", "subject_id", "exp_id", "status", "run_id"):
        table.add_column(col)
    for row in rows:
        table.add_row(
            str(row["started_at"]),
            str(row["subject_id"]),
            str(row["exp_id"]),
            str(row["status"]),
            str(row["run_id"]),
        )
    Console().print(table)
```

- [ ] **Step 4: Run**

- [ ] **Step 5: Commit**

```bash
git add src/expdeploy/cli.py tests/unit/test_cli.py
git commit -m "Add 'expdeploy status' subcommand"
```

---

### Task 15: Add `expdeploy sync` stub

**Files:**
- Modify: `src/expdeploy/cli.py`
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 1: Test**

```python
def test_sync_stub_says_no_remote(tmp_path):
    result = runner.invoke(app, ["sync", "--adapter", "supabase"])
    assert result.exit_code == 0
    assert "no remote adapter" in result.stdout.lower() or "plan 3" in result.stdout.lower()
```

- [ ] **Step 2: Run; expect failure**

- [ ] **Step 3: Implement (stub)**

```python
@app.command()
def sync(
    adapter: Annotated[str, typer.Option("--adapter")] = "",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    _data_dir: Annotated[Path, typer.Option("--data-dir")] = Path("./data"),
) -> None:
    """Replay failed remote-storage writes. (Remote adapters land in Plan 3.)"""
    typer.echo(
        f"No remote adapter '{adapter or '<unset>'}' available yet. "
        "Remote sync ships in Plan 3."
    )
```

- [ ] **Step 4: Run + commit**

```bash
uv run pytest -v
git add src/expdeploy/cli.py tests/unit/test_cli.py
git commit -m "Add 'expdeploy sync' stub (real adapters land in Plan 3)"
```

---

## Phase K — Mini battery example + e2e

### Task 16: Add `examples/mini_battery/`

**Files:**
- Create: `examples/mini_battery/flanker/manifest.toml`
- Create: `examples/mini_battery/flanker/index.js`
- Create: `examples/mini_battery/stroop/manifest.toml`
- Create: `examples/mini_battery/stroop/index.js`
- Create: `examples/mini_battery/battery.toml`

- [ ] **Step 1: Create flanker**

`examples/mini_battery/flanker/manifest.toml`:
```toml
[experiment]
exp_id = "flanker"
name = "Flanker"
version = "1.0.0"
entry = "index.js"
estimated_minutes = 1

[jspsych]
version = "8.2.3"
plugins = ["@jspsych/plugin-html-keyboard-response@2.1.0"]
init = { display_element = "jspsych-target" }
```

`examples/mini_battery/flanker/index.js`:
```javascript
import { initJsPsych } from "jspsych";
import htmlKeyboardResponse from "@jspsych/plugin-html-keyboard-response";

export default function build() {
  const startedAt = new Date().toISOString();
  const jsPsych = initJsPsych({
    on_finish: () => {
      window.expdeploy.submit({
        exp_id: "flanker",
        subject_id: window.expdeploy.subjectId,
        started_at: startedAt,
        ended_at: new Date().toISOString(),
        trials: jsPsych.data.get().values(),
        status: "finished",
      }).then(() => {
        document.body.innerHTML += '<p>Flanker done. Loading next...</p>';
        setTimeout(() => location.reload(), 500);
      });
    },
  });
  jsPsych.run([
    { type: htmlKeyboardResponse, stimulus: "<h1>Flanker</h1><p>Press any key.</p>" },
  ]);
}
```

- [ ] **Step 2: Create stroop (same shape, swap names)**

`examples/mini_battery/stroop/manifest.toml`:
```toml
[experiment]
exp_id = "stroop"
name = "Stroop"
version = "1.0.0"
entry = "index.js"
estimated_minutes = 1

[jspsych]
version = "8.2.3"
plugins = ["@jspsych/plugin-html-keyboard-response@2.1.0"]
init = { display_element = "jspsych-target" }
```

`examples/mini_battery/stroop/index.js`:
```javascript
import { initJsPsych } from "jspsych";
import htmlKeyboardResponse from "@jspsych/plugin-html-keyboard-response";

export default function build() {
  const startedAt = new Date().toISOString();
  const jsPsych = initJsPsych({
    on_finish: () => {
      window.expdeploy.submit({
        exp_id: "stroop",
        subject_id: window.expdeploy.subjectId,
        started_at: startedAt,
        ended_at: new Date().toISOString(),
        trials: jsPsych.data.get().values(),
        status: "finished",
      }).then(() => {
        document.body.innerHTML += '<p>Stroop done. Loading next...</p>';
        setTimeout(() => location.reload(), 500);
      });
    },
  });
  jsPsych.run([
    { type: htmlKeyboardResponse, stimulus: "<h1>Stroop</h1><p>Press any key.</p>" },
  ]);
}
```

- [ ] **Step 3: Create battery.toml**

`examples/mini_battery/battery.toml`:
```toml
[battery]
name = "Mini battery (flanker + stroop)"
counterbalance = "fixed"

[[experiments]]
exp_id = "flanker"
path = "./flanker"

[[experiments]]
exp_id = "stroop"
path = "./stroop"
```

- [ ] **Step 4: Validate**

```bash
uv run expdeploy validate ./examples/mini_battery/flanker
uv run expdeploy validate ./examples/mini_battery/stroop
```

Expected: both `ok`.

- [ ] **Step 5: Commit**

```bash
git add examples/mini_battery/
git commit -m "Add examples/mini_battery (flanker + stroop, fixed counterbalance)"
```

---

### Task 17: Playwright e2e for the mini battery

**Files:**
- Create: `tests/e2e/test_mini_battery.py`

- [ ] **Step 1: Write test**

```python
"""E2E: Playwright drives through a 2-experiment battery."""

from __future__ import annotations

import json
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import sync_playwright


REPO = Path(__file__).resolve().parents[2]
BATTERY = REPO / "examples" / "mini_battery" / "battery.toml"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_healthz(url: str, timeout_seconds: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code == 200:
                return
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.25)
    raise TimeoutError(f"{url} never healthy")


@pytest.mark.e2e
def test_battery_round_trip_two_experiments(tmp_path):
    port = _free_port()
    data_dir = tmp_path / "data"
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "expdeploy",
            "run", str(BATTERY),
            "--subject", "0",
            "--data-dir", str(data_dir),
            "--port", str(port),
            "--no-browser",
        ],
        cwd=str(REPO),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_for_healthz(f"http://127.0.0.1:{port}/healthz")

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            # Flanker
            page.goto(f"http://127.0.0.1:{port}/")
            page.wait_for_selector("text=Flanker", timeout=10_000)
            page.keyboard.press("Space")
            # Brief wait then a reload happens automatically (index.js)
            # Stroop
            page.wait_for_selector("text=Stroop", timeout=15_000)
            page.keyboard.press("Space")
            # Battery complete screen
            page.wait_for_selector("text=Battery complete", timeout=15_000)
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    # Verify SQLite catalog has two runs
    conn = sqlite3.connect(data_dir / "catalog.sqlite")
    rows = conn.execute("SELECT exp_id FROM runs ORDER BY started_at ASC").fetchall()
    conn.close()
    exp_ids = [r[0] for r in rows]
    assert exp_ids == ["flanker", "stroop"]

    # Verify raw files exist for both
    flanker_files = list((data_dir / "raw" / "sub-0").glob("*task-flanker*.json"))
    stroop_files = list((data_dir / "raw" / "sub-0").glob("*task-stroop*.json"))
    assert len(flanker_files) == 1
    assert len(stroop_files) == 1
```

- [ ] **Step 2: Run**

```bash
uv run pytest tests/e2e/test_mini_battery.py -v -m e2e
```

Expected: `1 passed`. (Allow 30-60s.)

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_mini_battery.py
git commit -m "Add Playwright e2e: 2-experiment mini battery round-trip with SQLite + raw verification"
```

---

## Phase L — Final sweep + PR

### Task 18: Full local verification

- [ ] **Step 1: Lint clean**

```bash
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

Expected: all unit + integration + e2e tests pass (60+ tests).

- [ ] **Step 4: Smoke (battery)**

```bash
uv run expdeploy run ./examples/mini_battery/battery.toml --subject 0 --port 18081 --no-browser &
sleep 4
curl -s -w "%{http_code}\n" -o /dev/null http://127.0.0.1:18081/healthz
curl -s http://127.0.0.1:18081/api/state | head -1
pkill -f "expdeploy run" || true
```

Expected: 200 on healthz; `/api/state` JSON includes `"current": "flanker"`.

- [ ] **Step 5: No commit — verification only.**

---

### Task 19: Open PR against main

- [ ] **Step 1: Push the feature branch**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/expdeploy
git push -u origin feat/plan-2-storage-battery
```

- [ ] **Step 2: Create the PR**

```bash
gh pr create --base main --head feat/plan-2-storage-battery --title "Plan 2: Storage layer + batteries + counterbalance" --body "$(cat <<'EOF'
## Summary
- Enriches `RunRecord` with ULID, timestamps, status, group_index, battery_id.
- Adds `SQLiteCatalog` always-on adapter (schema + queries).
- Splits `FSAdapter` into raw JSON write + BIDS layout (`dataset_description.json`, `participants.tsv`, `events.tsv`, sidecar JSON).
- Adds four counterbalance strategies (fixed, latin_square, seeded_random, user_supplied).
- Adds `BatteryManifest` + `load_battery`.
- Adds file-locked per-subject `RunSession`.
- Adds `BatteryOrchestrator` (manifest + strategy + session).
- Wires battery mode into the FastAPI app with `/api/state` endpoints.
- CLI gains: `run` accepts battery.toml or `--exps a,b,c`; `init experiment`/`init battery`; `status`; `sync` (stub).
- Adds `examples/mini_battery/` + a Playwright e2e covering the full 2-experiment round-trip.

Maps to spec sections §3–§8.

## Test plan
- [ ] Local: `uv run ruff check . && uv run ruff format --check . && uv run mypy src/expdeploy && uv run pytest -v` all green.
- [ ] Local smoke: `expdeploy run ./examples/mini_battery/battery.toml --subject 0` runs the full battery in a browser.
- [ ] CI matrix green on Ubuntu+macOS × Python 3.11+3.12.

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

## Summary of what Plan 2 produces

After Task 19:

- Full BIDS layout (fMRI + behavioral) generated alongside raw JSON
- SQLite catalog indexing every run; queryable via `expdeploy status`
- Battery support: launch via manifest file or inline `--exps a,b,c`
- Four counterbalance schemes (fixed, latin_square, seeded_random, user_supplied)
- File-locked per-subject session state surviving server restarts
- `/api/state` endpoints for current/completed/order + reset/skip ops
- `expdeploy init experiment` and `expdeploy init battery` scaffolds
- `expdeploy status` Rich-table view
- `expdeploy sync` stub (Plan-3 placeholder)
- `examples/mini_battery/` (flanker + stroop) + Playwright e2e covering battery round-trip

**Plan 3 (next):** Supabase adapter, OCI Dockerfile + multi-arch base image, `expdeploy build` for study images, cosign signing (deferred), mkdocs site, release CI.
