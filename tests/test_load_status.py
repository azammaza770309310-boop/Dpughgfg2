"""Unit tests for the load-status rule (W5 threshold logic)."""

import pytest

from app.load_status import (
    HIGH_LOAD,
    NORMAL,
    BUSY,
    compute_load,
    highest_level,
    load_percent,
)


def test_below_busy_threshold_is_normal():
    assert compute_load(0, 3, 6) == NORMAL
    assert compute_load(2, 3, 6) == NORMAL


def test_busy_range():
    assert compute_load(3, 3, 6) == BUSY
    assert compute_load(5, 3, 6) == BUSY


def test_high_load_boundary():
    assert compute_load(6, 3, 6) == HIGH_LOAD
    assert compute_load(100, 3, 6) == HIGH_LOAD


def test_invalid_thresholds_raise():
    with pytest.raises(ValueError):
        compute_load(1, 6, 3)
    with pytest.raises(ValueError):
        compute_load(1, 5, 5)


def test_negative_waiting_raises():
    with pytest.raises(ValueError):
        compute_load(-1, 3, 6)


def test_percent_gauge():
    assert load_percent(0, 16) == 0
    assert load_percent(8, 16) == 50
    assert load_percent(16, 16) == 100
    assert load_percent(40, 16) == 100  # clamped


def test_highest_level():
    assert highest_level([NORMAL, NORMAL]) == NORMAL
    assert highest_level([NORMAL, BUSY]) == BUSY
    assert highest_level([BUSY, HIGH_LOAD, NORMAL]) == HIGH_LOAD
