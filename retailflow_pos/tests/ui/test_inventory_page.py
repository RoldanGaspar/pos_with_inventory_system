"""
RetailFlow POS - Inventory Page UI Tests
Tests PySide6 InventoryPage rendering, stock status filtering, and stock adjustments.
"""

from decimal import Decimal

import pytest
from PySide6.QtCore import Qt

from application.services.product_service import ProductService
from infrastructure.database.models.product import Product
from infrastructure.database.repositories.product import InventoryRepository
from presentation.widgets.inventory_page import InventoryPage


@pytest.fixture
def inventory_sample(db_session, user_with_permissions):
    user = user_with_permissions("view_products", "edit_products")
    p1 = Product(
        sku="INV-TEST-1",
        name="Inventory Item In Stock",
        cost_price=Decimal("10.00"),
        selling_price=Decimal("20.00"),
        reorder_level=5,
        status="active",
    )
    p2 = Product(
        sku="INV-TEST-2",
        name="Inventory Item Out of Stock",
        cost_price=Decimal("5.00"),
        selling_price=Decimal("10.00"),
        reorder_level=5,
        status="active",
    )
    db_session.add_all([p1, p2])
    db_session.flush()

    inv_repo = InventoryRepository(db_session)
    inv_repo.set_quantity(p1.id, 25)
    inv_repo.set_quantity(p2.id, 0)
    db_session.commit()

    return p1, p2, user


def test_inventory_page_renders_products(qtbot, db_session, inventory_sample):
    p1, p2, user = inventory_sample
    product_service = ProductService(db_session)

    page = InventoryPage(user, product_service)
    qtbot.addWidget(page)

    assert page.tbl_inventory.rowCount() >= 2


def test_inventory_page_status_filter(qtbot, db_session, inventory_sample):
    p1, p2, user = inventory_sample
    product_service = ProductService(db_session)

    page = InventoryPage(user, product_service)
    qtbot.addWidget(page)

    # Filter Out of Stock
    idx = page.cmb_stock_filter.findText("Out of Stock")
    page.cmb_stock_filter.setCurrentIndex(idx)
    assert page.tbl_inventory.rowCount() >= 1

    # Filter In Stock
    idx_in = page.cmb_stock_filter.findText("In Stock")
    page.cmb_stock_filter.setCurrentIndex(idx_in)
    assert page.tbl_inventory.rowCount() >= 1
