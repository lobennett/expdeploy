"""Tests for expdeploy.storage.fs.FSAdapter (minimal Plan-1 surface)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from expdeploy.storage.base import RunRecord
from expdeploy.storage.fs import FSAdapter


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
        trials=(
            trials
            if trials is not None
            else [
                {"trial_type": "html-keyboard-response", "rt": 250},
            ]
        ),
        raw_payload={
            "trials": trials
            if trials is not None
            else [
                {"trial_type": "html-keyboard-response", "rt": 250},
            ]
        },
    )


def test_save_writes_raw_json(tmp_path):
    adapter = FSAdapter(data_dir=tmp_path)
    result = adapter.save(_record())
    assert result.ok is True
    saved = Path(result.path)
    assert saved.exists()
    assert saved.is_file()
    payload = json.loads(saved.read_text())
    assert payload["trials"][0]["rt"] == 250


def test_save_uses_bids_style_filename(tmp_path):
    adapter = FSAdapter(data_dir=tmp_path)
    result = adapter.save(_record(exp_id="hello", subject_id="01"))
    saved = Path(result.path)
    assert saved.name.startswith("sub-01_")
    assert "_task-hello_" in saved.name
    assert saved.name.endswith("_beh.json")


def test_save_with_session_and_run(tmp_path):
    adapter = FSAdapter(data_dir=tmp_path)
    record = RunRecord(
        exp_id="hello",
        subject_id="01",
        session_num="1",
        run_num="2",
        started_at=datetime(2026, 5, 15, 10, 0, 0, tzinfo=UTC),
        ended_at=datetime(2026, 5, 15, 10, 1, 0, tzinfo=UTC),
        status="finished",
        trials=[{"trial_type": "html-keyboard-response", "rt": 250}],
        raw_payload={"trials": []},
    )
    result = adapter.save(record)
    saved = Path(result.path)
    assert "sub-01" in saved.name
    assert "ses-1" in saved.name
    assert "run-2" in saved.name


def test_save_writes_under_subject_directory(tmp_path):
    adapter = FSAdapter(data_dir=tmp_path)
    result = adapter.save(_record(subject_id="01"))
    assert Path(result.path).parent.name == "sub-01"


def test_save_rejects_invalid_subject_id(tmp_path):
    with pytest.raises(ValueError):
        # subject_id with disallowed characters
        FSAdapter._make_filename(  # type: ignore[attr-defined]
            exp_id="hello",
            subject_id="sub/../escape",
            session_num=None,
            run_num=None,
        )
