"""Integration tests for the FastAPI app — TestClient against tmp_path fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from expdeploy import jspsych_assets
from expdeploy.app import AppConfig, create_app
from expdeploy.loader import ExperimentLoader
from expdeploy.storage.fs import FSAdapter

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


HELLO_JS = """
import { initJsPsych } from 'jspsych';
import htmlKeyboardResponse from '@jspsych/plugin-html-keyboard-response';

export default function build() {
  const jsPsych = initJsPsych({
    on_finish: () => window.expdeploy.submit({
      exp_id: window.expdeploy.expId,
      subject_id: window.expdeploy.subjectId,
      trials: jsPsych.data.get().values(),
      status: 'finished',
    }),
  });
  jsPsych.run([{
    type: htmlKeyboardResponse,
    stimulus: '<p>Press any key.</p>',
  }]);
}
"""


def _vendored_root() -> Path:
    return Path(jspsych_assets.__file__).resolve().parent


@pytest.fixture
def hello_experiment(tmp_path):
    exp_dir = tmp_path / "hello"
    exp_dir.mkdir()
    (exp_dir / "manifest.toml").write_text(HELLO_TOML)
    (exp_dir / "index.js").write_text(HELLO_JS)
    return exp_dir


@pytest.fixture
def app_client(hello_experiment, tmp_path):
    data_dir = tmp_path / "data"
    config = AppConfig(
        experiment=ExperimentLoader().load(hello_experiment),
        vendored_root=_vendored_root(),
        storage=FSAdapter(data_dir=data_dir),
        subject_id="01",
        session_num=None,
        run_num=None,
    )
    app = create_app(config)
    return TestClient(app), data_dir


def test_root_returns_html(app_client):
    client, _ = app_client
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert "<!DOCTYPE html>" in body
    assert 'type="importmap"' in body
    assert "window.expdeploy" in body
    assert '"subjectId":"01"' in body or '"subjectId": "01"' in body


def test_healthz_returns_ok(app_client):
    client, _ = app_client
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_static_jspsych_asset_served(app_client):
    client, _ = app_client
    response = client.get("/static/jspsych/8.2.3/jspsych.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_static_experiment_index_js_served(app_client):
    client, _ = app_client
    response = client.get("/static/exp/hello/index.js")
    assert response.status_code == 200
    body = response.text
    assert "initJsPsych" in body


def test_post_data_writes_file(app_client):
    client, data_dir = app_client
    payload = {
        "exp_id": "hello",
        "subject_id": "01",
        "trials": [{"trial_type": "html-keyboard-response", "rt": 432}],
        "status": "finished",
    }
    response = client.post("/api/data", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    saved_path = Path(body["path"])
    assert saved_path.exists()
    saved = json.loads(saved_path.read_text())
    assert saved["trials"][0]["rt"] == 432


def test_post_data_rejects_invalid_subject(app_client):
    client, _ = app_client
    payload = {
        "exp_id": "hello",
        "subject_id": "../oops",
        "trials": [],
        "status": "finished",
    }
    response = client.post("/api/data", json=payload)
    assert response.status_code == 422
