"""E2E: Playwright drives through a 2-experiment battery."""

from __future__ import annotations

import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
BATTERY = REPO / "examples" / "mini_battery" / "battery.toml"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_healthz(url: str, timeout_seconds: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.25)
    raise TimeoutError(f"{url} never healthy")


@pytest.mark.e2e
def test_battery_round_trip_two_experiments(tmp_path):
    port = _free_port()
    data_dir = tmp_path / "data"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "expdeploy",
            "run",
            str(BATTERY),
            "--subject",
            "0",
            "--data-dir",
            str(data_dir),
            "--port",
            str(port),
            "--no-browser",
        ],
        cwd=str(REPO),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_for_healthz(f"http://127.0.0.1:{port}/healthz")

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            # Flanker
            page.goto(f"http://127.0.0.1:{port}/")
            page.wait_for_selector("text=Flanker", timeout=10_000)
            page.keyboard.press("Space")
            # Brief wait then a reload happens automatically (index.js)
            # Stroop
            page.wait_for_selector("text=Stroop", timeout=15_000)
            page.keyboard.press("Space")
            # Battery complete screen
            page.wait_for_selector("text=Battery complete", timeout=15_000)
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    # Verify SQLite catalog has two runs
    conn = sqlite3.connect(data_dir / "catalog.sqlite")
    rows = conn.execute("SELECT exp_id FROM runs ORDER BY started_at ASC").fetchall()
    conn.close()
    exp_ids = [r[0] for r in rows]
    assert exp_ids == ["flanker", "stroop"]

    # Verify raw files exist for both
    flanker_files = list((data_dir / "raw" / "sub-0").glob("*task-flanker*.json"))
    stroop_files = list((data_dir / "raw" / "sub-0").glob("*task-stroop*.json"))
    assert len(flanker_files) == 1
    assert len(stroop_files) == 1
