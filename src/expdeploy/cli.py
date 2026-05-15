"""expdeploy CLI — Typer-based."""

from __future__ import annotations

import socket
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from expdeploy import __version__
from expdeploy.app import AppConfig, create_app
from expdeploy.loader import ExperimentLoader
from expdeploy.storage.fs import FSAdapter

app = typer.Typer(no_args_is_help=True, help="expdeploy — deploy jsPsych v8 experiments.")


@app.command()
def version() -> None:
    """Print the expdeploy version."""
    typer.echo(f"expdeploy {__version__}")


@app.command()
def validate(
    path: Annotated[Path, typer.Argument(exists=True, file_okay=False, dir_okay=True)],
) -> None:
    """Validate an experiment manifest at PATH."""
    try:
        ExperimentLoader().load(path)
    except Exception as exc:
        typer.echo(f"INVALID: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo("ok")


def _port_is_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _next_free_port(start: int, host: str = "127.0.0.1", attempts: int = 100) -> int | None:
    for candidate in range(start + 1, start + 1 + attempts):
        if _port_is_free(candidate, host):
            return candidate
    return None


@app.command()
def run(
    path: Annotated[Path, typer.Argument(exists=True, file_okay=False, dir_okay=True)],
    subject: Annotated[str, typer.Option("--subject", help="Subject label (e.g., 01).")],
    session: Annotated[str | None, typer.Option("--session", help="Session label.")] = None,
    run_num: Annotated[str | None, typer.Option("--run", help="Run label.")] = None,
    data_dir: Annotated[Path, typer.Option("--data-dir")] = Path("./data"),
    port: Annotated[int, typer.Option("--port")] = 8080,
    no_browser: Annotated[bool, typer.Option("--no-browser")] = False,
) -> None:
    """Serve an experiment on a local port."""
    if not _port_is_free(port):
        suggestion = _next_free_port(port)
        msg = f"Port {port} is in use."
        if suggestion is not None:
            msg += f" Try --port {suggestion}."
        typer.echo(msg)
        raise typer.Exit(code=2)

    experiment = ExperimentLoader().load(path)
    from expdeploy import jspsych_assets

    config = AppConfig(
        experiment=experiment,
        vendored_root=Path(jspsych_assets.__file__).resolve().parent,
        storage=FSAdapter(data_dir=data_dir),
        subject_id=subject,
        session_num=session,
        run_num=run_num,
    )
    fastapi_app = create_app(config)

    url = f"http://127.0.0.1:{port}/"
    typer.echo(f"Serving {experiment.manifest.experiment.exp_id} at {url}")
    if not no_browser:
        webbrowser.open(url)
    uvicorn.run(fastapi_app, host="127.0.0.1", port=port, log_level="info")
