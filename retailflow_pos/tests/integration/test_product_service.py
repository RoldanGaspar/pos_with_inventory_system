"""
Integration tests for the product service (real in-memory SQLite).
"""

from decimal import Decimal

import pytest

from app.constants import Status
from application.dto.product_dto import ProductFilterDTO, ProductFormDTO
from application.services.product_service import ProductService
from domain.exceptions import (
    AuthorizationError,
    DuplicateBarcodeError,
    DuplicateSkuError,
    ProductNotFoundError,
)
from infrastructure.database.models.inventory import Inventory
from infrastructure.database.models.product import Product, ProductBarcode
from tests.fixtures.product_factories import CategoryFactory, ProductBarcodeFactory, ProductFactory


def _form_dto(**overrides) -> ProductFormDTO:
    data = {
        "sku": "SKU-001",
        "name": "Test Product",
        "cost_price": Decimal("10.00"),
        "selling_price": Decimal("20.00"),
        "reorder_level": 0,
        "barcode": "4800000000001",
        "status": "active",
        "tax_type": "vat",
    }
    data.update(overrides)
    return ProductFormDTO(**data)


def _seed_product(db_session, sku, barcode, qty=0, reorder=0):
    product = ProductFactory.build(sku=sku, name=sku, reorder_level=reorder)
    db_session.add(product)
    db_session.flush()
    db_session.add(ProductBarcodeFactory.build(product_id=product.id, barcode=barcode))
    db_session.add(Inventory(product_id=product.id, quantity_on_hand=qty, quantity_allocated=0))
    db_session.commit()
    return product


def test_create_product(db_session, user_with_permissions):
    actor = user_with_permissions("create_products")
    service = ProductService(db_session)
    product = service.create(_form_dto(), actor)
    assert product.id is not None
    assert db_session.query(Product).count() == 1


def test_create_requires_permission(db_session, user_with_permissions):
    actor = user_with_permissions()
    service = ProductService(db_session)
    with pytest.raises(AuthorizationError):
        service.create(_form_dto(), actor)


def test_create_duplicate_sku_raises(db_session, user_with_permissions):
    actor = user_with_permissions("create_products")
    service = ProductService(db_session)
    service.create(_form_dto(sku="SKU-001", barcode="4800000000001"), actor)
    with pytest.raises(DuplicateSkuError):
        service.create(_form_dto(sku="SKU-001", barcode="4800000000002"), actor)


def test_create_duplicate_barcode_raises(db_session, user_with_permissions):
    actor = user_with_permissions("create_products")
    service = ProductService(db_session)
    service.create(_form_dto(sku="SKU-001", barcode="4800000000001"), actor)
    with pytest.raises(DuplicateBarcodeError):
        service.create(_form_dto(sku="SKU-002", barcode="4800000000001"), actor)


def test_update_product(db_session, user_with_permissions):
    actor = user_with_permissions("create_products", "edit_products")
    service = ProductService(db_session)
    product = service.create(_form_dto(sku="SKU-001", name="Old Name"), actor)

    updated = service.update(product.id, _form_dto(sku="SKU-001", name="New Name"), actor)
    assert updated.name == "New Name"


def test_update_requires_permission(db_session, user_with_permissions):
    actor = user_with_permissions("create_products")
    service = ProductService(db_session)
    product = service.create(_form_dto(sku="SKU-001"), actor)

    no_edit = user_with_permissions("create_products")
    with pytest.raises(AuthorizationError):
        service.update(product.id, _form_dto(sku="SKU-001", name="Hacked"), no_edit)


def test_archive_requires_permission(db_session, user_with_permissions):
    actor = user_with_permissions("create_products")
    service = ProductService(db_session)
    product = service.create(_form_dto(sku="SKU-001"), actor)

    no_delete = user_with_permissions("create_products")
    with pytest.raises(AuthorizationError):
        service.archive(product.id, no_delete)


def test_get_product_not_found(db_session, user_with_permissions):
    actor = user_with_permissions("view_products")
    service = ProductService(db_session)
    with pytest.raises(ProductNotFoundError):
        service.get_product(9999, actor)


def test_search_maps_stock_status(db_session, user_with_permissions):
    actor = user_with_permissions("view_products", "create_products")
    service = ProductService(db_session)
    service.create(_form_dto(sku="SKU-001", name="Low Item", reorder_level=5), actor)
    _seed_product(db_session, "SKU-002", "4800000000002", qty=2, reorder=5)

    result = service.search(ProductFilterDTO(), actor)
    assert result.total == 2
    item = next(i for i in result.items if i.sku == "SKU-002")
    assert item.stock_status == "low_stock"


def test_metrics(db_session, user_with_permissions):
    actor = user_with_permissions("view_products", "create_products")
    service = ProductService(db_session)
    service.create(_form_dto(sku="SKU-001", barcode="4800000000001"), actor)

    cat = CategoryFactory.build(name="Beverages")
    db_session.add(cat)
    db_session.commit()

    metrics = service.get_metrics(actor)
    assert metrics.total_products == 1
    assert metrics.categories == 1


def test_form_options_include_catalog_data(db_session, user_with_permissions):
    actor = user_with_permissions("view_products")
    cat = CategoryFactory.build(name="Beverages")
    db_session.add(cat)
    db_session.commit()
    service = ProductService(db_session)
    options = service.get_form_options(actor)
    assert len(options.categories) == 1
    assert options.categories[0].name == "Beverages"


# ─── Read authorization ───


def test_search_requires_view_permission(db_session, user_with_permissions):
    actor = user_with_permissions("create_products")
    service = ProductService(db_session)
    with pytest.raises(AuthorizationError):
        service.search(ProductFilterDTO(), actor)


def test_get_product_requires_view_permission(db_session, user_with_permissions):
    actor = user_with_permissions("create_products")
    service = ProductService(db_session)
    product = service.create(_form_dto(sku="SKU-001"), actor)
    with pytest.raises(AuthorizationError):
        service.get_product(product.id, actor)


def test_get_metrics_requires_view_permission(db_session, user_with_permissions):
    actor = user_with_permissions("create_products")
    service = ProductService(db_session)
    with pytest.raises(AuthorizationError):
        service.get_metrics(actor)


def test_get_form_options_requires_view_permission(db_session, user_with_permissions):
    actor = user_with_permissions("create_products")
    service = ProductService(db_session)
    with pytest.raises(AuthorizationError):
        service.get_form_options(actor)


# ─── Archive behavior ───


def test_archive_keeps_product_and_related_rows(db_session, user_with_permissions):
    actor = user_with_permissions("create_products", "delete_products")
    service = ProductService(db_session)
    product = service.create(_form_dto(sku="SKU-001", barcode="4800000000001"), actor)
    db_session.add(Inventory(product_id=product.id, quantity_on_hand=5, quantity_allocated=0))
    db_session.commit()

    service.archive(product.id, actor)

    archived = db_session.query(Product).filter(Product.id == product.id).first()
    assert archived is not None
    assert archived.status == Status.ARCHIVED
    assert (
        db_session.query(ProductBarcode).filter(ProductBarcode.product_id == product.id).count()
        == 1
    )
    assert db_session.query(Inventory).filter(Inventory.product_id == product.id).count() == 1


def test_archive_excluded_from_default_search(db_session, user_with_permissions):
    actor = user_with_permissions("view_products", "create_products", "delete_products")
    service = ProductService(db_session)
    product = service.create(_form_dto(sku="SKU-001"), actor)
    service.create(_form_dto(sku="SKU-002", barcode="4800000000002"), actor)

    service.archive(product.id, actor)

    result = service.search(ProductFilterDTO(), actor)
    assert result.total == 1
    assert result.items[0].sku == "SKU-002"


def test_archive_filterable_explicitly(db_session, user_with_permissions):
    actor = user_with_permissions("view_products", "create_products", "delete_products")
    service = ProductService(db_session)
    product = service.create(_form_dto(sku="SKU-001"), actor)
    service.archive(product.id, actor)

    result = service.search(ProductFilterDTO(status="archived"), actor)
    assert result.total == 1
    assert result.items[0].sku == "SKU-001"


def test_archive_is_idempotent(db_session, user_with_permissions):
    actor = user_with_permissions("view_products", "create_products", "delete_products")
    service = ProductService(db_session)
    product = service.create(_form_dto(sku="SKU-001"), actor)

    service.archive(product.id, actor)
    service.archive(product.id, actor)  # no error

    stored = db_session.query(Product).filter(Product.id == product.id).first()
    assert stored.status == Status.ARCHIVED


def test_metrics_exclude_archived(db_session, user_with_permissions):
    actor = user_with_permissions("view_products", "create_products", "delete_products")
    service = ProductService(db_session)
    product = service.create(_form_dto(sku="SKU-001"), actor)
    service.create(_form_dto(sku="SKU-002", barcode="4800000000002"), actor)

    service.archive(product.id, actor)

    metrics = service.get_metrics(actor)
    assert metrics.total_products == 1


# ─── IntegrityError mapping ───


def test_duplicate_sku_integrity_error_maps_and_rolls_back(db_session, user_with_permissions):
    actor = user_with_permissions("create_products")
    service = ProductService(db_session)
    service.create(_form_dto(sku="SKU-001", barcode="4800000000001"), actor)

    # Bypass the pre-check to simulate a race that reaches the DB unique constraint.
    service._ensure_sku_unique = lambda sku, exclude_id=None: None

    with pytest.raises(DuplicateSkuError):
        service.create(_form_dto(sku="SKU-001", barcode="4800000000002"), actor)

    # Session must remain usable after rollback.
    assert service.product_repo.count_active() == 1


def test_duplicate_barcode_integrity_error_maps(db_session, user_with_permissions):
    actor = user_with_permissions("create_products")
    service = ProductService(db_session)
    service.create(_form_dto(sku="SKU-001", barcode="4800000000001"), actor)

    service._ensure_barcode_unique = lambda barcode, exclude_id=None: None

    with pytest.raises(DuplicateBarcodeError):
        service.create(_form_dto(sku="SKU-002", barcode="4800000000001"), actor)

    assert service.product_repo.count_active() == 1
