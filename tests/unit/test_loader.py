"""Tests for expdeploy.loader.ExperimentLoader."""

from __future__ import annotations

import pytest

from expdeploy.loader import ExperimentLoader, LoadedExperiment

HELLO_TOML = """
[experiment]
exp_id = "hello"
name = "Hello world"
version = "1.0.0"
entry = "index.js"

[jspsych]
version = "8.2.3"
plugins = ["@jspsych/plugin-html-keyboard-response@2.1.0"]
"""


def _make_hello(tmp_path):
    exp_dir = tmp_path / "hello"
    exp_dir.mkdir()
    (exp_dir / "manifest.toml").write_text(HELLO_TOML)
    (exp_dir / "index.js").write_text("export default () => {};")
    return exp_dir


def test_loader_returns_loaded_experiment(tmp_path):
    exp_dir = _make_hello(tmp_path)
    loaded = ExperimentLoader().load(exp_dir)
    assert isinstance(loaded, LoadedExperiment)
    assert loaded.manifest.experiment.exp_id == "hello"
    assert loaded.path == exp_dir.resolve()
    assert loaded.entry_path == (exp_dir / "index.js").resolve()


def test_loader_rejects_missing_manifest(tmp_path):
    exp_dir = tmp_path / "no_manifest"
    exp_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        ExperimentLoader().load(exp_dir)


def test_loader_rejects_missing_entry(tmp_path):
    exp_dir = tmp_path / "no_entry"
    exp_dir.mkdir()
    (exp_dir / "manifest.toml").write_text(HELLO_TOML)
    # no index.js
    with pytest.raises(FileNotFoundError):
        ExperimentLoader().load(exp_dir)
