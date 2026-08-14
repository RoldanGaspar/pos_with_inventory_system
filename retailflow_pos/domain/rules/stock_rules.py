"""
RetailFlow POS - Stock Business Rules
Pure functions for deriving stock state. No framework or infrastructure imports.
"""

STOCK_IN_STOCK = "in_stock"
STOCK_LOW = "low_stock"
STOCK_OUT = "out_of_stock"


def stock_status(quantity_on_hand: int, reorder_level: int) -> str:
    """Derive the semantic stock state for a product.

    - out_of_stock: no stock on hand
    - low_stock: positive stock at or below the reorder threshold
    - in_stock: otherwise
    """
    if quantity_on_hand <= 0:
        return STOCK_OUT
    if reorder_level > 0 and quantity_on_hand <= reorder_level:
        return STOCK_LOW
    return STOCK_IN_STOCK
