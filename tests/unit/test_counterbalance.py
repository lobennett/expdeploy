"""Tests for expdeploy.battery.counterbalance — 4 strategies."""

from __future__ import annotations

import pytest

from expdeploy.battery.counterbalance import (
    FixedStrategy,
    LatinSquareStrategy,
    SeededRandomStrategy,
    UserSuppliedStrategy,
)

EXPS = ["flanker", "stroop", "nback"]


def test_fixed_returns_input_verbatim():
    s = FixedStrategy()
    assert s.order_for("01", EXPS) == EXPS
    assert s.order_for("any", EXPS) == EXPS


def test_fixed_does_not_mutate_input():
    s = FixedStrategy()
    out = s.order_for("01", EXPS)
    out.append("extra")
    assert ["flanker", "stroop", "nback"] == EXPS


def test_latin_square_rotates_by_subject():
    s = LatinSquareStrategy()
    o0 = s.order_for("0", EXPS)
    o1 = s.order_for("1", EXPS)
    o2 = s.order_for("2", EXPS)
    # First experiment must differ across rows
    firsts = {o0[0], o1[0], o2[0]}
    assert len(firsts) == 3  # all unique


def test_latin_square_is_deterministic():
    s = LatinSquareStrategy()
    a = s.order_for("5", EXPS)
    b = s.order_for("5", EXPS)
    assert a == b


def test_latin_square_wraps_at_k():
    s = LatinSquareStrategy()
    # Subject K and subject 0 should match (modulo K)
    a = s.order_for("0", EXPS)
    b = s.order_for(str(len(EXPS)), EXPS)
    assert a == b


def test_latin_square_rejects_non_int_subject():
    s = LatinSquareStrategy()
    with pytest.raises(ValueError):
        s.order_for("pilot_a", EXPS)


def test_strategy_name_attr_present():
    assert FixedStrategy().name == "fixed"
    assert LatinSquareStrategy().name == "latin_square"


def test_seeded_random_is_deterministic_per_subject():
    s = SeededRandomStrategy()
    assert s.order_for("01", EXPS) == s.order_for("01", EXPS)


def test_seeded_random_differs_across_subjects():
    s = SeededRandomStrategy()
    orders = {tuple(s.order_for(sid, EXPS)) for sid in ["01", "02", "03", "04", "05", "06"]}
    # Most subjects should get distinct orders; collision is possible but unlikely
    assert len(orders) >= 2


def test_user_supplied_returns_csv_row(tmp_path):
    csv_path = tmp_path / "orders.csv"
    csv_path.write_text(
        "subject_id,pos_1,pos_2,pos_3\n" "01,nback,flanker,stroop\n" "02,stroop,nback,flanker\n"
    )
    s = UserSuppliedStrategy(order_csv=csv_path)
    assert s.order_for("01", EXPS) == ["nback", "flanker", "stroop"]
    assert s.order_for("02", EXPS) == ["stroop", "nback", "flanker"]


def test_user_supplied_missing_subject_raises(tmp_path):
    csv_path = tmp_path / "orders.csv"
    csv_path.write_text("subject_id,pos_1\n01,nback\n")
    s = UserSuppliedStrategy(order_csv=csv_path)
    with pytest.raises(KeyError):
        s.order_for("99", EXPS)
