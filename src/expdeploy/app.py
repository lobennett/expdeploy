"""FastAPI app factory and route handlers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from expdeploy import __version__
from expdeploy.importmap import ImportMapBuilder
from expdeploy.loader import LoadedExperiment
from expdeploy.renderer import render_experiment_html
from expdeploy.storage.base import RunRecord, StorageAdapter


@dataclass(frozen=True, slots=True)
class AppConfig:
    experiment: LoadedExperiment
    vendored_root: Path
    storage: StorageAdapter
    subject_id: str
    session_num: str | None
    run_num: str | None


def create_app(config: AppConfig) -> FastAPI:
    app = FastAPI(title="expdeploy", version=__version__)

    exp = config.experiment
    exp_id = exp.manifest.experiment.exp_id
    jspsych_version = exp.manifest.jspsych.version
    jspsych_dir = config.vendored_root / jspsych_version
    if not jspsych_dir.is_dir():
        msg = f"jsPsych version {jspsych_version} not vendored"
        raise LookupError(msg)

    app.mount(
        f"/static/jspsych/{jspsych_version}",
        StaticFiles(directory=str(jspsych_dir)),
        name="static-jspsych",
    )
    app.mount(
        f"/static/exp/{exp_id}",
        StaticFiles(directory=str(exp.path)),
        name="static-experiment",
    )

    builder = ImportMapBuilder(vendored_root=config.vendored_root)

    @app.get("/", response_class=HTMLResponse)
    def serve_root() -> HTMLResponse:
        import_map = builder.build(
            exp,
            jspsych_url_prefix=f"/static/jspsych/{jspsych_version}",
            experiment_url_prefix=f"/static/exp/{exp_id}",
        )
        style_url = (
            f"/static/exp/{exp_id}/{exp.manifest.experiment.style}"
            if exp.manifest.experiment.style
            else None
        )
        html = render_experiment_html(
            exp_id=exp_id,
            experiment_entry_url=f"/static/exp/{exp_id}/{exp.manifest.experiment.entry}",
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
        return HTMLResponse(content=html)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        return {"status": "ready"}

    @app.post("/api/data")
    def post_data(payload: dict[str, Any]) -> JSONResponse:
        try:
            record = RunRecord(
                exp_id=payload.get("exp_id", exp_id),
                subject_id=payload.get("subject_id") or config.subject_id,
                session_num=payload.get("session_num") or config.session_num,
                run_num=payload.get("run_num") or config.run_num,
                raw_payload=payload,
            )
        except Exception as exc:  # Pydantic ValidationError surfaces here
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        result = config.storage.save(record)
        if not result.ok:
            raise HTTPException(status_code=500, detail=result.error or "save failed")
        return JSONResponse({"ok": True, "path": result.path})

    return app
