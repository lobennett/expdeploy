"""Tests for expdeploy.renderer.render_experiment_html."""

from __future__ import annotations

import json
import re

from expdeploy.renderer import render_experiment_html


def test_html_contains_import_map():
    html = render_experiment_html(
        exp_id="hello",
        experiment_entry_url="/static/exp/hello/index.js",
        style_url=None,
        jspsych_css_url="/static/jspsych/8.2.3/jspsych.css",
        import_map={"imports": {"jspsych": "/static/jspsych/8.2.3/jspsych.js"}},
        runtime_globals={"subjectId": "01", "sessionNum": "1", "runNum": "1"},
        post_url="/api/data",
    )
    # Find the import map script
    match = re.search(
        r'<script\s+type="importmap"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match is not None
    payload = json.loads(match.group(1))
    assert payload["imports"]["jspsych"] == "/static/jspsych/8.2.3/jspsych.js"


def test_html_injects_window_expdeploy():
    html = render_experiment_html(
        exp_id="hello",
        experiment_entry_url="/static/exp/hello/index.js",
        style_url=None,
        jspsych_css_url="/static/jspsych/8.2.3/jspsych.css",
        import_map={"imports": {}},
        runtime_globals={"subjectId": "01"},
        post_url="/api/data",
    )
    assert "window.expdeploy" in html
    assert '"subjectId":"01"' in html or '"subjectId": "01"' in html


def test_html_loads_experiment_entry_as_module():
    html = render_experiment_html(
        exp_id="hello",
        experiment_entry_url="/static/exp/hello/index.js",
        style_url=None,
        jspsych_css_url="/static/jspsych/8.2.3/jspsych.css",
        import_map={"imports": {}},
        runtime_globals={},
        post_url="/api/data",
    )
    # The experiment entry is imported as an ES module
    assert "/static/exp/hello/index.js" in html
    assert 'type="module"' in html


def test_html_optionally_includes_style():
    html_with = render_experiment_html(
        exp_id="hello",
        experiment_entry_url="/static/exp/hello/index.js",
        style_url="/static/exp/hello/style.css",
        jspsych_css_url="/static/jspsych/8.2.3/jspsych.css",
        import_map={"imports": {}},
        runtime_globals={},
        post_url="/api/data",
    )
    assert "/static/exp/hello/style.css" in html_with

    html_without = render_experiment_html(
        exp_id="hello",
        experiment_entry_url="/static/exp/hello/index.js",
        style_url=None,
        jspsych_css_url="/static/jspsych/8.2.3/jspsych.css",
        import_map={"imports": {}},
        runtime_globals={},
        post_url="/api/data",
    )
    assert "style.css" not in html_without
