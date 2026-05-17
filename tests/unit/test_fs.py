"""Tests for expdeploy.storage.fs.FSAdapter (minimal Plan-1 surface)."""

from __future__ import annotations

import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from expdeploy.manifest import ExperimentManifest
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
    assert data["trial_type"]["Description"] == "Congruency of flanker."
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
