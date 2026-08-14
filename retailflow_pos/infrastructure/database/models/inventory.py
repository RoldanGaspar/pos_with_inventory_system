"""
RetailFlow POS - Inventory Model
Stock-on-hand snapshot per product.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.models.base import BaseEntity
from infrastructure.database.models.product import Product


class Inventory(BaseEntity):
    """Current stock snapshot for a single product."""

    __tablename__ = "inventory"

    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), unique=True, nullable=False
    )
    quantity_on_hand: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quantity_allocated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_counted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    product: Mapped[Product] = relationship("Product", back_populates="inventory")

    def __repr__(self) -> str:
        return f"<Inventory(product_id={self.product_id}, qty={self.quantity_on_hand})>"
