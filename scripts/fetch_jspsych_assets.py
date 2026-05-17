"""Bundle jsPsych v8 + plugins as self-contained ESM via npm + esbuild. Run: uv run python scripts/fetch_jspsych_assets.py"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

JSPSYCH_VERSION = "8.2.3"
PLUGIN_VERSION = "2.1.0"

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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir_str:
        tmpdir = Path(tmpdir_str)

        # Build package.json with all dependencies
        deps: dict[str, str] = {"jspsych": JSPSYCH_VERSION}
        for plugin in PLUGINS:
            deps[f"@jspsych/plugin-{plugin}"] = PLUGIN_VERSION

        package_json = {
            "name": "jspsych-bundle-workspace",
            "version": "1.0.0",
            "private": True,
            "dependencies": deps,
        }
        (tmpdir / "package.json").write_text(json.dumps(package_json, indent=2) + "\n")

        # npm install
        print("Running npm install...")
        subprocess.run(
            ["npm", "install", "--no-audit", "--no-fund", "--silent"],
            cwd=tmpdir,
            check=True,
        )
        print("npm install done.")

        # Wipe existing vendored assets
        shutil.rmtree(ASSETS_ROOT, ignore_errors=True)
        ASSETS_ROOT.mkdir(parents=True)
        (ASSETS_ROOT / "plugins").mkdir()

        manifest: dict[str, dict[str, str]] = {}

        # --- Bundle jsPsych core (named exports only, no default) ---
        core_entry = tmpdir / "entry-jspsych.js"
        core_entry.write_text("export * from 'jspsych';\n")
        core_out = ASSETS_ROOT / "jspsych.js"
        print("Bundling jspsych core...")
        result = subprocess.run(
            [
                "npx",
                "--yes",
                "esbuild",
                str(core_entry),
                "--bundle",
                "--format=esm",
                "--platform=browser",
                "--target=es2022",
                f"--outfile={core_out}",
            ],
            cwd=tmpdir,
            capture_output=True,
            text=True,
        )
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        if result.returncode != 0:
            print(
                f"ERROR: esbuild failed for jspsych core (exit {result.returncode})",
                file=sys.stderr,
            )
            return 1
        manifest["jspsych"] = {
            "version": JSPSYCH_VERSION,
            "esm": "jspsych.js",
            "css": "jspsych.css",
            "sha256_esm": sha256(core_out),
        }
        print(f"  -> {core_out} ({core_out.stat().st_size:,} bytes)")

        # --- Bundle each plugin (default export shim) ---
        for plugin in PLUGINS:
            pkg_name = f"@jspsych/plugin-{plugin}"
            entry = tmpdir / f"entry-plugin-{plugin}.js"
            entry.write_text(f"import plugin from '{pkg_name}';\nexport default plugin;\n")
            out = ASSETS_ROOT / "plugins" / f"{plugin}.js"
            print(f"Bundling {pkg_name}...")
            result = subprocess.run(
                [
                    "npx",
                    "--yes",
                    "esbuild",
                    str(entry),
                    "--bundle",
                    "--format=esm",
                    "--platform=browser",
                    "--target=es2022",
                    "--external:jspsych",
                    f"--outfile={out}",
                ],
                cwd=tmpdir,
                capture_output=True,
                text=True,
            )
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
            if result.returncode != 0:
                print(
                    f"ERROR: esbuild failed for {pkg_name} (exit {result.returncode})",
                    file=sys.stderr,
                )
                return 1
            manifest[pkg_name] = {
                "version": PLUGIN_VERSION,
                "esm": f"plugins/{plugin}.js",
                "sha256_esm": sha256(out),
            }
            print(f"  -> {out} ({out.stat().st_size:,} bytes)")

        # --- Copy CSS ---
        css_src = tmpdir / "node_modules" / "jspsych" / "css" / "jspsych.css"
        css_dest = ASSETS_ROOT / "jspsych.css"
        shutil.copy2(css_src, css_dest)
        print(f"  Copied CSS: {css_dest} ({css_dest.stat().st_size:,} bytes)")

    # --- Write manifest ---
    manifest_path = ASSETS_ROOT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    # --- Ensure __init__.py exists ---
    package_init = ASSETS_ROOT.parent / "__init__.py"
    if not package_init.exists():
        package_init.write_text(
            '"""Vendored jsPsych ESM assets. Populated by scripts/fetch_jspsych_assets.py."""\n'
        )

    print(f"\nWrote {len(manifest)} entries to {manifest_path}")
    print(
        "Done — core is self-contained ESM; plugins reference jspsych as an external import resolved via import map."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
