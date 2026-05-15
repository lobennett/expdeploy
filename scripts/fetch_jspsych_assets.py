"""Fetch jsPsych v8 + plugin ESM bundles from unpkg into src/expdeploy/jspsych_assets/.

Run: uv run python scripts/fetch_jspsych_assets.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path

JSPSYCH_VERSION = "8.2.3"
PLUGIN_VERSION = "2.1.0"  # matches jsPsych 8.x

PLUGINS = [
    "html-keyboard-response",
    "html-button-response",
    "image-keyboard-response",
    "image-button-response",
    "fullscreen",
    "instructions",
    "preload",
    "call-function",
    "survey-text",
]

ROOT = Path(__file__).resolve().parent.parent
ASSETS_ROOT = ROOT / "src" / "expdeploy" / "jspsych_assets" / JSPSYCH_VERSION


def fetch(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  GET  {url}")
    with urllib.request.urlopen(url, timeout=30) as resp:
        dest.write_bytes(resp.read())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if ASSETS_ROOT.exists():
        print(f"Cleaning existing {ASSETS_ROOT}")
        shutil.rmtree(ASSETS_ROOT)
    ASSETS_ROOT.mkdir(parents=True)

    manifest: dict[str, dict[str, str]] = {}

    # Core jsPsych: ESM build + CSS
    fetch(
        f"https://unpkg.com/jspsych@{JSPSYCH_VERSION}/dist/index.js",
        ASSETS_ROOT / "jspsych.js",
    )
    fetch(
        f"https://unpkg.com/jspsych@{JSPSYCH_VERSION}/css/jspsych.css",
        ASSETS_ROOT / "jspsych.css",
    )
    manifest["jspsych"] = {
        "version": JSPSYCH_VERSION,
        "esm": "jspsych.js",
        "css": "jspsych.css",
        "sha256_esm": sha256(ASSETS_ROOT / "jspsych.js"),
    }

    # Plugins
    plugins_dir = ASSETS_ROOT / "plugins"
    plugins_dir.mkdir()
    for plugin in PLUGINS:
        url = f"https://unpkg.com/@jspsych/plugin-{plugin}@{PLUGIN_VERSION}/dist/index.js"
        dest = plugins_dir / f"{plugin}.js"
        fetch(url, dest)
        manifest[f"@jspsych/plugin-{plugin}"] = {
            "version": PLUGIN_VERSION,
            "esm": f"plugins/{plugin}.js",
            "sha256_esm": sha256(dest),
        }

    # Write a manifest so loader.py can introspect what's vendored
    (ASSETS_ROOT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )

    # Make `from expdeploy import jspsych_assets` work
    package_init = ASSETS_ROOT.parent / "__init__.py"
    if not package_init.exists():
        package_init.write_text(
            '"""Vendored jsPsych ESM assets. Populated by scripts/fetch_jspsych_assets.py."""\n'
        )

    print(f"\nWrote {len(manifest)} entries to {ASSETS_ROOT / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
