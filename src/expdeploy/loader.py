"""Loading experiment directories from disk."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from expdeploy.manifest import ExperimentManifest, load_manifest


@dataclass(frozen=True, slots=True)
class LoadedExperiment:
    """An experiment directory after manifest validation."""

    path: Path
    manifest: ExperimentManifest

    @property
    def entry_path(self) -> Path:
        return (self.path / self.manifest.experiment.entry).resolve()

    @property
    def style_path(self) -> Path | None:
        style = self.manifest.experiment.style
        if style is None:
            return None
        return (self.path / style).resolve()


class ExperimentLoader:
    """Loads + validates an experiment directory."""

    def load(self, exp_dir: Path) -> LoadedExperiment:
        exp_dir = Path(exp_dir).resolve()
        manifest_path = exp_dir / "manifest.toml"
        if not manifest_path.is_file():
            msg = f"manifest.toml not found in {exp_dir}"
            raise FileNotFoundError(msg)
        manifest = load_manifest(manifest_path)
        entry_path = exp_dir / manifest.experiment.entry
        if not entry_path.is_file():
            msg = f"entry file not found: {entry_path}"
            raise FileNotFoundError(msg)
        return LoadedExperiment(path=exp_dir, manifest=manifest)
