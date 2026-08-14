"""
RetailFlow POS - Customer & Loyalty ORM Model
SQLAlchemy ORM model for customer profiles, loyalty tiers, and purchase metrics.
"""

from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models.base import BaseEntity


class Customer(BaseEntity):
    """Customer profile entity with loyalty points tracking."""

    __tablename__ = "customers"

    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    loyalty_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tier: Mapped[str] = mapped_column(String(20), default="bronze", nullable=False)
    total_spent: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    total_visits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def calculate_tier(self) -> str:
        """Derive loyalty tier from points balance."""
        if self.loyalty_points >= 1000:
            return "platinum"
        elif self.loyalty_points >= 500:
            return "gold"
        elif self.loyalty_points >= 100:
            return "silver"
        return "bronze"

    def __repr__(self) -> str:
        return f"<Customer(name={self.name}, phone={self.phone}, tier={self.tier}, points={self.loyalty_points})>"
