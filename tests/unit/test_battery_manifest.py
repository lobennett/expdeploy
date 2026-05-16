"""Tests for the BatteryManifest Pydantic model + load_battery."""

from __future__ import annotations

import tomllib

import pytest
from pydantic import ValidationError

from expdeploy.manifest import BatteryManifest, load_battery

BATTERY_TOML = """
[battery]
name = "RDoC mini battery"
counterbalance = "latin_square"

[[experiments]]
exp_id = "flanker"
path = "./flanker"

[[experiments]]
exp_id = "stroop"
path = "./stroop"

[breaks]
between_each = { duration_seconds = 30, message = "Rest." }
"""


def test_battery_manifest_parses():
    data = tomllib.loads(BATTERY_TOML)
    m = BatteryManifest.model_validate(data)
    assert m.battery.name == "RDoC mini battery"
    assert m.battery.counterbalance == "latin_square"
    assert len(m.experiments) == 2
    assert m.experiments[0].exp_id == "flanker"
    assert m.experiments[0].path == "./flanker"
    assert m.breaks is not None
    assert m.breaks.between_each.duration_seconds == 30


def test_battery_rejects_unknown_counterbalance():
    bad = BATTERY_TOML.replace('"latin_square"', '"random"')
    with pytest.raises(ValidationError):
        BatteryManifest.model_validate(tomllib.loads(bad))


def test_load_battery_from_disk(tmp_path):
    p = tmp_path / "battery.toml"
    p.write_text(BATTERY_TOML)
    m = load_battery(p)
    assert m.battery.counterbalance == "latin_square"


def test_load_battery_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_battery(tmp_path / "nope.toml")
