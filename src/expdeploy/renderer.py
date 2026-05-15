"""Render the HTML page that serves an experiment to the browser."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)


def render_experiment_html(
    *,
    exp_id: str,
    experiment_entry_url: str,
    style_url: str | None,
    jspsych_css_url: str,
    import_map: dict[str, Any],
    runtime_globals: dict[str, Any],
    post_url: str,
) -> str:
    template = _env.get_template("deploy.html.j2")
    return template.render(
        exp_id=exp_id,
        experiment_entry_url=experiment_entry_url,
        style_url=style_url,
        jspsych_css_url=jspsych_css_url,
        import_map=import_map,
        runtime_globals=runtime_globals,
        post_url=post_url,
    )
