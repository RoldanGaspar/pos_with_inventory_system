"""
RetailFlow POS - Product & Catalog Repositories
Specialized queries for products, categories, brands, units, and inventory.
"""

from datetime import UTC, datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.constants import Status
from infrastructure.database.models.inventory import Inventory
from infrastructure.database.models.product import Brand, Category, Product, ProductBarcode, Unit
from infrastructure.database.repositories.base import SqlAlchemyRepository
from shared.pagination import PaginatedResult


class CategoryRepository(SqlAlchemyRepository[Category, int]):
    """Repository for product categories."""

    def __init__(self, session: Session):
        super().__init__(session, Category)

    def get_by_name(self, name: str) -> Category | None:
        return self._session.query(Category).filter(Category.name == name).first()

    def get_active(self) -> list[Category]:
        return (
            self._session.query(Category)
            .filter(Category.status == "active")
            .order_by(Category.name)
            .all()
        )


class BrandRepository(SqlAlchemyRepository[Brand, int]):
    """Repository for product brands."""

    def __init__(self, session: Session):
        super().__init__(session, Brand)

    def get_by_name(self, name: str) -> Brand | None:
        return self._session.query(Brand).filter(Brand.name == name).first()

    def get_active(self) -> list[Brand]:
        return (
            self._session.query(Brand).filter(Brand.status == "active").order_by(Brand.name).all()
        )


class UnitRepository(SqlAlchemyRepository[Unit, int]):
    """Repository for units of measure."""

    def __init__(self, session: Session):
        super().__init__(session, Unit)

    def get_by_name(self, name: str) -> Unit | None:
        return self._session.query(Unit).filter(Unit.name == name).first()

    def get_all_units(self) -> list[Unit]:
        return self._session.query(Unit).order_by(Unit.name).all()


class InventoryRepository(SqlAlchemyRepository[Inventory, int]):
    """Repository for inventory snapshots and stock aggregates."""

    def __init__(self, session: Session):
        super().__init__(session, Inventory)

    def get_by_product_id(self, product_id: int) -> Inventory | None:
        return self._session.query(Inventory).filter(Inventory.product_id == product_id).first()

    def set_quantity(self, product_id: int, quantity_on_hand: int) -> Inventory:
        inv = self.get_by_product_id(product_id)
        if inv is None:
            inv = Inventory(
                product_id=product_id,
                quantity_on_hand=quantity_on_hand,
                quantity_allocated=0,
                last_counted_at=datetime.now(UTC),
            )
            self._session.add(inv)
        else:
            inv.quantity_on_hand = quantity_on_hand
            inv.last_counted_at = datetime.now(UTC)
        self._session.flush()
        return inv

    def count_low_stock(self) -> int:
        return (
            self._session.query(Product)
            .join(Inventory, Inventory.product_id == Product.id)
            .filter(
                Product.status == Status.ACTIVE,
                Product.reorder_level > 0,
                Inventory.quantity_on_hand > 0,
                Inventory.quantity_on_hand <= Product.reorder_level,
            )
            .count()
        )

    def count_out_of_stock(self) -> int:
        return (
            self._session.query(Product)
            .outerjoin(Inventory, Inventory.product_id == Product.id)
            .filter(
                Product.status == Status.ACTIVE,
                or_(
                    Inventory.quantity_on_hand == 0,
                    Inventory.product_id.is_(None),
                ),
            )
            .count()
        )


class ProductRepository(SqlAlchemyRepository[Product, int]):
    """Repository for products with catalog search queries."""

    def __init__(self, session: Session):
        super().__init__(session, Product)

    @staticmethod
    def _detail_options():
        return (
            joinedload(Product.category),
            joinedload(Product.brand),
            joinedload(Product.unit),
            joinedload(Product.inventory),
            joinedload(Product.barcodes),
        )

    def get_by_sku(self, sku: str) -> Product | None:
        return self._session.query(Product).filter(Product.sku == sku).first()

    def get_by_barcode(self, barcode: str) -> Product | None:
        return (
            self._session.query(Product)
            .join(ProductBarcode, ProductBarcode.product_id == Product.id)
            .filter(ProductBarcode.barcode == barcode)
            .first()
        )

    def get_with_details(self, product_id: int) -> Product | None:
        return (
            self._session.query(Product)
            .options(*self._detail_options())
            .filter(Product.id == product_id)
            .first()
        )

    def search(
        self,
        keyword: str | None = None,
        category_id: int | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResult[Product]:
        query = self._session.query(Product)

        if keyword:
            like = f"%{keyword}%"
            query = query.outerjoin(ProductBarcode, ProductBarcode.product_id == Product.id).filter(
                or_(
                    Product.name.ilike(like),
                    Product.sku.ilike(like),
                    ProductBarcode.barcode.ilike(like),
                )
            )
        if category_id is not None:
            query = query.filter(Product.category_id == category_id)
        if status is not None:
            query = query.filter(Product.status == status)
        else:
            # Default catalog view excludes archived products.
            query = query.filter(Product.status != Status.ARCHIVED)

        filtered = query.distinct()
        total = filtered.count()
        items = (
            filtered.order_by(Product.name)
            .options(*self._detail_options())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return PaginatedResult(items=items, total=total, page=page, page_size=page_size)

    def count_active(self) -> int:
        return self._session.query(Product).filter(Product.status == Status.ACTIVE).count()
