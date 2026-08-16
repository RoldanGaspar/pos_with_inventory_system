"""
RetailFlow POS - Sales ORM Models
SQLAlchemy ORM models for Sales, SaleLineItems, and Payments.
"""

from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.models.base import BaseEntity

if TYPE_CHECKING:
    from infrastructure.database.models.auth import User
    from infrastructure.database.models.product import Product
    from infrastructure.database.models.returns import SalesReturn


class Sale(BaseEntity):
    """Completed or processed sales transaction header."""

    __tablename__ = "sales"

    transaction_number: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    cashier_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="COMPLETED", nullable=False, index=True
    )
    payment_method: Mapped[str] = mapped_column(
        String(30), default="CASH", nullable=False
    )

    cashier: Mapped[Optional["User"]] = relationship("User")
    items: Mapped[list["SaleLineItem"]] = relationship(
        "SaleLineItem", back_populates="sale", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="sale", cascade="all, delete-orphan"
    )
    returns: Mapped[list["SalesReturn"]] = relationship(
        "SalesReturn", back_populates="sale"
    )

    def __repr__(self) -> str:
        return f"<Sale(txn={self.transaction_number}, total={self.total_amount})>"


class SaleLineItem(BaseEntity):
    """Individual product line item in a sale transaction."""

    __tablename__ = "sale_line_items"

    sale_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sales.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False, index=True
    )
    product_name: Mapped[str] = mapped_column(String(150), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )

    sale: Mapped[Sale] = relationship("Sale", back_populates="items")
    product: Mapped["Product"] = relationship("Product")

    def __repr__(self) -> str:
        return f"<SaleLineItem(product={self.product_name}, qty={self.quantity}, subtotal={self.subtotal})>"


class Payment(BaseEntity):
    """Payment record linked to a sale."""

    __tablename__ = "payments"

    sale_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sales.id"), nullable=False, index=True
    )
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    change_given: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    sale: Mapped[Sale] = relationship("Sale", back_populates="payments")

    def __repr__(self) -> str:
        return f"<Payment(method={self.payment_method}, amount={self.amount_paid})>"
