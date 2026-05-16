"""FastAPI app factory and route handlers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from expdeploy import __version__
from expdeploy.battery.counterbalance import CounterbalanceStrategy
from expdeploy.battery.orchestrator import BatteryOrchestrator
from expdeploy.importmap import ImportMapBuilder
from expdeploy.loader import LoadedExperiment
from expdeploy.manifest import BatteryManifest
from expdeploy.renderer import render_experiment_html
from expdeploy.session import RunSession
from expdeploy.storage.base import RunRecord, StorageAdapter

COMPLETE_HTML = """<!DOCTYPE html>
<html><body style="text-align:center;margin-top:4em;font-family:system-ui,sans-serif;">
<h1>Battery complete</h1>
<p>All experiments finished. You may close this tab.</p>
</body></html>
"""


@dataclass(frozen=True, slots=True)
class AppConfig:
    """A single-experiment OR battery deployment config.

    Exactly one of `experiment` or `(battery_manifest, experiments_by_id)` is set.
    """

    vendored_root: Path
    storage: StorageAdapter  # primary always-on (FSAdapter)
    catalog: StorageAdapter | None  # SQLiteCatalog or None
    state_dir: Path  # for RunSession
    subject_id: str
    session_num: str | None
    run_num: str | None

    # Single-experiment mode
    experiment: LoadedExperiment | None = None

    # Battery mode
    battery_manifest: BatteryManifest | None = None
    experiments_by_id: dict[str, LoadedExperiment] | None = None
    counterbalance_strategy: CounterbalanceStrategy | None = None

    def is_battery(self) -> bool:
        return self.battery_manifest is not None


def create_app(config: AppConfig) -> FastAPI:
    app = FastAPI(title="expdeploy", version=__version__)

    builder = ImportMapBuilder(vendored_root=config.vendored_root)

    # Mount vendored jsPsych once (single version for now).
    if config.is_battery():
        assert config.experiments_by_id is not None
        any_exp = next(iter(config.experiments_by_id.values()))
    else:
        assert config.experiment is not None
        any_exp = config.experiment
    jspsych_version = any_exp.manifest.jspsych.version
    jspsych_dir = config.vendored_root / jspsych_version
    if not jspsych_dir.is_dir():
        msg = f"jsPsych version {jspsych_version} not vendored"
        raise LookupError(msg)
    app.mount(
        f"/static/jspsych/{jspsych_version}",
        StaticFiles(directory=str(jspsych_dir)),
        name="static-jspsych",
    )

    # Mount each experiment dir.
    if config.is_battery():
        assert config.experiments_by_id is not None
        for exp_id, loaded in config.experiments_by_id.items():
            app.mount(
                f"/static/exp/{exp_id}",
                StaticFiles(directory=str(loaded.path)),
                name=f"static-experiment-{exp_id}",
            )
    else:
        assert config.experiment is not None
        exp_id_single = config.experiment.manifest.experiment.exp_id
        app.mount(
            f"/static/exp/{exp_id_single}",
            StaticFiles(directory=str(config.experiment.path)),
            name="static-experiment",
        )

    # Orchestrator (battery mode only)
    orchestrator: BatteryOrchestrator | None = None
    if config.is_battery():
        assert config.battery_manifest is not None and config.counterbalance_strategy is not None
        session = RunSession(state_dir=config.state_dir, subject_id=config.subject_id)
        orchestrator = BatteryOrchestrator(
            manifest=config.battery_manifest,
            strategy=config.counterbalance_strategy,
            session=session,
        )
        orchestrator.start()

    def _render_for(loaded: LoadedExperiment) -> str:
        exp_id = loaded.manifest.experiment.exp_id
        import_map = builder.build(
            loaded,
            jspsych_url_prefix=f"/static/jspsych/{jspsych_version}",
            experiment_url_prefix=f"/static/exp/{exp_id}",
        )
        style_url = (
            f"/static/exp/{exp_id}/{loaded.manifest.experiment.style}"
            if loaded.manifest.experiment.style
            else None
        )
        return render_experiment_html(
            exp_id=exp_id,
            experiment_entry_url=f"/static/exp/{exp_id}/{loaded.manifest.experiment.entry}",
            style_url=style_url,
            jspsych_css_url=f"/static/jspsych/{jspsych_version}/jspsych.css",
            import_map=import_map,
            runtime_globals={
                "expId": exp_id,
                "subjectId": config.subject_id,
                "sessionNum": config.session_num,
                "runNum": config.run_num,
                "deployVersion": __version__,
            },
            post_url="/api/data",
        )

    @app.get("/", response_class=HTMLResponse)
    def serve_root() -> HTMLResponse:
        if orchestrator is not None:
            ref = orchestrator.next_experiment()
            if ref is None:
                return HTMLResponse(content=COMPLETE_HTML)
            assert config.experiments_by_id is not None
            loaded = config.experiments_by_id[ref.exp_id]
            return HTMLResponse(content=_render_for(loaded))
        assert config.experiment is not None
        return HTMLResponse(content=_render_for(config.experiment))

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        return {"status": "ready"}

    @app.get("/api/state")
    def get_state() -> JSONResponse:
        if orchestrator is None:
            assert config.experiment is not None
            exp_id = config.experiment.manifest.experiment.exp_id
            return JSONResponse({"current": exp_id, "completed": [], "order": [exp_id]})
        session = orchestrator.session
        return JSONResponse(
            {
                "current": session.current(),
                "completed": session.completed(),
                "order": [e.exp_id for e in orchestrator.manifest.experiments],
                "battery_id": orchestrator.battery_id,
            }
        )

    @app.post("/api/state")
    def update_state(action: dict[str, Any]) -> JSONResponse:
        if orchestrator is None:
            raise HTTPException(status_code=400, detail="not a battery deployment")
        op = action.get("op")
        if op == "reset":
            orchestrator.session.reset()
            orchestrator.start()
        elif op == "skip":
            orchestrator.advance()
        else:
            raise HTTPException(status_code=400, detail=f"unknown op {op!r}")
        return JSONResponse({"current": orchestrator.session.current()})

    @app.post("/api/data")
    def post_data(payload: dict[str, Any]) -> JSONResponse:
        try:
            record = RunRecord(
                exp_id=payload.get("exp_id", ""),
                subject_id=payload.get("subject_id") or config.subject_id,
                session_num=payload.get("session_num") or config.session_num,
                run_num=payload.get("run_num") or config.run_num,
                battery_id=(orchestrator.battery_id if orchestrator else None),
                started_at=payload["started_at"],
                ended_at=payload["ended_at"],
                status=payload.get("status", "finished"),
                trials=payload.get("trials", []),
                interaction_data=payload.get("interaction_data", []),
                jspsych_version=payload.get("jspsych_version"),
                deploy_version=payload.get("deploy_version"),
                client_user_agent=payload.get("client_user_agent"),
                raw_payload=payload,
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        result = config.storage.save(record)
        if not result.ok:
            raise HTTPException(status_code=500, detail=result.error or "save failed")
        # SQLite catalog write (best-effort but synchronous)
        if config.catalog is not None:
            config.catalog.save(record)
        # BIDS write if applicable
        loaded = _find_loaded(config, record.exp_id)
        if (
            loaded is not None
            and loaded.manifest.bids is not None
            and hasattr(config.storage, "save_bids")
        ):
            config.storage.save_bids(record, loaded.manifest)
        # Advance battery
        if orchestrator is not None:
            orchestrator.advance()
        return JSONResponse({"ok": True, "path": result.path})

    return app


def _find_loaded(config: AppConfig, exp_id: str | None) -> LoadedExperiment | None:
    if exp_id is None:
        return None
    if config.experiments_by_id is not None:
        return config.experiments_by_id.get(exp_id)
    if config.experiment is not None and config.experiment.manifest.experiment.exp_id == exp_id:
        return config.experiment
    return None
