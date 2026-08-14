"""
RetailFlow POS - Suppliers Page UI Tests
Tests PySide6 SuppliersPage rendering, search, payment terms filtering, and vendor creation.
"""

import pytest
from PySide6.QtCore import Qt

from application.dto.supplier_dto import CreateSupplierDTO
from application.services.supplier_service import SupplierService
from presentation.widgets.suppliers_page import SuppliersPage


@pytest.fixture
def suppliers_sample(db_session, user_with_permissions):
    admin = user_with_permissions("view_suppliers", "manage_suppliers")
    supplier_service = SupplierService(db_session)

    s1 = supplier_service.create_supplier(
        CreateSupplierDTO(
            code="SUP-001",
            name="Coca-Cola Beverages Philippines, Inc.",
            contact_person="Eduardo Rodriguez",
            phone="+63 2 8888 1234",
            email="orders@coca-cola.com.ph",
            address="Taguig City",
            payment_terms="NET_30",
            tax_id="000-123-456-000",
        ),
        actor=admin,
    )
    s2 = supplier_service.create_supplier(
        CreateSupplierDTO(
            code="SUP-002",
            name="Benguet Fresh Produce",
            contact_person="Mang Jose",
            phone="+63 917 555 4321",
            email="produce@gmail.com",
            address="Benguet",
            payment_terms="COD",
            tax_id="123-888-999-000",
        ),
        actor=admin,
    )
    db_session.commit()

    return admin, supplier_service


def test_suppliers_page_renders_table(qtbot, suppliers_sample):
    admin, supplier_service = suppliers_sample
    page = SuppliersPage(admin, supplier_service)
    qtbot.addWidget(page)

    assert page.tbl_suppliers.rowCount() >= 2
    assert int(page.card_total._value_label.text()) >= 2


def test_suppliers_page_search_filtering(qtbot, suppliers_sample):
    admin, supplier_service = suppliers_sample
    page = SuppliersPage(admin, supplier_service)
    qtbot.addWidget(page)

    page.txt_search.setText("Coca-Cola")
    assert page.tbl_suppliers.rowCount() == 1

    page.txt_search.setText("SUP-002")
    assert page.tbl_suppliers.rowCount() == 1

    page.txt_search.setText("NON_EXISTENT_SUPPLIER_9999")
    assert page.tbl_suppliers.rowCount() == 0


def test_suppliers_page_terms_filtering(qtbot, suppliers_sample):
    admin, supplier_service = suppliers_sample
    page = SuppliersPage(admin, supplier_service)
    qtbot.addWidget(page)

    idx = page.cmb_terms.findData("NET_30")
    if idx >= 0:
        page.cmb_terms.setCurrentIndex(idx)
        assert page.tbl_suppliers.rowCount() >= 1

    idx_cod = page.cmb_terms.findData("COD")
    if idx_cod >= 0:
        page.cmb_terms.setCurrentIndex(idx_cod)
        assert page.tbl_suppliers.rowCount() >= 1
