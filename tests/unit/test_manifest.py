"""Tests for expdeploy.manifest — Pydantic models for manifest.toml."""

from __future__ import annotations

import tomllib

from expdeploy.manifest import ExperimentManifest

HELLO_TOML = """
[experiment]
exp_id = "hello"
name = "Hello world"
version = "1.0.0"
entry = "index.js"
estimated_minutes = 1

[jspsych]
version = "8.2.3"
plugins = ["@jspsych/plugin-html-keyboard-response@2.1.0"]
init = { fullscreen = false }
"""


def test_minimal_manifest_parses():
    data = tomllib.loads(HELLO_TOML)
    manifest = ExperimentManifest.model_validate(data)
    assert manifest.experiment.exp_id == "hello"
    assert manifest.experiment.name == "Hello world"
    assert manifest.experiment.entry == "index.js"
    assert manifest.jspsych.version == "8.2.3"
    assert manifest.jspsych.plugins == ["@jspsych/plugin-html-keyboard-response@2.1.0"]
    assert manifest.bids is None
    assert manifest.import_map_extras == {}
