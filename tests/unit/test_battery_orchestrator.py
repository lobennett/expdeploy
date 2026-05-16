"""Tests for expdeploy.battery.orchestrator.BatteryOrchestrator."""

from __future__ import annotations

from expdeploy.battery.counterbalance import FixedStrategy, LatinSquareStrategy
from expdeploy.battery.orchestrator import BatteryOrchestrator
from expdeploy.manifest import BatteryExperimentRef, BatteryInfo, BatteryManifest
from expdeploy.session import RunSession


def _battery(experiments: list[str], counterbalance: str = "fixed") -> BatteryManifest:
    return BatteryManifest(
        battery=BatteryInfo(name="b", counterbalance=counterbalance),  # type: ignore[arg-type]
        experiments=[BatteryExperimentRef(exp_id=e, path=f"./{e}") for e in experiments],
    )


def test_orchestrator_returns_first_in_order(tmp_path):
    session = RunSession(state_dir=tmp_path, subject_id="01")
    o = BatteryOrchestrator(
        manifest=_battery(["flanker", "stroop", "nback"]),
        strategy=FixedStrategy(),
        session=session,
    )
    o.start()
    assert o.next_experiment().exp_id == "flanker"


def test_orchestrator_advances_through_battery(tmp_path):
    session = RunSession(state_dir=tmp_path, subject_id="01")
    o = BatteryOrchestrator(
        manifest=_battery(["flanker", "stroop"]),
        strategy=FixedStrategy(),
        session=session,
    )
    o.start()
    assert o.next_experiment().exp_id == "flanker"
    o.advance()
    assert o.next_experiment().exp_id == "stroop"
    o.advance()
    assert o.next_experiment() is None


def test_orchestrator_uses_strategy_for_order(tmp_path):
    session = RunSession(state_dir=tmp_path, subject_id="1")  # row 1 of latin square
    o = BatteryOrchestrator(
        manifest=_battery(["flanker", "stroop", "nback"]),
        strategy=LatinSquareStrategy(),
        session=session,
    )
    o.start()
    # Row 1 of Williams square: (1+j) mod 3 → stroop, nback, flanker
    assert o.next_experiment().exp_id == "stroop"


def test_orchestrator_battery_id_is_stable(tmp_path):
    m = _battery(["flanker", "stroop"])
    session = RunSession(state_dir=tmp_path, subject_id="01")
    o = BatteryOrchestrator(manifest=m, strategy=FixedStrategy(), session=session)
    o.start()
    bid_1 = o.battery_id
    o2 = BatteryOrchestrator(
        manifest=m,
        strategy=FixedStrategy(),
        session=RunSession(state_dir=tmp_path, subject_id="02"),
    )
    o2.start()
    assert bid_1 == o2.battery_id  # battery_id is hash of manifest, not subject-specific
