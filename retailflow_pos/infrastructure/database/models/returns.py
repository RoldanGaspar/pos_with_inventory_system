"""
RetailFlow POS - Returns & Refunds ORM Models
SQLAlchemy ORM models for SalesReturn header and SalesReturnItem line item vouchers.
"""

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import RefundMethod, ReturnDisposition, ReturnReason, ReturnStatus
from infrastructure.database.models.base import BaseEntity

if TYPE_CHECKING:
    from infrastructure.database.models.auth import User
    from infrastructure.database.models.product import Product
    from infrastructure.database.models.sales import Sale, SaleLineItem


class SalesReturn(BaseEntity):
    """
    Finalized customer return transaction voucher header.
    Immutable once completed. Contains authoritative P&L, VAT, and COGS reversal totals.
    """

    __tablename__ = "sales_returns"
    __table_args__ = (
        CheckConstraint("subtotal_returned >= 0", name="chk_return_subtotal_non_negative"),
        CheckConstraint("discount_reversal >= 0", name="chk_return_discount_non_negative"),
        CheckConstraint("taxable_reversal >= 0", name="chk_return_taxable_non_negative"),
        CheckConstraint("tax_reversal >= 0", name="chk_return_tax_non_negative"),
        CheckConstraint("total_refund_amount >= 0", name="chk_return_total_refund_non_negative"),
        CheckConstraint("cogs_reversal_total >= 0", name="chk_return_cogs_reversal_non_negative"),
        CheckConstraint("writeoff_cost_total >= 0", name="chk_return_writeoff_cost_non_negative"),
        CheckConstraint(f"status = '{ReturnStatus.COMPLETED.value}'", name="chk_return_status_completed"),
        CheckConstraint(
            f"refund_payment_method IN ('{RefundMethod.CASH.value}', '{RefundMethod.ORIGINAL_METHOD.value}')",
            name="chk_return_refund_method_valid",
        ),
        CheckConstraint(
            f"reason_code IN ('{ReturnReason.DEFECTIVE.value}', '{ReturnReason.WRONG_ITEM.value}', "
            f"'{ReturnReason.CUSTOMER_CHANGE_MIND.value}', '{ReturnReason.EXPIRED.value}', '{ReturnReason.OTHER.value}')",
            name="chk_return_reason_code_valid",
        ),
    )

    return_number: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    sale_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sales.id"), nullable=False, index=True
    )
    cashier_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    approved_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    return_date: Mapped[date] = mapped_column(
        Date, nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=ReturnStatus.COMPLETED.value, nullable=False
    )
    reason_code: Mapped[str] = mapped_column(
        String(50), default=ReturnReason.OTHER.value, nullable=False
    )
    reason_notes: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    refund_payment_method: Mapped[str] = mapped_column(
        String(30), default=RefundMethod.CASH.value, nullable=False
    )
    original_payment_method_snapshot: Mapped[str] = mapped_column(
        String(30), nullable=False
    )
    refund_reference: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )

    # ── Financial Authoritative Snapshots ──
    subtotal_returned: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    discount_reversal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    taxable_reversal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    tax_reversal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    total_refund_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    cogs_reversal_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    writeoff_cost_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )

    # ── Relationships (Non-destructive, append-only ledger) ──
    sale: Mapped["Sale"] = relationship("Sale", back_populates="returns")
    cashier: Mapped["User"] = relationship("User", foreign_keys=[cashier_id])
    approved_by: Mapped["User"] = relationship("User", foreign_keys=[approved_by_id])
    items: Mapped[list["SalesReturnItem"]] = relationship(
        "SalesReturnItem", back_populates="sales_return"
    )

    def __repr__(self) -> str:
        return f"<SalesReturn(ret_num={self.return_number}, refund={self.total_refund_amount}, status={self.status})>"


class SalesReturnItem(BaseEntity):
    """
    Individual itemized product in a customer return voucher.
    Contains line-level historical snapshots and exact proportional reversals.
    """

    __tablename__ = "sales_return_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_return_item_quantity_positive"),
        CheckConstraint("unit_price_snapshot >= 0", name="chk_return_item_unit_price_non_negative"),
        CheckConstraint("unit_cost_snapshot >= 0", name="chk_return_item_unit_cost_non_negative"),
        CheckConstraint("gross_amount_reversal >= 0", name="chk_return_item_gross_non_negative"),
        CheckConstraint("discount_reversal >= 0", name="chk_return_item_discount_non_negative"),
        CheckConstraint("taxable_reversal >= 0", name="chk_return_item_taxable_non_negative"),
        CheckConstraint("tax_reversal >= 0", name="chk_return_item_tax_non_negative"),
        CheckConstraint("total_refund_amount >= 0", name="chk_return_item_refund_non_negative"),
        CheckConstraint("cogs_reversal >= 0", name="chk_return_item_cogs_non_negative"),
        CheckConstraint("writeoff_cost >= 0", name="chk_return_item_writeoff_non_negative"),
        CheckConstraint(
            f"disposition IN ('{ReturnDisposition.RESTOCK.value}', '{ReturnDisposition.DAMAGED_WRITE_OFF.value}')",
            name="chk_return_item_disposition_valid",
        ),
    )

    sales_return_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sales_returns.id"), nullable=False, index=True
    )
    sale_line_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sale_line_items.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False, index=True
    )
    product_name: Mapped[str] = mapped_column(
        String(150), nullable=False
    )
    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    unit_price_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    unit_cost_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )

    # ── Financial Line Snapshots ──
    gross_amount_reversal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    discount_reversal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    taxable_reversal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    tax_reversal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    total_refund_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    cogs_reversal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    writeoff_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    disposition: Mapped[str] = mapped_column(
        String(30), default=ReturnDisposition.RESTOCK.value, nullable=False
    )

    # ── Relationships ──
    sales_return: Mapped[SalesReturn] = relationship("SalesReturn", back_populates="items")
    sale_line_item: Mapped["SaleLineItem"] = relationship("SaleLineItem")
    product: Mapped["Product"] = relationship("Product")

    def __repr__(self) -> str:
        return f"<SalesReturnItem(product={self.product_name}, qty={self.quantity}, refund={self.total_refund_amount}, disp={self.disposition})>"
