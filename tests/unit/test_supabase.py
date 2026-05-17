"""Tests for expdeploy.storage.supabase.SupabaseAdapter (mocked client)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

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
    client.schema.return_value.table.return_value.upsert.return_value.execute.return_value = (
        MagicMock(data=[{"run_id": rec.run_id}], count=1)
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
    client.schema.return_value.table.return_value.upsert.return_value.execute.return_value = (
        MagicMock(data=[{"run_id": rec.run_id}], count=1)
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
