"""
RetailFlow POS - Store Settings Model
Singleton configuration entity for store profile and receipt preferences.
"""

from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import ReceiptWidth
from infrastructure.database.models.base import BaseEntity


class StoreSettings(BaseEntity):
    """
    Singleton store configuration and receipt preferences table.
    Enforced via database CHECK constraint (id = 1) and primary key uniqueness.
    """

    __tablename__ = "store_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_store_settings_single_row"),
        CheckConstraint(
            f"paper_width IN ('{ReceiptWidth.MM_58.value}', '{ReceiptWidth.MM_80.value}')",
            name="ck_store_settings_paper_width",
        ),
    )

    # ── 1. Store Profile ──
    store_name: Mapped[str] = mapped_column(
        String(100),
        default="RetailFlow Store",
        nullable=False,
    )
    store_address: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    contact_number: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    email: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    tin: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    logo_path: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # ── 2. Receipt Preferences ──
    receipt_header: Mapped[Optional[str]] = mapped_column(
        String(255),
        default="Official Sales Invoice / Thermal Receipt",
        nullable=True,
    )
    receipt_footer: Mapped[Optional[str]] = mapped_column(
        Text,
        default="Thank you for shopping with us!",
        nullable=True,
    )
    paper_width: Mapped[str] = mapped_column(
        String(10),
        default=ReceiptWidth.MM_80.value,
        nullable=False,
    )
    show_store_address: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    show_contact: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    show_tin: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    show_tax_details: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # ── 3. Audit Metadata ──
    updated_by_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Direct relationship to User for inspection
    updated_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[updated_by_id]
    )

    def __repr__(self) -> str:
        return f"<StoreSettings(id={self.id}, store_name='{self.store_name}', paper_width='{self.paper_width}')>"
