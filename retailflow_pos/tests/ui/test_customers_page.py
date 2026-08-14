"""
RetailFlow POS - Customers Page UI Tests
Tests PySide6 CustomersPage rendering, search, loyalty tier filtering, and points adjustment.
"""

from decimal import Decimal

import pytest
from PySide6.QtCore import Qt

from application.dto.customer_dto import CreateCustomerDTO
from application.services.customer_service import CustomerService
from infrastructure.database.models.auth import User
from presentation.widgets.customers_page import CustomersPage


@pytest.fixture
def customers_sample(db_session, user_with_permissions):
    admin = user_with_permissions("view_customers", "create_customers", "edit_customers")
    customer_service = CustomerService(db_session)

    c1 = customer_service.create_customer(
        CreateCustomerDTO(
            name="Maria Santos",
            phone="09171234567",
            email="maria@gmail.com",
            address="Quezon City",
            initial_points=1250,
        ),
        actor=admin,
    )
    c2 = customer_service.create_customer(
        CreateCustomerDTO(
            name="Juan Dela Cruz",
            phone="09185557890",
            email="juan@yahoo.com",
            address="Makati City",
            initial_points=620,
        ),
        actor=admin,
    )
    c3 = customer_service.create_customer(
        CreateCustomerDTO(
            name="Ana Reyes",
            phone="09208881122",
            email="ana@corp.ph",
            address="Pasig City",
            initial_points=50,
        ),
        actor=admin,
    )
    db_session.commit()

    return admin, customer_service


def test_customers_page_renders_table(qtbot, customers_sample):
    admin, customer_service = customers_sample
    page = CustomersPage(admin, customer_service)
    qtbot.addWidget(page)

    assert page.tbl_customers.rowCount() >= 3
    assert int(page.card_total._value_label.text()) >= 3


def test_customers_page_search_filtering(qtbot, customers_sample):
    admin, customer_service = customers_sample
    page = CustomersPage(admin, customer_service)
    qtbot.addWidget(page)

    page.txt_search.setText("Maria")
    assert page.tbl_customers.rowCount() == 1

    page.txt_search.setText("09185557890")
    assert page.tbl_customers.rowCount() == 1

    page.txt_search.setText("NON_EXISTENT_CUSTOMER_PHONE_9999")
    assert page.tbl_customers.rowCount() == 0


def test_customers_page_tier_filtering(qtbot, customers_sample):
    admin, customer_service = customers_sample
    page = CustomersPage(admin, customer_service)
    qtbot.addWidget(page)

    idx = page.cmb_tier.findData("platinum")
    if idx >= 0:
        page.cmb_tier.setCurrentIndex(idx)
        assert page.tbl_customers.rowCount() >= 1

    idx_b = page.cmb_tier.findData("bronze")
    if idx_b >= 0:
        page.cmb_tier.setCurrentIndex(idx_b)
        assert page.tbl_customers.rowCount() >= 1


def test_customers_page_points_adjustment(qtbot, customers_sample):
    admin, customer_service = customers_sample
    c = customer_service.get_customer_by_phone("09208881122")
    assert c is not None
    assert c.tier == "bronze"

    # Add 100 points -> should upgrade to silver
    updated = customer_service.adjust_points(c.id, 100, reason="Test bonus", actor=admin)
    assert updated.loyalty_points == 150
    assert updated.tier == "silver"
