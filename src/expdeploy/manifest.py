"""Pydantic models for manifest.toml and battery.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Annotated, Literal

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


CounterbalanceName = Literal["fixed", "latin_square", "seeded_random", "user_supplied"]


class BatteryBreakConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_seconds: int = Field(ge=0)
    message: str = ""


class BatteryBreaks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    between_each: BatteryBreakConfig | None = None


class BatteryInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    counterbalance: CounterbalanceName = "fixed"
    order_csv: str | None = None


class BatteryExperimentRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exp_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$", max_length=128)
    path: str


class BatteryManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    battery: BatteryInfo
    experiments: list[BatteryExperimentRef]
    breaks: BatteryBreaks | None = None


def load_battery(path: Path) -> BatteryManifest:
    """Read a battery.toml from disk and return a validated BatteryManifest."""
    with path.open("rb") as fp:
        data = tomllib.load(fp)
    return BatteryManifest.model_validate(data)
