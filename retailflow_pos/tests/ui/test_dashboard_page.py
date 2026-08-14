"""
RetailFlow POS - Dashboard Page UI Tests
Tests PySide6 DashboardPage rendering, KPI card metrics, and quick action callbacks.
"""

from decimal import Decimal

import pytest

from application.services.product_service import ProductService
from application.services.sales_service import SalesService
from infrastructure.database.models.product import Product
from infrastructure.database.models.sales import Sale, SaleLineItem
from presentation.widgets.dashboard_page import DashboardPage


@pytest.fixture
def dashboard_sample(db_session, user_with_permissions):
    user = user_with_permissions("view_products", "view_sales")
    p1 = Product(
        sku="DASH-1",
        name="Dashboard Item A",
        cost_price=Decimal("10.00"),
        selling_price=Decimal("20.00"),
        reorder_level=5,
        status="active",
    )
    db_session.add(p1)
    db_session.flush()

    sale = Sale(
        transaction_number="TXN-DASH-0001",
        subtotal=Decimal("40.00"),
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("4.80"),
        total_amount=Decimal("44.80"),
        status="COMPLETED",
        payment_method="Cash",
        items=[
            SaleLineItem(
                product_id=p1.id,
                product_name=p1.name,
                unit_price=p1.selling_price,
                quantity=2,
                subtotal=Decimal("40.00"),
            )
        ],
    )
    db_session.add(sale)
    db_session.commit()

    return p1, sale, user


def test_dashboard_page_renders_metrics(qtbot, db_session, dashboard_sample):
    p1, sale, user = dashboard_sample
    product_service = ProductService(db_session)
    sales_service = SalesService(db_session)

    nav_called = []

    def mock_nav(key):
        nav_called.append(key)

    page = DashboardPage(user, product_service, sales_service, navigate_callback=mock_nav)
    qtbot.addWidget(page)

    assert page.tbl_top.rowCount() >= 1
    assert page.tbl_recent.rowCount() >= 1

    # Test quick action navigation callback
    page._navigate("pos")
    assert "pos" in nav_called
