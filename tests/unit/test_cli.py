"""Tests for the Typer CLI (without spinning up uvicorn)."""

from __future__ import annotations

from typer.testing import CliRunner

from expdeploy import __version__
from expdeploy.cli import app

runner = CliRunner()

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


def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_validate_valid_experiment(tmp_path):
    exp_dir = tmp_path / "hello"
    exp_dir.mkdir()
    (exp_dir / "manifest.toml").write_text(HELLO_TOML)
    (exp_dir / "index.js").write_text("export default () => {};")
    result = runner.invoke(app, ["validate", str(exp_dir)])
    assert result.exit_code == 0
    assert "ok" in result.stdout.lower()


def test_validate_missing_manifest(tmp_path):
    exp_dir = tmp_path / "empty"
    exp_dir.mkdir()
    result = runner.invoke(app, ["validate", str(exp_dir)])
    assert result.exit_code != 0
    assert "manifest.toml" in result.stdout or "manifest.toml" in str(result.exception)


def test_validate_bad_bids_task_label(tmp_path):
    bad_toml = HELLO_TOML + '\n[bids]\ntype = "fmri"\ntask = "n_back"\n'
    exp_dir = tmp_path / "bad"
    exp_dir.mkdir()
    (exp_dir / "manifest.toml").write_text(bad_toml)
    (exp_dir / "index.js").write_text("")
    result = runner.invoke(app, ["validate", str(exp_dir)])
    assert result.exit_code != 0
