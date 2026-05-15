"""expdeploy CLI — Typer-based."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from expdeploy import __version__
from expdeploy.loader import ExperimentLoader

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
