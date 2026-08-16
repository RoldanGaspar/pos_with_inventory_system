"""
RetailFlow POS - Purchasing & Purchase Order ORM Models
SQLAlchemy ORM models for Purchase Orders and Purchase Order Line Items.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.models.base import BaseEntity

if TYPE_CHECKING:
    from infrastructure.database.models.auth import User
    from infrastructure.database.models.product import Product
    from infrastructure.database.models.supplier import Supplier


class PurchaseOrder(BaseEntity):
    """Wholesale purchase order record."""

    __tablename__ = "purchase_orders"

    po_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    supplier_id: Mapped[int] = mapped_column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    order_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expected_delivery: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ORDERED", nullable=False, index=True)
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    payment_terms: Mapped[str] = mapped_column(String(30), default="NET_30", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    received_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    supplier: Mapped["Supplier"] = relationship("Supplier")
    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        "PurchaseOrderItem", back_populates="purchase_order", cascade="all, delete-orphan"
    )
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_id])
    received_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[received_by_id])

    def __repr__(self) -> str:
        return f"<PurchaseOrder(po={self.po_number}, status={self.status}, total={self.total_amount})>"


class PurchaseOrderItem(BaseEntity):
    """Line item within a purchase order."""

    __tablename__ = "purchase_order_items"

    purchase_order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("purchase_orders.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(150), nullable=False)
    quantity_ordered: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    quantity_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )

    purchase_order: Mapped[PurchaseOrder] = relationship("PurchaseOrder", back_populates="items")
    product: Mapped["Product"] = relationship("Product")

    def __repr__(self) -> str:
        return f"<PurchaseOrderItem(product={self.product_name}, qty={self.quantity_ordered}, subtotal={self.subtotal})>"
