"""Tests for expdeploy.importmap.ImportMapBuilder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from expdeploy.importmap import ImportMapBuilder
from expdeploy.loader import ExperimentLoader

HELLO_TOML = """
[experiment]
exp_id = "hello"
name = "Hello world"
version = "1.0.0"
entry = "index.js"

[jspsych]
version = "8.2.3"
plugins = ["@jspsych/plugin-html-keyboard-response@2.1.0"]

[import_map_extras]
"@lab/iti" = "./lib/iti.js"
"""


def _make_hello(tmp_path):
    exp_dir = tmp_path / "hello"
    exp_dir.mkdir()
    (exp_dir / "manifest.toml").write_text(HELLO_TOML)
    (exp_dir / "index.js").write_text("export default () => {};")
    (exp_dir / "lib").mkdir()
    (exp_dir / "lib" / "iti.js").write_text("export const sampleITI = () => 500;")
    return exp_dir


def _vendored_assets_root() -> Path:
    """Find the real vendored jsPsych assets root (committed in Task 8)."""
    from expdeploy import jspsych_assets

    return Path(jspsych_assets.__file__).resolve().parent


def test_import_map_contains_jspsych_and_plugin(tmp_path):
    loaded = ExperimentLoader().load(_make_hello(tmp_path))
    builder = ImportMapBuilder(vendored_root=_vendored_assets_root())
    import_map = builder.build(
        loaded,
        jspsych_url_prefix="/static/jspsych/8.2.3",
        experiment_url_prefix="/static/exp/hello",
    )
    imports = import_map["imports"]
    assert imports["jspsych"] == "/static/jspsych/8.2.3/jspsych.js"
    assert imports["@jspsych/plugin-html-keyboard-response"] == (
        "/static/jspsych/8.2.3/plugins/html-keyboard-response.js"
    )


def test_import_map_includes_extras(tmp_path):
    loaded = ExperimentLoader().load(_make_hello(tmp_path))
    builder = ImportMapBuilder(vendored_root=_vendored_assets_root())
    import_map = builder.build(
        loaded,
        jspsych_url_prefix="/static/jspsych/8.2.3",
        experiment_url_prefix="/static/exp/hello",
    )
    assert import_map["imports"]["@lab/iti"] == "/static/exp/hello/lib/iti.js"


def test_import_map_is_json_serializable(tmp_path):
    loaded = ExperimentLoader().load(_make_hello(tmp_path))
    builder = ImportMapBuilder(vendored_root=_vendored_assets_root())
    import_map = builder.build(
        loaded,
        jspsych_url_prefix="/static/jspsych/8.2.3",
        experiment_url_prefix="/static/exp/hello",
    )
    # Must round-trip through json.dumps without raising
    json.dumps(import_map)


def test_import_map_rejects_unvendored_jspsych_version(tmp_path):
    bad_toml = HELLO_TOML.replace('version = "8.2.3"', 'version = "9.99.99"')
    exp_dir = tmp_path / "hello"
    exp_dir.mkdir()
    (exp_dir / "manifest.toml").write_text(bad_toml)
    (exp_dir / "index.js").write_text("export default () => {};")
    loaded = ExperimentLoader().load(exp_dir)
    builder = ImportMapBuilder(vendored_root=_vendored_assets_root())
    with pytest.raises(LookupError) as excinfo:
        builder.build(
            loaded,
            jspsych_url_prefix="/static/jspsych/9.99.99",
            experiment_url_prefix="/static/exp/hello",
        )
    assert "9.99.99" in str(excinfo.value)
