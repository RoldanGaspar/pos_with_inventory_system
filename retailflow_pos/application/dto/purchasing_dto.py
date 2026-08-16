"""
RetailFlow POS - Purchasing & Purchase Order Data Transfer Objects
Data structures for purchase order creation, line items, status tracking, and purchasing metrics.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional


@dataclass(frozen=True)
class PurchaseOrderItemDTO:
    """Itemized product in a purchase order."""
    id: int
    product_id: int
    product_name: str
    quantity_ordered: int
    quantity_received: int
    unit_cost: Decimal
    subtotal: Decimal


@dataclass(frozen=True)
class CreatePOItemDTO:
    """Input payload for adding a product line item to a purchase order."""
    product_id: int
    quantity: int
    unit_cost: Decimal


@dataclass(frozen=True)
class PurchaseOrderResponseDTO:
    """Full representation of a purchase order."""
    id: int
    po_number: str
    supplier_id: int
    supplier_name: str
    supplier_code: str
    status: str
    order_date: str
    expected_delivery: Optional[str]
    received_at: Optional[str]
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    payment_terms: str
    notes: Optional[str]
    items_count: int
    total_units: int
    items: List[PurchaseOrderItemDTO] = field(default_factory=list)


@dataclass(frozen=True)
class CreatePurchaseOrderDTO:
    """Input payload for issuing or drafting a new purchase order."""
    supplier_id: int
    items: List[CreatePOItemDTO]
    expected_delivery: Optional[str] = None
    payment_terms: str = "NET_30"
    status: str = "ORDERED"
    notes: Optional[str] = None


@dataclass(frozen=True)
class PurchaseOrderFilterDTO:
    """Query filters for searching purchase orders."""
    keyword: Optional[str] = None
    status: Optional[str] = None
    supplier_id: Optional[int] = None
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class POSearchResultDTO:
    """Paginated result of purchase orders."""
    items: List[PurchaseOrderResponseDTO]
    total: int
    page: int
    page_size: int

    @property
    def has_next(self) -> bool:
        return self.page * self.page_size < self.total

    @property
    def has_previous(self) -> bool:
        return self.page > 1


@dataclass(frozen=True)
class PurchasingMetricsDTO:
    """Aggregate statistics for purchasing department."""
    total_pos: int
    pending_orders: int
    received_orders: int
    total_purchases_spent: Decimal
