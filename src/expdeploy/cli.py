"""expdeploy CLI — Typer-based."""

from __future__ import annotations

import hashlib
import os
import socket
import subprocess
import webbrowser
from pathlib import Path
from typing import Annotated, Any

import typer
import uvicorn

from expdeploy import __version__
from expdeploy.app import AppConfig, create_app
from expdeploy.battery.counterbalance import (
    CounterbalanceStrategy,
    FixedStrategy,
    LatinSquareStrategy,
    SeededRandomStrategy,
    UserSuppliedStrategy,
)
from expdeploy.loader import ExperimentLoader, LoadedExperiment
from expdeploy.manifest import BatteryExperimentRef, BatteryInfo, BatteryManifest, load_battery
from expdeploy.storage.base import RunRecord
from expdeploy.storage.fs import FSAdapter
from expdeploy.storage.sqlite import SQLiteCatalog

app = typer.Typer(no_args_is_help=True, help="expdeploy — deploy jsPsych v8 experiments.")
init_app = typer.Typer(help="Scaffold a new experiment or battery.")
app.add_typer(init_app, name="init")

supabase_app = typer.Typer(help="Manage Supabase remote adapter.")
app.add_typer(supabase_app, name="supabase")


@supabase_app.command("migrate")
def supabase_migrate() -> None:
    """Apply idempotent DDL to the configured Supabase Postgres."""
    try:
        from expdeploy.storage.supabase import SupabaseAdapter, SupabaseConfig

        cfg = SupabaseConfig.from_env()
        adapter = SupabaseAdapter(config=cfg)
        adapter.apply_migrations()
    except Exception as exc:
        typer.echo(f"Migration failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo("Schema applied.")


@supabase_app.command("test-connection")
def supabase_test_connection() -> None:
    """Verify the configured Supabase credentials and bucket access."""
    try:
        from expdeploy.storage.supabase import SupabaseAdapter, SupabaseConfig

        cfg = SupabaseConfig.from_env()
        adapter = SupabaseAdapter(config=cfg)
        client = adapter._get_client()
        # A trivial read against the configured schema.
        client.schema(cfg.schema).table("runs").select("run_id").limit(1).execute()
        typer.echo(f"Connected to {cfg.url} (schema={cfg.schema}, bucket={cfg.bucket}).")
    except Exception as exc:
        typer.echo(f"Connection failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@supabase_app.command("drop")
def supabase_drop(
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Required for destructive operation")
    ] = False,
) -> None:
    """DROP the expdeploy schema. Test envs only."""
    if not confirm:
        typer.echo("Refusing without --confirm.", err=True)
        raise typer.Exit(code=2)
    try:
        from expdeploy.storage.supabase import SupabaseAdapter, SupabaseConfig

        cfg = SupabaseConfig.from_env()
        adapter = SupabaseAdapter(config=cfg)
        client = adapter._get_client()
        client.postgrest.rpc(
            "exec_sql", {"sql": f"DROP SCHEMA IF EXISTS {cfg.schema} CASCADE;"}
        ).execute()
        typer.echo(f"Dropped schema {cfg.schema}.")
    except Exception as exc:
        typer.echo(f"Drop failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc


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
        typer.echo(f"INVALID: {exc}", err=True)
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


def _build_strategy(name: str, order_csv: Path | None) -> CounterbalanceStrategy:
    if name == "fixed":
        return FixedStrategy()
    if name == "latin_square":
        return LatinSquareStrategy()
    if name == "seeded_random":
        return SeededRandomStrategy()
    if name == "user_supplied":
        if order_csv is None:
            msg = "user_supplied counterbalance requires --order-csv or [battery] order_csv"
            raise typer.BadParameter(msg)
        return UserSuppliedStrategy(order_csv=order_csv)
    msg = f"unknown counterbalance {name!r}"
    raise typer.BadParameter(msg)


def _classify_target(path: Path) -> str:
    """Returns 'experiment', 'battery', or raises."""
    if path.is_file() and path.suffix == ".toml":
        return "battery"
    if path.is_dir() and (path / "manifest.toml").exists():
        return "experiment"
    msg = f"{path} is neither an experiment dir nor a battery.toml"
    raise typer.BadParameter(msg)


@app.command()
def run(
    target: Annotated[Path | None, typer.Argument(help="Experiment dir or battery.toml")] = None,
    exps: Annotated[
        str | None,
        typer.Option("--exps", help="Comma-delimited list of experiment dirs (inline battery)"),
    ] = None,
    counterbalance: Annotated[
        str,
        typer.Option(
            "--counterbalance", help="fixed | latin_square | seeded_random | user_supplied"
        ),
    ] = "fixed",
    order_csv: Annotated[
        Path | None, typer.Option("--order-csv", help="For --counterbalance user_supplied")
    ] = None,
    subject: Annotated[str, typer.Option("--subject")] = "",
    session: Annotated[str | None, typer.Option("--session")] = None,
    run_num: Annotated[str | None, typer.Option("--run")] = None,
    data_dir: Annotated[Path, typer.Option("--data-dir")] = Path("./data"),
    port: Annotated[int, typer.Option("--port")] = 8080,
    no_browser: Annotated[bool, typer.Option("--no-browser")] = False,
    remote: Annotated[
        list[str] | None,
        typer.Option("--remote", help="Remote adapter name(s) to mirror data (e.g. supabase)"),
    ] = None,
) -> None:
    """Serve an experiment or battery on a local port."""
    if not subject:
        typer.echo("--subject is required", err=True)
        raise typer.Exit(code=2)

    if target is None and not exps:
        typer.echo("provide either a target path or --exps a,b,c", err=True)
        raise typer.Exit(code=2)
    if target is not None and exps:
        typer.echo("cannot combine target path and --exps", err=True)
        raise typer.Exit(code=2)

    if not _port_is_free(port):
        suggestion = _next_free_port(port)
        msg = f"Port {port} is in use."
        if suggestion is not None:
            msg += f" Try --port {suggestion}."
        typer.echo(msg, err=True)
        raise typer.Exit(code=2)

    from expdeploy import jspsych_assets

    vendored_root = Path(jspsych_assets.__file__).resolve().parent
    fs = FSAdapter(data_dir=data_dir)
    catalog = SQLiteCatalog(db_path=data_dir / "catalog.sqlite")
    catalog.init_schema()
    state_dir = data_dir / "state"

    from expdeploy.storage.base import StorageAdapter

    remotes_list: list[StorageAdapter] = []
    for r in remote or []:
        if r == "supabase":
            from expdeploy.storage.supabase import SupabaseAdapter, SupabaseConfig

            remotes_list.append(SupabaseAdapter(config=SupabaseConfig.from_env()))
        else:
            typer.echo(f"Unknown --remote adapter: {r}", err=True)
            raise typer.Exit(code=2)

    if target is not None and _classify_target(target) == "experiment":
        # Single-experiment mode
        experiment = ExperimentLoader().load(target)
        config = AppConfig(
            vendored_root=vendored_root,
            storage=fs,
            catalog=catalog,
            state_dir=state_dir,
            subject_id=subject,
            session_num=session,
            run_num=run_num,
            experiment=experiment,
            remotes=tuple(remotes_list),
        )
    else:
        # Battery mode: from manifest OR inline --exps
        if target is not None:
            battery = load_battery(target)
            battery_dir = target.resolve().parent
            exp_paths = [(e.exp_id, (battery_dir / e.path).resolve()) for e in battery.experiments]
        else:
            assert exps is not None
            paths = [Path(p).expanduser().resolve() for p in exps.split(",") if p.strip()]
            experiments_loaded = [(ExperimentLoader().load(p), p) for p in paths]
            battery = BatteryManifest(
                battery=BatteryInfo(name="inline", counterbalance=counterbalance),  # type: ignore[arg-type]
                experiments=[
                    BatteryExperimentRef(exp_id=loaded.manifest.experiment.exp_id, path=str(p))
                    for loaded, p in experiments_loaded
                ],
            )
            exp_paths = [(loaded.manifest.experiment.exp_id, p) for loaded, p in experiments_loaded]

        experiments_by_id: dict[str, LoadedExperiment] = {
            exp_id: ExperimentLoader().load(p) for exp_id, p in exp_paths
        }
        strategy = _build_strategy(
            battery.battery.counterbalance,
            order_csv
            if order_csv
            else (Path(battery.battery.order_csv) if battery.battery.order_csv else None),
        )
        config = AppConfig(
            vendored_root=vendored_root,
            storage=fs,
            catalog=catalog,
            state_dir=state_dir,
            subject_id=subject,
            session_num=session,
            run_num=run_num,
            battery_manifest=battery,
            experiments_by_id=experiments_by_id,
            counterbalance_strategy=strategy,
            remotes=tuple(remotes_list),
        )

    fastapi_app = create_app(config)
    host = os.environ.get("EXPDEPLOY_HOST", "127.0.0.1")
    url = f"http://{host}:{port}/"
    if config.is_battery():
        assert config.battery_manifest is not None
        label = f"battery {config.battery_manifest.battery.name}"
    else:
        assert config.experiment is not None
        label = config.experiment.manifest.experiment.exp_id
    typer.echo(f"Serving {label} at {url}")
    if not no_browser:
        webbrowser.open(url)
    uvicorn.run(fastapi_app, host=host, port=port, log_level="info")


@app.command()
def status(
    data_dir: Annotated[Path, typer.Option("--data-dir")] = Path("./data"),
    subject: Annotated[str | None, typer.Option("--subject")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 25,
) -> None:
    """Show recent runs from the SQLite catalog."""
    from rich.console import Console
    from rich.table import Table

    catalog = SQLiteCatalog(db_path=data_dir / "catalog.sqlite")
    if not catalog.db_path.exists():
        typer.echo("no runs (catalog not yet created)")
        return
    catalog.init_schema()
    rows = (
        catalog.runs_for_subject(subject)[:limit] if subject else catalog.recent_runs(limit=limit)
    )
    if not rows:
        typer.echo("no runs")
        return
    table = Table(title=f"Recent runs ({len(rows)})")
    for col in ("started_at", "subject_id", "exp_id", "status", "run_id"):
        table.add_column(col)
    for row in rows:
        table.add_row(
            str(row["started_at"]),
            str(row["subject_id"]),
            str(row["exp_id"]),
            str(row["status"]),
            str(row["run_id"]),
        )
    Console().print(table)


def _row_to_run_record(row: dict[str, Any]) -> RunRecord:
    import json as _json

    return RunRecord(
        run_id=row["run_id"],
        exp_id=row["exp_id"],
        exp_version=row["exp_version"],
        subject_id=row["subject_id"],
        session_num=row["session_num"],
        run_num=row["run_num"],
        battery_id=row["battery_id"],
        group_index=row["group_index"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        status=row["status"],
        trials=_json.loads(row["trials_json"] or "[]"),
        interaction_data=_json.loads(row["interaction_data_json"] or "[]"),
        jspsych_version=row["jspsych_version"],
        deploy_version=row["deploy_version"],
        client_user_agent=row["client_user_agent"],
    )


@app.command()
def sync(
    adapter: Annotated[str, typer.Option("--adapter")] = "supabase",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    data_dir: Annotated[Path, typer.Option("--data-dir")] = Path("./data"),
) -> None:
    """Replay failed remote-storage writes against the configured adapter."""
    catalog = SQLiteCatalog(db_path=data_dir / "catalog.sqlite")
    if not catalog.db_path.exists():
        typer.echo(f"No catalog at {catalog.db_path}", err=True)
        raise typer.Exit(code=1)
    pending = catalog.pending_remote_writes(adapter=adapter)
    if not pending:
        typer.echo("Nothing to sync.")
        return

    if dry_run:
        typer.echo(f"Would replay {len(pending)} run(s) against {adapter}:")
        for r in pending:
            typer.echo(f"  - {r['run_id']} ({r['subject_id']} / {r['exp_id']})")
        return

    if adapter != "supabase":
        typer.echo(f"Unknown adapter {adapter!r}", err=True)
        raise typer.Exit(code=2)

    from expdeploy.storage.supabase import SupabaseAdapter, SupabaseConfig

    try:
        cfg = SupabaseConfig.from_env()
    except Exception as exc:
        typer.echo(f"Supabase config error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    sa = SupabaseAdapter(config=cfg)
    ok_count = 0
    fail_count = 0
    for row in pending:
        record = _row_to_run_record(row)
        result = sa.save(record)
        if result.ok:
            catalog.record_remote_attempt(record.run_id, adapter, "synced", remote_uri=result.path)
            ok_count += 1
        else:
            catalog.record_remote_attempt(record.run_id, adapter, "failed", error=result.error)
            fail_count += 1

    typer.echo(f"Synced {ok_count} / Failed {fail_count}.")
    if fail_count:
        raise typer.Exit(code=1)


@app.command()
def build(
    target: Annotated[
        Path, typer.Argument(exists=True, help="Path to battery.toml or experiment dir")
    ],
    tag: Annotated[
        str, typer.Option("--tag", help="OCI image tag, e.g. ghcr.io/you/study:2026-05-17")
    ],
    base_tag: Annotated[
        str, typer.Option("--base-tag", help="Base image tag to FROM")
    ] = "ghcr.io/lobennett/expdeploy:latest",
    engine: Annotated[str, typer.Option("--engine", help="docker | podman")] = "docker",
    push: Annotated[bool, typer.Option("--push/--no-push")] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Where to write study.Dockerfile (default: next to target)"),
    ] = None,
) -> None:
    """Build a study-specific OCI image with experiments baked in."""
    target = target.resolve()
    if target.is_file() and target.suffix == ".toml":
        battery = load_battery(target)
        battery_dir = target.parent
        copies = [
            (
                e.exp_id,
                Path(e.path) if Path(e.path).is_absolute() else (battery_dir / e.path).resolve(),
            )
            for e in battery.experiments
        ]
        battery_file = target.name
    elif target.is_dir() and (target / "manifest.toml").exists():
        loaded = ExperimentLoader().load(target)
        battery = None
        copies = [(loaded.manifest.experiment.exp_id, target)]
        battery_file = None
        battery_dir = target.parent
    else:
        typer.echo(f"{target} is neither battery.toml nor an experiment dir", err=True)
        raise typer.Exit(code=2)

    # Validate each experiment
    for _eid, p in copies:
        ExperimentLoader().load(p)

    # Compute manifest hash (content provenance label)
    h = hashlib.sha256()
    for _eid, p in copies:
        for f in sorted(p.rglob("*")):
            if f.is_file():
                h.update(f.read_bytes())
    if battery_file:
        h.update((battery_dir / battery_file).read_bytes())
    manifest_hash = h.hexdigest()[:16]

    # Build the Dockerfile body
    lines = [f"FROM {base_tag}"]
    for eid, p in copies:
        # Use COPY <relative-to-Dockerfile> /experiments/<eid>
        rel = p.relative_to(battery_dir) if p.is_relative_to(battery_dir) else p
        lines.append(f"COPY ./{rel} /experiments/{eid}")
    if battery_file:
        lines.append(f"COPY ./{battery_file} /experiments/{battery_file}")
        lines.append(f"ENV EXPDEPLOY_BATTERY=/experiments/{battery_file}")
        cmd = f'CMD ["run", "/experiments/{battery_file}"]'
    else:
        eid = copies[0][0]
        cmd = f'CMD ["run", "/experiments/{eid}"]'
    lines.append(f'LABEL org.expdeploy.manifest_hash="{manifest_hash}"')
    lines.append(f'LABEL org.expdeploy.deploy_version="{__version__}"')
    lines.append(cmd)

    dockerfile_path = (output if output else (battery_dir / "study.Dockerfile")).resolve()
    dockerfile_path.write_text("\n".join(lines) + "\n")
    typer.echo(f"Wrote {dockerfile_path}")

    # Invoke the engine
    build_cmd = [engine, "build", "-f", str(dockerfile_path), "-t", tag, str(battery_dir)]
    typer.echo(" ".join(build_cmd))
    proc = subprocess.run(build_cmd, check=False)
    if proc.returncode != 0:
        typer.echo(f"{engine} build failed (exit {proc.returncode})", err=True)
        raise typer.Exit(code=proc.returncode)

    if push:
        push_cmd = [engine, "push", tag]
        typer.echo(" ".join(push_cmd))
        proc = subprocess.run(push_cmd, check=False)
        if proc.returncode != 0:
            typer.echo(f"{engine} push failed (exit {proc.returncode})", err=True)
            raise typer.Exit(code=proc.returncode)

    typer.echo(f"Built {tag}")


@init_app.command("experiment")
def init_experiment(
    target: Annotated[Path, typer.Argument(help="Directory to create")],
    task: Annotated[str, typer.Option("--task", help="BIDS task label (alphanumeric)")] = "task",
    type_: Annotated[str, typer.Option("--type", help="behavioral | fmri | none")] = "none",
) -> None:
    target.mkdir(parents=True, exist_ok=False)
    manifest_lines = [
        "[experiment]",
        f'exp_id = "{task}"',
        f'name = "{task.capitalize()}"',
        'version = "0.1.0"',
        'entry = "index.js"',
        'style = "style.css"',
        "",
        "[jspsych]",
        'version = "8.2.3"',
        'plugins = ["@jspsych/plugin-html-keyboard-response@2.1.0"]',
    ]
    if type_ in ("behavioral", "fmri"):
        manifest_lines += [
            "",
            "[bids]",
            f'type = "{type_}"',
            f'task = "{task}"',
        ]
    (target / "manifest.toml").write_text("\n".join(manifest_lines) + "\n")
    (target / "index.js").write_text(
        """import { initJsPsych } from "jspsych";
import htmlKeyboardResponse from "@jspsych/plugin-html-keyboard-response";

export default function build() {
  const startedAt = new Date().toISOString();
  const jsPsych = initJsPsych({
    on_finish: () => {
      window.expdeploy.submit({
        exp_id: window.expdeploy.expId,
        subject_id: window.expdeploy.subjectId,
        started_at: startedAt,
        ended_at: new Date().toISOString(),
        trials: jsPsych.data.get().values(),
        status: "finished",
      });
    },
  });
  jsPsych.run([
    { type: htmlKeyboardResponse, stimulus: "<h1>"""
        + task
        + """</h1><p>Press any key.</p>" },
  ]);
}
"""
    )
    (target / "style.css").write_text(
        "body { font-family: system-ui, sans-serif; text-align: center; margin-top: 4em; }\n"
    )
    typer.echo(f"Created {target}")


@init_app.command("battery")
def init_battery(
    target: Annotated[Path, typer.Argument(help="Directory to create")],
    experiments: Annotated[
        str, typer.Option("--experiments", help="Comma-delimited experiment dirs")
    ],
    counterbalance: Annotated[str, typer.Option("--counterbalance")] = "latin_square",
) -> None:
    target.mkdir(parents=True, exist_ok=False)
    paths = [Path(p).expanduser().resolve() for p in experiments.split(",") if p.strip()]
    rows: list[str] = []
    for p in paths:
        loaded = ExperimentLoader().load(p)
        eid = loaded.manifest.experiment.exp_id
        rows.append(f'[[experiments]]\nexp_id = "{eid}"\npath = "{p}"\n')
    body = (
        "[battery]\n"
        f'name = "{target.name}"\n'
        f'counterbalance = "{counterbalance}"\n\n' + "\n".join(rows)
    )
    (target / "battery.toml").write_text(body)
    typer.echo(f"Created {target / 'battery.toml'}")
