from __future__ import annotations

import pytest

from price_monitor.detector import drop_pct, is_drop


def test_drop_at_exact_threshold_is_true() -> None:
    # 10% drop, threshold exactly 10% → must be True (boundary inclusive)
    assert is_drop(prev_price=100.0, new_price=90.0, threshold_pct=10.0) is True


def test_drop_below_threshold_is_false() -> None:
    # 4% drop, threshold 5% → False
    assert is_drop(prev_price=100.0, new_price=96.0, threshold_pct=5.0) is False


def test_price_increase_is_not_a_drop() -> None:
    # new > prev → drop_pct is negative → False
    assert is_drop(prev_price=90.0, new_price=100.0, threshold_pct=5.0) is False


def test_prev_price_zero_is_false() -> None:
    # Guard: dividing by zero is nonsensical; always returns False
    assert is_drop(prev_price=0.0, new_price=50.0, threshold_pct=5.0) is False


def test_equal_prices_is_not_a_drop() -> None:
    assert is_drop(prev_price=50.0, new_price=50.0, threshold_pct=0.01) is False


def test_large_drop_is_true() -> None:
    # 70% drop
    assert is_drop(prev_price=100.0, new_price=30.0, threshold_pct=5.0) is True


def test_drop_pct_calculation() -> None:
    assert drop_pct(prev_price=100.0, new_price=75.0) == pytest.approx(25.0)


def test_drop_pct_price_increase_is_negative() -> None:
    assert drop_pct(prev_price=80.0, new_price=100.0) == pytest.approx(-25.0)
