"""
RetailFlow POS - Sales Page UI Tests
Tests PySide6 SalesPage rendering, transaction search, and modal interactions.
"""

from decimal import Decimal

import pytest
from PySide6.QtCore import Qt

from application.dto.sales_dto import CartItemDTO, CheckoutRequestDTO
from application.services.sales_service import SalesService
from infrastructure.database.models.product import Product
from infrastructure.database.repositories.product import InventoryRepository
from presentation.widgets.sales_page import SalesPage


@pytest.fixture
def sale_sample(db_session, user_with_permissions):
    user = user_with_permissions("view_products", "process_sale", "view_sales")
    p = Product(
        sku="SALE-TEST-1",
        name="Sales Test Item",
        cost_price=Decimal("15.00"),
        selling_price=Decimal("30.00"),
        status="active",
    )
    db_session.add(p)
    db_session.flush()

    inv_repo = InventoryRepository(db_session)
    inv_repo.set_quantity(p.id, 50)
    db_session.commit()

    sales_service = SalesService(db_session)
    req = CheckoutRequestDTO(
        items=[
            CartItemDTO(
                product_id=p.id,
                sku=p.sku,
                name=p.name,
                unit_price=p.selling_price,
                quantity=2,
            )
        ],
        amount_tendered=Decimal("100.00"),
        payment_method="Cash",
    )
    sale_resp = sales_service.process_checkout(req, actor=user)
    return sale_resp, user


def test_sales_page_renders_completed_sales(qtbot, db_session, sale_sample):
    sale_resp, user = sale_sample
    sales_service = SalesService(db_session)

    page = SalesPage(user, sales_service)
    qtbot.addWidget(page)

    assert page.tbl_sales.rowCount() >= 1
    txn_item = page.tbl_sales.item(0, 0)
    assert txn_item is not None
    assert sale_resp.transaction_number in txn_item.text()


def test_sales_page_search_filter(qtbot, db_session, sale_sample):
    sale_resp, user = sale_sample
    sales_service = SalesService(db_session)

    page = SalesPage(user, sales_service)
    qtbot.addWidget(page)

    # Search matching keyword
    page.txt_search.setText(sale_resp.transaction_number[:6])
    assert page.tbl_sales.rowCount() >= 1

    # Search non-matching keyword
    page.txt_search.setText("NON_EXISTENT_TXN_999")
    assert page.tbl_sales.rowCount() == 0
