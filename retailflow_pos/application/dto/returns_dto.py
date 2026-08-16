"""
RetailFlow POS - Returns & Refunds Data Transfer Objects (DTOs)
Immutable data contracts for return requests, line item breakdowns, and return summaries.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional

from app.constants import RefundMethod, ReturnDisposition, ReturnReason, ReturnStatus


@dataclass(frozen=True)
class ReturnItemRequestDTO:
    """Input payload for a single line item being returned."""

    sale_line_item_id: int
    quantity: int
    disposition: str = ReturnDisposition.RESTOCK.value


@dataclass(frozen=True)
class ProcessReturnRequestDTO:
    """Input payload for processing a customer return voucher."""

    sale_id: int
    items: List[ReturnItemRequestDTO]
    reason_code: str = ReturnReason.OTHER.value
    reason_notes: Optional[str] = None
    refund_payment_method: str = RefundMethod.CASH.value
    refund_reference: Optional[str] = None


@dataclass(frozen=True)
class SalesReturnItemDTO:
    """Detailed itemized line item in a completed return voucher."""

    id: int
    sales_return_id: int
    sale_line_item_id: int
    product_id: int
    product_name: str
    quantity: int
    unit_price_snapshot: Decimal
    unit_cost_snapshot: Decimal
    gross_amount_reversal: Decimal
    discount_reversal: Decimal
    taxable_reversal: Decimal
    tax_reversal: Decimal
    total_refund_amount: Decimal
    cogs_reversal: Decimal
    writeoff_cost: Decimal
    disposition: str


@dataclass(frozen=True)
class SalesReturnDTO:
    """Complete representation of a finalized customer return voucher."""

    id: int
    return_number: str
    sale_id: int
    sale_transaction_number: str
    cashier_id: int
    cashier_name: str
    approved_by_id: int
    approver_name: str
    return_date: str
    status: str
    reason_code: str
    reason_notes: Optional[str]
    refund_payment_method: str
    original_payment_method_snapshot: str
    refund_reference: Optional[str]
    subtotal_returned: Decimal
    discount_reversal: Decimal
    taxable_reversal: Decimal
    tax_reversal: Decimal
    total_refund_amount: Decimal
    cogs_reversal_total: Decimal
    writeoff_cost_total: Decimal
    created_at: str
    items: List[SalesReturnItemDTO] = field(default_factory=list)


@dataclass(frozen=True)
class ReturnableLineItemDTO:
    """Line item with calculated remaining returnable balance for UI modal display."""

    sale_line_item_id: int
    product_id: int
    product_name: str
    unit_price: Decimal
    unit_cost: Decimal
    original_quantity: int
    previously_returned_quantity: int
    remaining_returnable_quantity: int
    max_discount_allocable: Decimal
    max_tax_allocable: Decimal


@dataclass(frozen=True)
class SaleReturnSummaryDTO:
    """Derived return state and cumulative return metrics for a parent sale transaction."""

    sale_id: int
    transaction_number: str
    total_original_quantity: int
    total_returned_quantity: int
    derived_state: str  # "none", "partial", "full"
    total_refunded_amount: Decimal
    returns_count: int


@dataclass(frozen=True)
class ReturnItemPreviewDTO:
    """Itemized non-mutating preview breakdown for a single returnable line item."""

    sale_line_item_id: int
    product_id: int
    product_name: str
    quantity: int
    unit_price: Decimal
    unit_cost: Decimal
    gross_amount_reversal: Decimal
    discount_reversal: Decimal
    taxable_reversal: Decimal
    tax_reversal: Decimal
    total_refund_amount: Decimal
    cogs_reversal: Decimal
    writeoff_cost: Decimal
    disposition: str


@dataclass(frozen=True)
class ReturnPreviewDTO:
    """Complete non-mutating preview of an anticipated customer return voucher."""

    sale_id: int
    subtotal_returned: Decimal
    discount_reversal: Decimal
    taxable_reversal: Decimal
    tax_reversal: Decimal
    total_refund_amount: Decimal
    cogs_reversal_total: Decimal
    writeoff_cost_total: Decimal
    items: List[ReturnItemPreviewDTO] = field(default_factory=list)

