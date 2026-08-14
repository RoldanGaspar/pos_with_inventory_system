"""
Unit tests for product form validators.
"""

from decimal import Decimal

import pytest

from application.dto.product_dto import ProductFormDTO
from application.validators.product_validators import validate_product_form
from domain.exceptions import InvalidPriceError, ValidationError


def make_dto(**overrides) -> ProductFormDTO:
    data = {
        "sku": "SKU-001",
        "name": "Test Product",
        "cost_price": Decimal("10.00"),
        "selling_price": Decimal("20.00"),
        "reorder_level": 0,
        "barcode": "4800000000001",
    }
    data.update(overrides)
    return ProductFormDTO(**data)


def test_valid_dto_passes():
    validate_product_form(make_dto())


def test_missing_sku_raises():
    with pytest.raises(ValidationError):
        validate_product_form(make_dto(sku=""))


def test_missing_name_raises():
    with pytest.raises(ValidationError):
        validate_product_form(make_dto(name="   "))


def test_negative_cost_raises():
    with pytest.raises(InvalidPriceError):
        validate_product_form(make_dto(cost_price=Decimal("-1.00")))


def test_negative_price_raises():
    with pytest.raises(InvalidPriceError):
        validate_product_form(make_dto(selling_price=Decimal("-0.01")))


def test_negative_reorder_level_raises():
    with pytest.raises(ValidationError):
        validate_product_form(make_dto(reorder_level=-1))
