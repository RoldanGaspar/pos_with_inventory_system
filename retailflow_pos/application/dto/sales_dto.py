"""
RetailFlow POS - Sales DTOs
Data transfer objects for shopping cart, checkout, and sales history.
"""

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class CartItemDTO:
    """Item present in the active POS shopping cart."""

    product_id: int
    sku: str
    name: str
    unit_price: Decimal
    quantity: int = 1
    available_stock: int = 0

    @property
    def subtotal(self) -> Decimal:
        return self.unit_price * Decimal(self.quantity)


@dataclass
class CartSummaryDTO:
    """Totals calculation for the current shopping cart."""

    items: list[CartItemDTO] = field(default_factory=list)
    discount_amount: Decimal = Decimal("0.00")
    tax_rate: Decimal = Decimal("0.12")  # Default 12% tax rate

    @property
    def subtotal(self) -> Decimal:
        return sum((item.subtotal for item in self.items), Decimal("0.00"))

    @property
    def tax_amount(self) -> Decimal:
        taxable = max(Decimal("0.00"), self.subtotal - self.discount_amount)
        return (taxable * self.tax_rate).quantize(Decimal("0.01"))

    @property
    def total_amount(self) -> Decimal:
        return max(Decimal("0.00"), self.subtotal - self.discount_amount + self.tax_amount)


@dataclass
class CheckoutRequestDTO:
    """Payload sent when completing a sale at the POS."""

    items: list[CartItemDTO]
    payment_method: str  # CASH, CARD, GCASH, MAYA
    amount_tendered: Decimal
    discount_amount: Decimal = Decimal("0.00")
    cashier_id: int | None = None
    reference_number: str | None = None


@dataclass
class SaleLineItemDTO:
    """Line item breakdown in a sale receipt / details."""

    id: int
    product_id: int
    product_name: str
    unit_price: Decimal
    quantity: int
    subtotal: Decimal


@dataclass
class SaleResponseDTO:
    """Complete sale transaction receipt data."""

    id: int
    transaction_number: str
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    payment_method: str
    amount_paid: Decimal
    change_given: Decimal
    status: str
    created_at: str
    items: list[SaleLineItemDTO] = field(default_factory=list)
