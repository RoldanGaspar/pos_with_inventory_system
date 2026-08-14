"""
RetailFlow POS - POS Page UI Tests
Tests PySide6 POS page rendering, cart interactions, and clear cart.
"""

from decimal import Decimal

import pytest
from PySide6.QtCore import Qt

from application.services.product_service import ProductService
from application.services.sales_service import SalesService
from infrastructure.database.models.product import Product
from infrastructure.database.repositories.product import InventoryRepository
from presentation.widgets.pos_page import POSPage


@pytest.fixture
def product_sample(db_session):
    p = Product(
        sku="POS-ITEM-1",
        name="POS Test Item",
        cost_price=Decimal("10.00"),
        selling_price=Decimal("25.00"),
        status="active",
    )
    db_session.add(p)
    db_session.flush()

    inv_repo = InventoryRepository(db_session)
    inv_repo.set_quantity(p.id, 20)
    db_session.commit()
    return p


def test_pos_page_renders_products(qtbot, db_session, user_with_permissions, product_sample):
    user = user_with_permissions("view_products", "process_sale")
    product_service = ProductService(db_session)
    sales_service = SalesService(db_session)

    page = POSPage(user, product_service, sales_service)
    qtbot.addWidget(page)

    assert page.tbl_products.rowCount() == 1
    assert page.tbl_products.item(0, 0).text() == "POS-ITEM-1"
    assert page.tbl_products.item(0, 1).text() == "POS Test Item"


def test_cart_add_and_clear(qtbot, db_session, user_with_permissions, product_sample):
    user = user_with_permissions("view_products", "process_sale")
    product_service = ProductService(db_session)
    sales_service = SalesService(db_session)

    page = POSPage(user, product_service, sales_service)
    qtbot.addWidget(page)

    # Click "+ Add" button on row 0
    btn_add = page.tbl_products.cellWidget(0, 4)
    assert btn_add is not None
    qtbot.mouseClick(btn_add, Qt.LeftButton)

    # Cart table should now have 1 item
    assert page.tbl_cart.rowCount() == 1
    assert page.lbl_subtotal.text() == "₱25.00"
    assert page.lbl_tax.text() == "₱3.00"
    assert page.lbl_total.text() == "₱28.00"

    # Click "Clear Cart"
    qtbot.mouseClick(page.btn_clear, Qt.LeftButton)
    assert page.tbl_cart.rowCount() == 0
    assert page.lbl_total.text() == "₱0.00"
