"""End-to-end test: Playwright drives a real browser through hello-world."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
HELLO_DIR = REPO / "examples" / "hello_world"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_healthz(url: str, timeout_seconds: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code == 200:
                return
        except Exception as exc:
            last_exc = exc
        time.sleep(0.25)
    msg = f"server at {url} never became healthy"
    if last_exc is not None:
        msg += f" (last error: {last_exc})"
    raise TimeoutError(msg)


@pytest.mark.e2e
def test_hello_world_browser_round_trip(tmp_path):
    port = _free_port()
    data_dir = tmp_path / "data"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "expdeploy",
            "run",
            str(HELLO_DIR),
            "--subject",
            "01",
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
            page.goto(f"http://127.0.0.1:{port}/")
            # Wait for the jsPsych target to render the stimulus
            page.wait_for_selector("text=Hello, world!", timeout=10_000)
            # Press a key — Space is fine; html-keyboard-response accepts any.
            page.keyboard.press("Space")
            # Wait for the "Saved." confirmation rendered by index.js
            page.wait_for_selector("text=Saved.", timeout=10_000)
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    # Verify the run was saved to disk
    saved_files = list((data_dir / "raw" / "sub-01").glob("*.json"))
    assert len(saved_files) == 1, f"expected one saved run, got {saved_files}"
    saved = json.loads(saved_files[0].read_text())
    # The single trial should be present in the payload
    trials = saved["trials"]
    assert len(trials) == 1
    assert trials[0]["trial_type"] == "html-keyboard-response"
