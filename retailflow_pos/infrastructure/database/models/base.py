"""
RetailFlow POS - Base SQLAlchemy Model
Mixin with common fields: id, created_at, updated_at.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.session import Base


class TimestampMixin:
    """Mixin for created_at/updated_at timestamp columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class BaseEntity(Base, TimestampMixin):
    """Abstract base for all entities with an integer primary key."""

    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
