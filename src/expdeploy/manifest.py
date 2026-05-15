"""Pydantic models for manifest.toml and battery.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExperimentMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")  # researchers add arbitrary keys

    cognitive_atlas_task_id: str | None = None
    contributors: list[str] = Field(default_factory=list)
    notes: str | None = None


class ExperimentInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exp_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$", max_length=128)
    name: str
    version: str = "0.1.0"
    entry: str = "index.js"
    style: str | None = None
    estimated_minutes: int | None = Field(default=None, ge=0)
    metadata: ExperimentMetadata = Field(default_factory=ExperimentMetadata)


class JsPsychConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    plugins: list[str] = Field(default_factory=list)
    init: dict[str, object] = Field(default_factory=dict)


class BidsColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    levels: dict[str, str] = Field(default_factory=dict)


BidsType = Annotated[str, Field(pattern=r"^(fmri|behavioral)$")]
BidsTaskLabel = Annotated[str, Field(pattern=r"^[a-zA-Z0-9]+$", max_length=64)]


class BidsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: BidsType
    task: BidsTaskLabel
    columns: dict[str, BidsColumn] = Field(default_factory=dict)


class ExperimentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment: ExperimentInfo
    jspsych: JsPsychConfig
    bids: BidsConfig | None = None
    import_map_extras: dict[str, str] = Field(default_factory=dict)

    @field_validator("import_map_extras")
    @classmethod
    def _no_bare_keys(cls, value: dict[str, str]) -> dict[str, str]:
        for key in value:
            if not key.strip():
                msg = "import_map_extras keys must not be empty"
                raise ValueError(msg)
        return value


def load_manifest(path: Path) -> ExperimentManifest:
    """Read a manifest.toml from disk and return a validated ExperimentManifest."""
    with path.open("rb") as fp:
        data = tomllib.load(fp)
    return ExperimentManifest.model_validate(data)
