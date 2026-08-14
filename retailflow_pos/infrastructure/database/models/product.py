"""
RetailFlow POS - Product & Catalog Models
SQLAlchemy ORM models for Products, Categories, Brands, Units, and Barcodes.
"""

from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import Status, TaxType
from infrastructure.database.models.base import BaseEntity

if TYPE_CHECKING:
    from infrastructure.database.models.inventory import Inventory


class Category(BaseEntity):
    """Product category with optional hierarchical parent."""

    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default=Status.ACTIVE, nullable=False)

    parent: Mapped[Optional["Category"]] = relationship(
        "Category", remote_side="Category.id", back_populates="children"
    )
    children: Mapped[list["Category"]] = relationship("Category", back_populates="parent")
    products: Mapped[list["Product"]] = relationship("Product", back_populates="category")

    def __repr__(self) -> str:
        return f"<Category(name={self.name})>"


class Brand(BaseEntity):
    """Product brand."""

    __tablename__ = "brands"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=Status.ACTIVE, nullable=False)

    products: Mapped[list["Product"]] = relationship("Product", back_populates="brand")

    def __repr__(self) -> str:
        return f"<Brand(name={self.name})>"


class Unit(BaseEntity):
    """Unit of measure (piece, box, kg, etc.)."""

    __tablename__ = "units"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    abbreviation: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)

    products: Mapped[list["Product"]] = relationship("Product", back_populates="unit")

    def __repr__(self) -> str:
        return f"<Unit(name={self.name})>"


class Product(BaseEntity):
    """Product catalog entry."""

    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True
    )
    brand_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("brands.id"), nullable=True)
    base_unit_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("units.id"), nullable=True)

    cost_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    selling_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    tax_type: Mapped[str] = mapped_column(String(20), default=TaxType.VAT, nullable=False)

    status: Mapped[str] = mapped_column(String(20), default=Status.ACTIVE, nullable=False)
    reorder_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    has_batch_tracking: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_expiry: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    category: Mapped[Category | None] = relationship("Category", back_populates="products")
    brand: Mapped[Brand | None] = relationship("Brand", back_populates="products")
    unit: Mapped[Unit | None] = relationship("Unit", back_populates="products")
    barcodes: Mapped[list["ProductBarcode"]] = relationship(
        "ProductBarcode",
        back_populates="product",
        cascade="all, delete-orphan",
    )
    inventory: Mapped[Optional["Inventory"]] = relationship(
        "Inventory", back_populates="product", uselist=False
    )

    def __repr__(self) -> str:
        return f"<Product(sku={self.sku}, name={self.name})>"


class ProductBarcode(BaseEntity):
    """Barcode assigned to a product. A product may have multiple barcodes."""

    __tablename__ = "product_barcodes"

    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False, index=True
    )
    barcode: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    product: Mapped[Product] = relationship("Product", back_populates="barcodes")

    def __repr__(self) -> str:
        return f"<ProductBarcode(barcode={self.barcode})>"
