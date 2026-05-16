"""Tests for the Typer CLI (without spinning up uvicorn)."""

from __future__ import annotations

from unittest.mock import patch

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


def test_run_command_wires_uvicorn(tmp_path):
    exp_dir = tmp_path / "hello"
    exp_dir.mkdir()
    (exp_dir / "manifest.toml").write_text(HELLO_TOML)
    (exp_dir / "index.js").write_text("export default () => {};")

    with patch("expdeploy.cli.uvicorn") as mock_uvicorn:
        result = runner.invoke(
            app,
            ["run", str(exp_dir), "--subject", "01", "--port", "9091", "--no-browser"],
        )
    assert result.exit_code == 0, result.stdout
    assert mock_uvicorn.run.called
    kwargs = mock_uvicorn.run.call_args.kwargs
    assert kwargs["port"] == 9091
    assert kwargs["host"] == "127.0.0.1"


def test_run_command_rejects_busy_port(tmp_path):
    import socket

    exp_dir = tmp_path / "hello"
    exp_dir.mkdir()
    (exp_dir / "manifest.toml").write_text(HELLO_TOML)
    (exp_dir / "index.js").write_text("export default () => {};")

    # Open a socket on a port to make it busy
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    busy_port = sock.getsockname()[1]
    try:
        result = runner.invoke(
            app,
            ["run", str(exp_dir), "--subject", "01", "--port", str(busy_port), "--no-browser"],
        )
        assert result.exit_code != 0
        # Look for the suggested-next-port hint (could be in stdout OR stderr depending on err=True flag)
        out = (result.stdout or "") + (result.stderr or "")
        assert "busy" in out.lower() or "in use" in out.lower()
    finally:
        sock.close()


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
        f"""
[battery]
name = "test"
counterbalance = "latin_square"

[[experiments]]
exp_id = "ea"
path = "{tmp_path / "ea"}"

[[experiments]]
exp_id = "eb"
path = "{tmp_path / "eb"}"
"""
    )

    with patch("expdeploy.cli.uvicorn") as mock_uvicorn:
        result = runner.invoke(
            app,
            [
                "run",
                str(tmp_path / "battery.toml"),
                "--subject",
                "0",
                "--port",
                "9095",
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
                "--exps",
                f"{tmp_path / 'ea'},{tmp_path / 'eb'}",
                "--counterbalance",
                "fixed",
                "--subject",
                "01",
                "--port",
                "9096",
                "--no-browser",
            ],
        )
    assert result.exit_code == 0, result.stdout
    assert mock_uvicorn.run.called


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
            "init",
            "battery",
            str(out),
            "--experiments",
            f"{tmp_path / 'flanker'},{tmp_path / 'stroop'}",
        ],
    )
    assert result.exit_code == 0
    bt = out / "battery.toml"
    assert bt.exists()
    text = bt.read_text()
    assert "flanker" in text
    assert "stroop" in text


def test_status_with_empty_catalog(tmp_path):
    result = runner.invoke(app, ["status", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "no runs" in result.stdout.lower() or "0 runs" in result.stdout


def test_status_lists_runs(tmp_path):
    from datetime import UTC
    from datetime import datetime as dt

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
