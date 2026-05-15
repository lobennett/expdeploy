"""Tests for expdeploy.manifest — Pydantic models for manifest.toml."""

from __future__ import annotations

import tomllib

import pytest

from expdeploy.manifest import ExperimentManifest, load_manifest

HELLO_TOML = """
[experiment]
exp_id = "hello"
name = "Hello world"
version = "1.0.0"
entry = "index.js"
estimated_minutes = 1

[jspsych]
version = "8.2.3"
plugins = ["@jspsych/plugin-html-keyboard-response@2.1.0"]
init = { fullscreen = false }
"""


def test_minimal_manifest_parses():
    data = tomllib.loads(HELLO_TOML)
    manifest = ExperimentManifest.model_validate(data)
    assert manifest.experiment.exp_id == "hello"
    assert manifest.experiment.name == "Hello world"
    assert manifest.experiment.entry == "index.js"
    assert manifest.jspsych.version == "8.2.3"
    assert manifest.jspsych.plugins == ["@jspsych/plugin-html-keyboard-response@2.1.0"]
    assert manifest.bids is None
    assert manifest.import_map_extras == {}


INVALID_BIDS_TASK_TOML = """
[experiment]
exp_id = "n_back_test"
name = "Bad BIDS label"
version = "1.0.0"
entry = "index.js"

[jspsych]
version = "8.2.3"
plugins = []

[bids]
type = "fmri"
task = "n_back"
"""


def test_bids_task_label_rejects_underscore():
    data = tomllib.loads(INVALID_BIDS_TASK_TOML)
    with pytest.raises(Exception) as excinfo:
        ExperimentManifest.model_validate(data)
    assert "task" in str(excinfo.value)


VALID_BIDS_TOML = """
[experiment]
exp_id = "nback_v1"
name = "N-back"
version = "1.0.0"
entry = "index.js"

[jspsych]
version = "8.2.3"
plugins = []

[bids]
type = "behavioral"
task = "nback"

[bids.columns.trial_type]
description = "Whether the trial was a target or non-target."
levels = { target = "Target", nontarget = "Non-target" }
"""


def test_valid_bids_with_columns_parses():
    data = tomllib.loads(VALID_BIDS_TOML)
    manifest = ExperimentManifest.model_validate(data)
    assert manifest.bids is not None
    assert manifest.bids.type == "behavioral"
    assert manifest.bids.task == "nback"
    assert "trial_type" in manifest.bids.columns
    assert manifest.bids.columns["trial_type"].levels["target"] == "Target"


def test_load_manifest_from_disk(tmp_path):
    manifest_path = tmp_path / "manifest.toml"
    manifest_path.write_text(HELLO_TOML)
    manifest = load_manifest(manifest_path)
    assert manifest.experiment.exp_id == "hello"


def test_load_manifest_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_manifest(tmp_path / "nope.toml")
