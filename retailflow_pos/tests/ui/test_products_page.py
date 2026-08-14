"""
UI tests for the products page (pytest-qt).
"""

from decimal import Decimal

import pytest
from PySide6.QtWidgets import QMessageBox

from application.dto.product_dto import ProductFormDTO
from application.services.product_service import ProductService
from presentation.widgets.products_page import ProductsPage


def _form_dto(sku, name, barcode):
    return ProductFormDTO(
        sku=sku,
        name=name,
        cost_price=Decimal("10.00"),
        selling_price=Decimal("20.00"),
        barcode=barcode,
        reorder_level=0,
        status="active",
        tax_type="vat",
    )


@pytest.mark.ui
def test_page_renders_products(qtbot, db_session, user_with_permissions):
    actor = user_with_permissions(
        "view_products", "create_products", "edit_products", "delete_products"
    )
    service = ProductService(db_session)
    service.create(_form_dto("SKU-001", "Coca-Cola", "4800000000001"), actor)
    service.create(_form_dto("SKU-002", "Nova Chips", "4800000000002"), actor)

    page = ProductsPage(actor, service)
    qtbot.addWidget(page)

    assert page._model.rowCount() == 2
    assert page._total_card._value_label.text() == "2"


@pytest.mark.ui
def test_search_filters_results(qtbot, db_session, user_with_permissions):
    actor = user_with_permissions("view_products", "create_products")
    service = ProductService(db_session)
    service.create(_form_dto("SKU-001", "Coca-Cola", "4800000000001"), actor)
    service.create(_form_dto("SKU-002", "Nova Chips", "4800000000002"), actor)

    page = ProductsPage(actor, service)
    qtbot.addWidget(page)

    page._search.setText("coca")
    page._apply_search()
    assert page._model.rowCount() == 1


@pytest.mark.ui
def test_empty_state_on_no_matches(qtbot, db_session, user_with_permissions):
    actor = user_with_permissions("view_products")
    service = ProductService(db_session)

    page = ProductsPage(actor, service)
    qtbot.addWidget(page)

    page._search.setText("zzzz-no-match")
    page._apply_search()
    assert page._stack.currentIndex() == 0


@pytest.mark.ui
def test_status_filtering(qtbot, db_session, user_with_permissions):
    actor = user_with_permissions("view_products", "create_products", "delete_products")
    service = ProductService(db_session)
    service.create(_form_dto("SKU-001", "Coca-Cola", "4800000000001"), actor)
    archived = service.create(_form_dto("SKU-002", "Nova Chips", "4800000000002"), actor)
    service.archive(archived.id, actor)

    page = ProductsPage(actor, service)
    qtbot.addWidget(page)
    assert page._model.rowCount() == 1  # archived excluded by default

    page._status_combo.setCurrentIndex(page._status_combo.findData("archived"))
    assert page._model.rowCount() == 1
    assert page._model.item_at(0).sku == "SKU-002"


@pytest.mark.ui
def test_no_access_state(qtbot, db_session, user_with_permissions):
    actor = user_with_permissions()  # no view_products
    service = ProductService(db_session)

    page = ProductsPage(actor, service)
    qtbot.addWidget(page)
    assert page._stack.currentIndex() == 0


@pytest.mark.ui
def test_add_button_hidden_without_create_permission(qtbot, db_session, user_with_permissions):
    actor = user_with_permissions("view_products")
    service = ProductService(db_session)

    page = ProductsPage(actor, service)
    qtbot.addWidget(page)
    assert not page._add_btn.isVisible()


@pytest.mark.ui
def test_archive_confirmation_calls_service(qtbot, db_session, user_with_permissions, monkeypatch):
    actor = user_with_permissions("view_products", "create_products", "delete_products")
    service = ProductService(db_session)
    product = service.create(_form_dto("SKU-001", "Coca-Cola", "4800000000001"), actor)

    page = ProductsPage(actor, service)
    qtbot.addWidget(page)

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    page._archive_product(product.id)

    assert service.get_product(product.id, actor).status == "archived"
