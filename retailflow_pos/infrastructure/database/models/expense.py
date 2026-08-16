"""
RetailFlow POS - Expense ORM Model
SQLAlchemy ORM model for store operating expenses and disbursement vouchers.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import ExpenseCategory, ExpenseSource, ExpenseStatus
from infrastructure.database.models.base import BaseEntity

if TYPE_CHECKING:
    from infrastructure.database.models.auth import User


class Expense(BaseEntity):
    """Store operational expense and disbursement voucher record."""

    __tablename__ = "expenses"

    voucher_number: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(
        String(30), default=ExpenseCategory.OTHER, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payee: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    payment_method: Mapped[str] = mapped_column(
        String(30), default="CASH", nullable=False
    )
    reference_number: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    expense_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default=ExpenseStatus.PAID, nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(
        String(20), default=ExpenseSource.MANUAL, nullable=False
    )
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    void_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    voided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    voided_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_id]
    )
    voided_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[voided_by_id]
    )

    def __repr__(self) -> str:
        return f"<Expense(voucher={self.voucher_number}, category={self.category}, amount={self.amount}, status={self.status})>"
