"""Build browser-native import maps for served experiments."""

from __future__ import annotations

import json
import re
from pathlib import Path

from expdeploy.loader import LoadedExperiment

PLUGIN_NAME_RE = re.compile(r"^(@jspsych/plugin-[a-zA-Z0-9-]+)(?:@([\d.]+))?$")


class ImportMapBuilder:
    """Constructs a browser import map for a LoadedExperiment.

    The vendored_root is `src/expdeploy/jspsych_assets/`. Inside it, each
    available jsPsych version has its own subdir (e.g., `8.2.3/`) with a
    `manifest.json` describing what's available.
    """

    def __init__(self, vendored_root: Path) -> None:
        self.vendored_root = Path(vendored_root).resolve()

    def build(
        self,
        loaded: LoadedExperiment,
        *,
        jspsych_url_prefix: str,
        experiment_url_prefix: str,
    ) -> dict[str, dict[str, str]]:
        manifest = loaded.manifest
        version = manifest.jspsych.version
        version_dir = self.vendored_root / version
        if not version_dir.is_dir():
            available = sorted(p.name for p in self.vendored_root.iterdir() if p.is_dir())
            msg = f"jsPsych version {version} is not vendored. " f"Available versions: {available}"
            raise LookupError(msg)

        vendored_manifest_path = version_dir / "manifest.json"
        if not vendored_manifest_path.is_file():
            msg = f"Vendored manifest missing at {vendored_manifest_path}"
            raise LookupError(msg)
        vendored = json.loads(vendored_manifest_path.read_text())

        imports: dict[str, str] = {}

        # Core jsPsych
        imports["jspsych"] = f"{jspsych_url_prefix}/{vendored['jspsych']['esm']}"

        # Plugins declared in the experiment manifest
        for plugin_spec in manifest.jspsych.plugins:
            match = PLUGIN_NAME_RE.match(plugin_spec)
            if match is None:
                msg = f"Unrecognized plugin spec: {plugin_spec!r}"
                raise ValueError(msg)
            name = match.group(1)
            if name not in vendored:
                available_plugins = sorted(k for k in vendored if k.startswith("@jspsych/"))
                msg = f"Plugin not vendored: {name}. Available: {available_plugins}"
                raise LookupError(msg)
            imports[name] = f"{jspsych_url_prefix}/{vendored[name]['esm']}"

        # Experiment-local imports for bare ./ paths via the import map
        # (relative imports in index.js resolve automatically; this exposes
        # any aliases declared in import_map_extras)
        for alias, relative in manifest.import_map_extras.items():
            if relative.startswith("./"):
                url = f"{experiment_url_prefix}/{relative[2:]}"
            elif relative.startswith("/") or relative.startswith("http"):
                url = relative
            else:
                url = f"{experiment_url_prefix}/{relative}"
            imports[alias] = url

        return {"imports": imports}
