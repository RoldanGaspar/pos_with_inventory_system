"""
RetailFlow POS - Supplier ORM Model
SQLAlchemy ORM model for wholesale suppliers, vendors, and distributors.
"""

from typing import Optional

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models.base import BaseEntity


class Supplier(BaseEntity):
    """Wholesale vendor and distributor entity."""

    __tablename__ = "suppliers"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    contact_person: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    phone: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payment_terms: Mapped[str] = mapped_column(String(30), default="NET_30", nullable=False)
    tax_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<Supplier(code={self.code}, name={self.name}, terms={self.payment_terms})>"
