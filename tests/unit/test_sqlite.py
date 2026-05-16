"""Tests for expdeploy.storage.sqlite.SQLiteCatalog."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

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
    catalog.save(
        _record(
            subject_id="01",
            started_at=datetime(2026, 5, 14, tzinfo=UTC),
            ended_at=datetime(2026, 5, 14, 0, 5, tzinfo=UTC),
        )
    )
    catalog.save(
        _record(
            subject_id="02",
            started_at=datetime(2026, 5, 15, tzinfo=UTC),
            ended_at=datetime(2026, 5, 15, 0, 5, tzinfo=UTC),
        )
    )
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
