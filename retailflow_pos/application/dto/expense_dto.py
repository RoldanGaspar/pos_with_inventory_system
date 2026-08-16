"""
RetailFlow POS - Expense Data Transfer Objects
Strongly-typed, immutable DTO schemas for expense creation, metadata updates,
voiding, filtering, and reporting aggregations.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional


@dataclass(frozen=True)
class CreateExpenseDTO:
    """Input payload for recording a new expense disbursement."""

    category: str
    title: str
    payee: str
    amount: Decimal
    expense_date: date
    payment_method: str = "CASH"
    description: Optional[str] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None


@dataclass(frozen=True)
class UpdateExpenseMetadataDTO:
    """
    Input payload for editing non-financial expense metadata.
    Strictly excludes financial fields (amount, category, date, payment_method, voucher_number, status).
    """

    payee: str
    description: Optional[str] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None


@dataclass(frozen=True)
class VoidExpenseDTO:
    """Input payload for soft-cancelling/voiding an expense voucher."""

    expense_id: int
    void_reason: str


@dataclass(frozen=True)
class ExpenseResponseDTO:
    """Full representation of an expense voucher."""

    id: int
    voucher_number: str
    category: str
    category_display: str
    title: str
    description: Optional[str]
    payee: str
    amount: Decimal
    payment_method: str
    payment_method_display: str
    reference_number: Optional[str]
    expense_date: str
    status: str
    source: str
    notes: Optional[str]
    void_reason: Optional[str]
    voided_at: Optional[str]
    created_by_username: str


@dataclass(frozen=True)
class ExpenseFilterDTO:
    """Query parameters for searching and filtering expenses."""

    keyword: Optional[str] = None
    category: Optional[str] = None
    payment_method: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class ExpenseSearchResultDTO:
    """Paginated result of expense records."""

    items: List[ExpenseResponseDTO]
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
class ExpenseMetricsDTO:
    """Summary metrics for the Expenses workstation header cards."""

    total_expenses: Decimal
    this_month_spend: Decimal
    top_category_display: str
    active_vouchers_count: int
