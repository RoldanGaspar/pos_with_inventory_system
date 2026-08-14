"""
Unit tests for stock business rules.
"""

from domain.rules.stock_rules import (
    STOCK_IN_STOCK,
    STOCK_LOW,
    STOCK_OUT,
    stock_status,
)


def test_out_of_stock_when_zero():
    assert stock_status(0, 10) == STOCK_OUT


def test_low_stock_when_below_reorder_level():
    assert stock_status(5, 10) == STOCK_LOW


def test_low_stock_when_equal_to_reorder_level():
    assert stock_status(10, 10) == STOCK_LOW


def test_in_stock_above_reorder_level():
    assert stock_status(11, 10) == STOCK_IN_STOCK


def test_no_reorder_level_never_low():
    assert stock_status(1, 0) == STOCK_IN_STOCK
