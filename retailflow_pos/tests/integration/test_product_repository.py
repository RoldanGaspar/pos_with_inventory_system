"""
Integration tests for the product and inventory repositories (real in-memory SQLite).
"""

from decimal import Decimal

from infrastructure.database.models.inventory import Inventory
from infrastructure.database.repositories.product import InventoryRepository, ProductRepository
from tests.fixtures.product_factories import CategoryFactory, ProductBarcodeFactory, ProductFactory


def _add_product(db_session, sku, name, barcode, qty, reorder, category=None, status="active"):
    product = ProductFactory.build(
        sku=sku,
        name=name,
        status=status,
        reorder_level=reorder,
        selling_price=Decimal("20.00"),
        cost_price=Decimal("10.00"),
    )
    if category is not None:
        product.category = category
    db_session.add(product)
    db_session.flush()
    db_session.add(ProductBarcodeFactory.build(product_id=product.id, barcode=barcode))
    db_session.add(Inventory(product_id=product.id, quantity_on_hand=qty, quantity_allocated=0))
    db_session.commit()
    return product


def test_get_by_sku(db_session):
    product = _add_product(db_session, "SKU-1", "Coke", "4800000000001", 10, 5)
    repo = ProductRepository(db_session)
    found = repo.get_by_sku("SKU-1")
    assert found is not None
    assert found.id == product.id


def test_get_by_barcode(db_session):
    _add_product(db_session, "SKU-1", "Coke", "4800000000001", 10, 5)
    repo = ProductRepository(db_session)
    found = repo.get_by_barcode("4800000000001")
    assert found is not None
    assert found.sku == "SKU-1"


def test_search_by_name_keyword(db_session):
    _add_product(db_session, "SKU-1", "Coca-Cola", "4800000000001", 10, 5)
    _add_product(db_session, "SKU-2", "Nova Chips", "4800000000002", 0, 5)
    repo = ProductRepository(db_session)
    result = repo.search(keyword="coca")
    assert result.total == 1
    assert result.items[0].name == "Coca-Cola"


def test_search_by_sku_keyword(db_session):
    _add_product(db_session, "SKU-ABC", "Coca-Cola", "4800000000001", 10, 5)
    _add_product(db_session, "SKU-2", "Nova Chips", "4800000000002", 0, 5)
    repo = ProductRepository(db_session)
    result = repo.search(keyword="abc")
    assert result.total == 1
    assert result.items[0].sku == "SKU-ABC"


def test_search_by_barcode_keyword(db_session):
    _add_product(db_session, "SKU-1", "Coca-Cola", "4800000000001", 10, 5)
    _add_product(db_session, "SKU-2", "Nova Chips", "4800000000002", 0, 5)
    repo = ProductRepository(db_session)
    result = repo.search(keyword="4800000000002")
    assert result.total == 1
    assert result.items[0].sku == "SKU-2"


def test_search_filter_by_category(db_session):
    cat = CategoryFactory.build(name="Beverages")
    db_session.add(cat)
    db_session.flush()
    _add_product(db_session, "SKU-1", "Coca-Cola", "4800000000001", 10, 5, category=cat)
    _add_product(db_session, "SKU-2", "Nova Chips", "4800000000002", 0, 5)
    repo = ProductRepository(db_session)
    result = repo.search(category_id=cat.id)
    assert result.total == 1
    assert result.items[0].name == "Coca-Cola"


def test_search_filter_by_status(db_session):
    _add_product(db_session, "SKU-1", "Coke", "4800000000001", 10, 5, status="active")
    _add_product(db_session, "SKU-2", "Nova", "4800000000002", 0, 5, status="inactive")
    repo = ProductRepository(db_session)
    result = repo.search(status="inactive")
    assert result.total == 1
    assert result.items[0].sku == "SKU-2"


def test_search_excludes_archived_by_default(db_session):
    _add_product(db_session, "SKU-1", "Coke", "4800000000001", 10, 5, status="active")
    _add_product(db_session, "SKU-2", "Nova", "4800000000002", 0, 5, status="archived")
    repo = ProductRepository(db_session)
    result = repo.search()
    assert result.total == 1
    assert result.items[0].sku == "SKU-1"


def test_search_includes_archived_when_filtered(db_session):
    _add_product(db_session, "SKU-1", "Coke", "4800000000001", 10, 5, status="active")
    _add_product(db_session, "SKU-2", "Nova", "4800000000002", 0, 5, status="archived")
    repo = ProductRepository(db_session)
    result = repo.search(status="archived")
    assert result.total == 1
    assert result.items[0].sku == "SKU-2"


def test_pagination(db_session):
    for i in range(5):
        _add_product(db_session, f"SKU-{i}", f"Product {i}", f"48000000000{i:02d}", 10, 0)
    repo = ProductRepository(db_session)
    result = repo.search(page=1, page_size=2)
    assert result.total == 5
    assert len(result.items) == 2
    assert result.total_pages == 3
    assert result.has_next is True


# ─── InventoryRepository ───


def test_inventory_count_low_and_out_of_stock(db_session):
    _add_product(db_session, "SKU-1", "Coke", "4800000000001", 10, 5)  # in stock
    _add_product(db_session, "SKU-2", "Nova", "4800000000002", 2, 5)  # low stock
    _add_product(db_session, "SKU-3", "Piat", "4800000000003", 0, 5)  # out of stock
    repo = InventoryRepository(db_session)
    assert repo.count_low_stock() == 1
    assert repo.count_out_of_stock() == 1


def test_inventory_counts_exclude_archived(db_session):
    _add_product(db_session, "SKU-1", "Coke", "4800000000001", 10, 5)
    _add_product(db_session, "SKU-2", "Nova", "4800000000002", 0, 5, status="archived")
    repo = InventoryRepository(db_session)
    assert repo.count_out_of_stock() == 0


def test_set_quantity_creates_then_updates_single_row(db_session):
    product = ProductFactory.build(sku="SKU-1", name="Coke")
    db_session.add(product)
    db_session.flush()

    repo = InventoryRepository(db_session)
    inv = repo.set_quantity(product.id, 10)
    assert inv.quantity_on_hand == 10

    updated = repo.set_quantity(product.id, 25)
    assert updated.id == inv.id
    assert updated.quantity_on_hand == 25
    assert db_session.query(Inventory).count() == 1
