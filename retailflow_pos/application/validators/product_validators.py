"""
RetailFlow POS - Product Validators
Input validation for product form data.
"""

from decimal import Decimal

from application.dto.product_dto import ProductFormDTO
from domain.exceptions import InvalidPriceError, ValidationError


def validate_product_form(dto: ProductFormDTO) -> None:
    """Validate product form input. Raises domain exceptions on failure."""
    if not dto.sku or not dto.sku.strip():
        raise ValidationError("SKU is required.")
    if not dto.name or not dto.name.strip():
        raise ValidationError("Product name is required.")
    if dto.cost_price < Decimal("0"):
        raise InvalidPriceError("Cost price cannot be negative.")
    if dto.selling_price < Decimal("0"):
        raise InvalidPriceError("Selling price cannot be negative.")
    if dto.reorder_level < 0:
        raise ValidationError("Reorder level cannot be negative.")
    if dto.barcode and not dto.barcode.strip():
        raise ValidationError("Barcode cannot be empty.")
