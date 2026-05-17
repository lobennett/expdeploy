"""Tests for the real `expdeploy sync` command."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from expdeploy.cli import app
from expdeploy.storage.base import RunRecord, SaveResult
from expdeploy.storage.sqlite import SQLiteCatalog

runner = CliRunner()


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
        result_first = runner.invoke(
            app, ["sync", "--data-dir", str(data_dir), "--adapter", "supabase"]
        )
        assert result_first.exit_code == 0
        # Second invocation: nothing pending
        result_second = runner.invoke(
            app, ["sync", "--data-dir", str(data_dir), "--adapter", "supabase"]
        )
    assert result_second.exit_code == 0
    assert "Nothing to sync" in result_second.stdout
