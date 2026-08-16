"""
RetailFlow POS - Financial & Reporting Data Transfer Objects
Strongly-typed, immutable DTO schemas for executive financial summaries, P&L metrics,
daily timeline points, cashier performance, product analytics, refund breakdowns, and inventory valuations.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional


@dataclass(frozen=True)
class FinancialSummaryDTO:
    """
    Authoritative high-level financial summary and Profit & Loss statement for a date range.
    Integrates customer sales returns into net revenue, operational tax liability, and net collections.
    """

    start_date: str
    end_date: str

    # ── Core Baseline P&L Metrics ──
    gross_sales: Decimal
    discounts: Decimal
    net_sales: Decimal
    output_vat: Decimal  # Legacy compatibility field: identical to gross_output_vat
    total_collections: Decimal
    cogs: Decimal  # Net reported COGS: original_cogs - cogs_reversals
    gross_profit: Decimal
    gross_margin_percent: Decimal
    operating_expenses: Decimal
    net_operating_profit: Decimal
    net_operating_margin_percent: Decimal

    # ── Additive Return & Reconciliation Metrics ──
    sales_returns: Decimal = Decimal("0.00")
    gross_output_vat: Decimal = Decimal("0.00")
    vat_reversals: Decimal = Decimal("0.00")
    net_output_vat: Decimal = Decimal("0.00")
    refunds_issued: Decimal = Decimal("0.00")
    net_collections: Decimal = Decimal("0.00")
    original_cogs: Decimal = Decimal("0.00")
    cogs_reversals: Decimal = Decimal("0.00")

    def __post_init__(self):
        if self.gross_output_vat == Decimal("0.00") and self.output_vat > Decimal("0.00"):
            object.__setattr__(self, "gross_output_vat", self.output_vat)
        if self.net_output_vat == Decimal("0.00") and self.output_vat > Decimal("0.00") and self.vat_reversals == Decimal("0.00"):
            object.__setattr__(self, "net_output_vat", self.output_vat)
        if self.net_collections == Decimal("0.00") and self.total_collections > Decimal("0.00") and self.refunds_issued == Decimal("0.00"):
            object.__setattr__(self, "net_collections", self.total_collections)
        if self.original_cogs == Decimal("0.00") and self.cogs > Decimal("0.00") and self.cogs_reversals == Decimal("0.00"):
            object.__setattr__(self, "original_cogs", self.cogs)


@dataclass(frozen=True)
class DailyFinancialPointDTO:
    """Single calendar day data point for financial trends with continuous zero-filling."""

    date: str  # YYYY-MM-DD
    net_sales: Decimal
    cogs: Decimal
    gross_profit: Decimal
    opex: Decimal
    net_operating_profit: Decimal
    gross_sales: Decimal = Decimal("0.00")
    discounts: Decimal = Decimal("0.00")
    sales_returns: Decimal = Decimal("0.00")


@dataclass(frozen=True)
class ExpenseCategoryBreakdownDTO:
    """Store operating expenses breakdown by category with authoritative percentage."""

    category: str
    category_display: str
    amount: Decimal
    percentage: Decimal


@dataclass(frozen=True)
class PaymentMethodSummaryDTO:
    """Distribution of gross collections by incoming payment method channel."""

    payment_method: str
    payment_method_display: str
    transaction_count: int
    total_amount: Decimal
    percentage: Decimal


@dataclass(frozen=True)
class RefundMethodSummaryDTO:
    """Distribution of customer refund disbursements by payment method channel."""

    refund_method: str
    refund_method_display: str
    return_count: int
    total_refund_amount: Decimal
    percentage: Decimal


@dataclass(frozen=True)
class CashierPerformanceDTO:
    """Operational sales and net performance metrics per cashier."""

    cashier_id: Optional[int]
    cashier_name: str
    transaction_count: int
    net_sales: Decimal
    collections: Decimal
    average_order_value: Decimal
    discounts: Decimal
    units_sold: int
    refunds_issued: Decimal = Decimal("0.00")
    net_collections: Decimal = Decimal("0.00")
    units_returned: int = 0
    net_units: int = 0

    def __post_init__(self):
        if self.net_collections == Decimal("0.00") and self.collections > Decimal("0.00") and self.refunds_issued == Decimal("0.00"):
            object.__setattr__(self, "net_collections", self.collections)
        if self.net_units == 0 and self.units_sold > 0 and self.units_returned == 0:
            object.__setattr__(self, "net_units", self.units_sold)


@dataclass(frozen=True)
class ProductPerformanceDTO:
    """Sales volume and direct product contribution leaderboard entry."""

    product_id: int
    sku: str
    product_name: str
    quantity_sold: int
    gross_revenue: Decimal
    historical_cogs: Decimal
    direct_margin: Decimal = Decimal("0.00")
    quantity_returned: int = 0
    net_units_sold: int = 0
    gross_revenue_reversal: Decimal = Decimal("0.00")
    net_gross_revenue: Decimal = Decimal("0.00")
    cogs_reversals: Decimal = Decimal("0.00")
    net_historical_cogs: Decimal = Decimal("0.00")
    direct_margin_before_order_discount: Optional[Decimal] = None

    def __post_init__(self):
        if self.direct_margin == Decimal("0.00") and self.direct_margin_before_order_discount is not None:
            object.__setattr__(self, "direct_margin", self.direct_margin_before_order_discount)
        elif self.direct_margin_before_order_discount is None:
            object.__setattr__(self, "direct_margin_before_order_discount", self.direct_margin)
        if self.net_units_sold == 0 and self.quantity_sold > 0 and self.quantity_returned == 0:
            object.__setattr__(self, "net_units_sold", self.quantity_sold)
        if self.net_gross_revenue == Decimal("0.00") and self.gross_revenue > Decimal("0.00") and self.gross_revenue_reversal == Decimal("0.00"):
            object.__setattr__(self, "net_gross_revenue", self.gross_revenue)
        if self.net_historical_cogs == Decimal("0.00") and self.historical_cogs > Decimal("0.00") and self.cogs_reversals == Decimal("0.00"):
            object.__setattr__(self, "net_historical_cogs", self.historical_cogs)


@dataclass(frozen=True)
class InventoryValueDTO:
    """Current working capital inventory valuation at replacement cost and retail value."""

    total_products: int
    total_units_on_hand: int
    current_cost_value: Decimal
    current_retail_value: Decimal
    potential_unrealized_margin: Decimal


@dataclass(frozen=True)
class PurchaseIntakeSummaryDTO:
    """Procurement summary of received purchase orders in a date range."""

    start_date: str
    end_date: str
    received_order_count: int
    received_purchase_value: Decimal
    total_units_received: int
