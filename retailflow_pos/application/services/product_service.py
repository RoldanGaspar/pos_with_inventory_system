"""
RetailFlow POS - Product Service
Coordinates product CRUD, catalog search, stock metrics, and archiving.
"""

import logging
from typing import NoReturn

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants import Status
from application.dto.product_dto import (
    CategoryOptionDTO,
    ProductFilterDTO,
    ProductFormDTO,
    ProductFormOptionsDTO,
    ProductListItemDTO,
    ProductMetricsDTO,
)
from application.validators.product_validators import validate_product_form
from domain.exceptions import (
    AuthorizationError,
    DuplicateBarcodeError,
    DuplicateSkuError,
    ProductNotFoundError,
)
from domain.rules.stock_rules import stock_status
from infrastructure.database.models.auth import User
from infrastructure.database.models.product import Product, ProductBarcode
from infrastructure.database.repositories.auth import AuditLogRepository
from infrastructure.database.repositories.product import (
    BrandRepository,
    CategoryRepository,
    InventoryRepository,
    ProductRepository,
    UnitRepository,
)
from shared.pagination import PaginatedResult

logger = logging.getLogger("retailflow.products")

PERMISSION_VIEW = "view_products"
PERMISSION_CREATE = "create_products"
PERMISSION_EDIT = "edit_products"
PERMISSION_DELETE = "delete_products"


class ProductService:
    """Handles all product and catalog operations."""

    def __init__(self, session: Session):
        self._session = session
        self.product_repo = ProductRepository(session)
        self.category_repo = CategoryRepository(session)
        self.brand_repo = BrandRepository(session)
        self.unit_repo = UnitRepository(session)
        self.inventory_repo = InventoryRepository(session)
        self.audit_repo = AuditLogRepository(session)

    # ─── Queries ───

    def search(self, filters: ProductFilterDTO, actor: User) -> PaginatedResult[ProductListItemDTO]:
        self._require_permission(actor, PERMISSION_VIEW)
        result = self.product_repo.search(
            keyword=filters.keyword,
            category_id=filters.category_id,
            status=filters.status,
            page=filters.page,
            page_size=filters.page_size,
        )
        items = [self._to_list_item(p) for p in result.items]
        return PaginatedResult(
            items=items,
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )

    def get_product(self, product_id: int, actor: User) -> Product:
        self._require_permission(actor, PERMISSION_VIEW)
        return self._get_product_or_raise(product_id)

    def get_metrics(self, actor: User) -> ProductMetricsDTO:
        self._require_permission(actor, PERMISSION_VIEW)
        return ProductMetricsDTO(
            total_products=self.product_repo.count_active(),
            low_stock=self.inventory_repo.count_low_stock(),
            out_of_stock=self.inventory_repo.count_out_of_stock(),
            categories=self.category_repo.count(),
        )

    def get_form_options(self, actor: User) -> ProductFormOptionsDTO:
        self._require_permission(actor, PERMISSION_VIEW)
        return ProductFormOptionsDTO(
            categories=[
                CategoryOptionDTO(id=c.id, name=c.name) for c in self.category_repo.get_active()
            ],
            brands=[CategoryOptionDTO(id=b.id, name=b.name) for b in self.brand_repo.get_active()],
            units=[CategoryOptionDTO(id=u.id, name=u.name) for u in self.unit_repo.get_all_units()],
        )

    # ─── Commands ───

    def create(self, dto: ProductFormDTO, actor: User) -> Product:
        validate_product_form(dto)
        self._require_permission(actor, PERMISSION_CREATE)
        self._ensure_sku_unique(dto.sku)
        self._ensure_barcode_unique(dto.barcode)

        try:
            product = Product(
                sku=dto.sku.strip(),
                name=dto.name.strip(),
                description=dto.description,
                category_id=dto.category_id,
                brand_id=dto.brand_id,
                base_unit_id=dto.base_unit_id,
                cost_price=dto.cost_price,
                selling_price=dto.selling_price,
                tax_type=dto.tax_type,
                status=dto.status,
                reorder_level=dto.reorder_level,
            )
            self._session.add(product)
            self._session.flush()

            if dto.barcode and dto.barcode.strip():
                self._session.add(
                    ProductBarcode(
                        product_id=product.id,
                        barcode=dto.barcode.strip(),
                        is_primary=True,
                    )
                )
                self._session.flush()

            self._audit(actor, "PRODUCT_CREATED", product.id)
            self._session.commit()
        except IntegrityError as e:
            self._session.rollback()
            self._map_integrity_error(e)

        logger.info(f"Product created: {product.sku}")
        return product

    def update(self, product_id: int, dto: ProductFormDTO, actor: User) -> Product:
        validate_product_form(dto)
        self._require_permission(actor, PERMISSION_EDIT)
        product = self._get_product_or_raise(product_id)
        self._ensure_sku_unique(dto.sku, exclude_id=product_id)
        self._ensure_barcode_unique(dto.barcode, exclude_id=product_id)

        product.sku = dto.sku.strip()
        product.name = dto.name.strip()
        product.description = dto.description
        product.category_id = dto.category_id
        product.brand_id = dto.brand_id
        product.base_unit_id = dto.base_unit_id
        product.cost_price = dto.cost_price
        product.selling_price = dto.selling_price
        product.tax_type = dto.tax_type
        product.status = dto.status
        product.reorder_level = dto.reorder_level

        self._replace_primary_barcode(product, dto.barcode)

        try:
            self._audit(actor, "PRODUCT_UPDATED", product.id)
            self._session.commit()
        except IntegrityError as e:
            self._session.rollback()
            self._map_integrity_error(e)

        logger.info(f"Product updated: {product.sku}")
        return product

    def archive(self, product_id: int, actor: User) -> None:
        self._require_permission(actor, PERMISSION_DELETE)
        product = self._get_product_or_raise(product_id)

        if product.status == Status.ARCHIVED:
            return

        product.status = Status.ARCHIVED
        self._audit(actor, "PRODUCT_ARCHIVED", product.id)
        self._session.commit()
        logger.info(f"Product archived: id={product_id}")

    def adjust_inventory(
        self,
        product_id: int,
        new_quantity: int,
        reason: str,
        actor: User,
    ) -> None:
        """Adjust product stock-on-hand quantity and record audit log."""
        if new_quantity < 0:
            raise ValidationError("Quantity on hand cannot be negative.")
        product = self._get_product_or_raise(product_id)

        self.inventory_repo.set_quantity(product.id, new_quantity)
        self._audit(actor, f"STOCK_ADJUSTED: {reason} (Qty: {new_quantity})", product.id)
        self._session.commit()
        logger.info(f"Inventory adjusted for product {product.sku}: qty={new_quantity}, reason='{reason}'")

    # ─── Helpers ───

    def _get_product_or_raise(self, product_id: int) -> Product:
        product = self.product_repo.get_with_details(product_id)
        if product is None:
            raise ProductNotFoundError(f"Product with id {product_id} not found.")
        return product

    def _require_permission(self, actor: User, permission: str) -> None:
        if not actor.has_permission(permission):
            raise AuthorizationError(f"You do not have permission: {permission}")

    def _ensure_sku_unique(self, sku: str, exclude_id: int | None = None) -> None:
        existing = self.product_repo.get_by_sku(sku.strip())
        if existing is not None and existing.id != exclude_id:
            raise DuplicateSkuError(f"SKU '{sku.strip()}' is already assigned to another product.")

    def _ensure_barcode_unique(self, barcode: str, exclude_id: int | None = None) -> None:
        if not barcode or not barcode.strip():
            return
        existing = self.product_repo.get_by_barcode(barcode.strip())
        if existing is not None and existing.id != exclude_id:
            raise DuplicateBarcodeError(
                f"Barcode '{barcode.strip()}' is already assigned to another product."
            )

    def _replace_primary_barcode(self, product: Product, barcode: str) -> None:
        barcode = barcode.strip() if barcode else ""
        primary = next((b for b in product.barcodes if b.is_primary), None)
        if barcode:
            if primary is not None:
                primary.barcode = barcode
            else:
                product.barcodes.append(
                    ProductBarcode(product_id=product.id, barcode=barcode, is_primary=True)
                )
        elif primary is not None:
            self._session.delete(primary)

    def _map_integrity_error(self, e: IntegrityError) -> NoReturn:
        message = str(e.orig).lower()
        if "barcode" in message:
            raise DuplicateBarcodeError("Barcode is already assigned to another product.")
        if "sku" in message:
            raise DuplicateSkuError("SKU is already assigned to another product.")
        raise e

    def _audit(self, actor: User, action: str, record_id: int) -> None:
        self.audit_repo.log_action(
            user_id=actor.id,
            username=actor.username,
            action=action,
            module="products",
            record_type="product",
            record_id=record_id,
        )

    def _to_list_item(self, product: Product) -> ProductListItemDTO:
        primary_barcode = next(
            (b.barcode for b in product.barcodes if b.is_primary),
            None,
        )
        if primary_barcode is None and product.barcodes:
            primary_barcode = product.barcodes[0].barcode

        quantity = product.inventory.quantity_on_hand if product.inventory is not None else 0
        return ProductListItemDTO(
            id=product.id,
            sku=product.sku,
            name=product.name,
            barcode=primary_barcode or "",
            category_name=product.category.name if product.category else "",
            cost_price=product.cost_price,
            selling_price=product.selling_price,
            status=product.status,
            stock_quantity=quantity,
            stock_status=stock_status(quantity, product.reorder_level),
            reorder_level=product.reorder_level,
        )
