"""
RetailFlow POS - Product DTOs
Data transfer objects for the product module.
"""

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class ProductFormDTO:
    """Input payload for creating or updating a product."""

    sku: str
    name: str
    description: str | None = None
    category_id: int | None = None
    brand_id: int | None = None
    base_unit_id: int | None = None
    cost_price: Decimal = Decimal("0")
    selling_price: Decimal = Decimal("0")
    tax_type: str = "vat"
    status: str = "active"
    reorder_level: int = 0
    barcode: str = ""


@dataclass
class ProductFilterDTO:
    """Filter parameters for the product catalog search."""

    keyword: str | None = None
    category_id: int | None = None
    status: str | None = None
    page: int = 1
    page_size: int = 20


@dataclass
class ProductListItemDTO:
    """Row data for the product catalog table."""

    id: int
    sku: str
    name: str
    barcode: str
    category_name: str
    cost_price: Decimal
    selling_price: Decimal
    status: str
    stock_quantity: int
    stock_status: str
    reorder_level: int = 0


@dataclass
class ProductMetricsDTO:
    """Summary metrics for the catalog header cards."""

    total_products: int = 0
    low_stock: int = 0
    out_of_stock: int = 0
    categories: int = 0


@dataclass
class CategoryOptionDTO:
    """Dropdown option for category/brand/unit selectors."""

    id: int
    name: str


@dataclass
class ProductFormOptionsDTO:
    """Options needed to populate the product form dropdowns."""

    categories: list[CategoryOptionDTO] = field(default_factory=list)
    brands: list[CategoryOptionDTO] = field(default_factory=list)
    units: list[CategoryOptionDTO] = field(default_factory=list)
