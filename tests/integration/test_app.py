"""Integration tests for the FastAPI app — TestClient against tmp_path fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from expdeploy import jspsych_assets
from expdeploy.app import AppConfig, create_app
from expdeploy.battery.counterbalance import FixedStrategy
from expdeploy.loader import ExperimentLoader
from expdeploy.manifest import BatteryExperimentRef, BatteryInfo, BatteryManifest
from expdeploy.storage.fs import FSAdapter
from expdeploy.storage.sqlite import SQLiteCatalog

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
        vendored_root=_vendored_root(),
        storage=FSAdapter(data_dir=data_dir),
        catalog=None,
        state_dir=tmp_path / "state",
        subject_id="01",
        session_num=None,
        run_num=None,
        experiment=ExperimentLoader().load(hello_experiment),
    )
    app = create_app(config)
    return TestClient(app), data_dir


def _two_exp_battery(tmp_path):
    """Build a fixture with two minimal experiments and a battery manifest."""
    exp_a = tmp_path / "ea"
    exp_a.mkdir()
    (exp_a / "manifest.toml").write_text(HELLO_TOML.replace('exp_id = "hello"', 'exp_id = "ea"'))
    (exp_a / "index.js").write_text("export default () => {};")

    exp_b = tmp_path / "eb"
    exp_b.mkdir()
    (exp_b / "manifest.toml").write_text(HELLO_TOML.replace('exp_id = "hello"', 'exp_id = "eb"'))
    (exp_b / "index.js").write_text("export default () => {};")

    battery = BatteryManifest(
        battery=BatteryInfo(name="t", counterbalance="fixed"),
        experiments=[
            BatteryExperimentRef(exp_id="ea", path=str(exp_a)),
            BatteryExperimentRef(exp_id="eb", path=str(exp_b)),
        ],
    )
    return battery, {"ea": ExperimentLoader().load(exp_a), "eb": ExperimentLoader().load(exp_b)}


@pytest.fixture
def battery_client(tmp_path):
    battery, exps = _two_exp_battery(tmp_path)
    data_dir = tmp_path / "data"
    catalog = SQLiteCatalog(db_path=data_dir / "catalog.sqlite")
    catalog.init_schema()
    config = AppConfig(
        vendored_root=_vendored_root(),
        storage=FSAdapter(data_dir=data_dir),
        catalog=catalog,
        state_dir=tmp_path / "state",
        subject_id="01",
        session_num=None,
        run_num=None,
        battery_manifest=battery,
        experiments_by_id=exps,
        counterbalance_strategy=FixedStrategy(),
    )
    app = create_app(config)
    return TestClient(app), data_dir, catalog


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
    client, _data_dir = app_client
    payload = {
        "exp_id": "hello",
        "subject_id": "01",
        "trials": [{"trial_type": "html-keyboard-response", "rt": 432}],
        "status": "finished",
        "started_at": "2026-05-15T10:00:00+00:00",
        "ended_at": "2026-05-15T10:01:00+00:00",
    }
    response = client.post("/api/data", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    saved_path = Path(body["path"])
    assert saved_path.exists()
    saved = json.loads(saved_path.read_text())
    assert saved["trials"][0]["rt"] == 432
    assert saved["run_id"]  # ULID present
    assert saved["status"] == "finished"


def test_post_data_rejects_invalid_subject(app_client):
    client, _ = app_client
    payload = {
        "exp_id": "hello",
        "subject_id": "../oops",
        "trials": [],
        "status": "finished",
        "started_at": "2026-05-15T10:00:00+00:00",
        "ended_at": "2026-05-15T10:01:00+00:00",
    }
    response = client.post("/api/data", json=payload)
    assert response.status_code == 422


def test_battery_get_root_serves_first_experiment(battery_client):
    client, _, _ = battery_client
    response = client.get("/")
    assert response.status_code == 200
    assert "/static/exp/ea/" in response.text


def test_battery_state_endpoint(battery_client):
    client, _, _ = battery_client
    r = client.get("/api/state")
    body = r.json()
    assert body["current"] == "ea"
    assert body["completed"] == []
    assert body["order"] == ["ea", "eb"]


def test_battery_post_data_advances(battery_client):
    client, data_dir, catalog = battery_client
    payload = {
        "exp_id": "ea",
        "subject_id": "01",
        "trials": [],
        "status": "finished",
        "started_at": "2026-05-15T10:00:00+00:00",
        "ended_at": "2026-05-15T10:01:00+00:00",
    }
    r = client.post("/api/data", json=payload)
    assert r.status_code == 200
    # State advanced
    r2 = client.get("/api/state")
    assert r2.json()["current"] == "eb"
    # SQLite has a row
    rows = catalog.recent_runs()
    assert len(rows) == 1
    assert rows[0]["exp_id"] == "ea"


def test_battery_serves_second_experiment_after_first(battery_client):
    client, _, _ = battery_client
    # Complete first
    client.post(
        "/api/data",
        json={
            "exp_id": "ea",
            "subject_id": "01",
            "trials": [],
            "status": "finished",
            "started_at": "2026-05-15T10:00:00+00:00",
            "ended_at": "2026-05-15T10:01:00+00:00",
        },
    )
    response = client.get("/")
    assert "/static/exp/eb/" in response.text


def test_battery_complete_screen_after_all(battery_client):
    client, _, _ = battery_client
    for exp_id in ["ea", "eb"]:
        client.post(
            "/api/data",
            json={
                "exp_id": exp_id,
                "subject_id": "01",
                "trials": [],
                "status": "finished",
                "started_at": "2026-05-15T10:00:00+00:00",
                "ended_at": "2026-05-15T10:01:00+00:00",
            },
        )
    response = client.get("/")
    assert response.status_code == 200
    assert "Battery complete" in response.text or "complete" in response.text.lower()
