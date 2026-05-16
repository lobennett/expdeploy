"""Tests for expdeploy.session.RunSession."""

from __future__ import annotations

import json

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
