"""
UI tests for the product form dialog (pytest-qt).
"""

from decimal import Decimal

import pytest

from application.dto.product_dto import ProductFormDTO
from application.services.product_service import ProductService
from presentation.dialogs.product_form_dialog import ProductFormDialog


def _form_dto(sku, name, barcode="4800000000001"):
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
def test_add_flow_creates_product(qtbot, db_session, user_with_permissions):
    actor = user_with_permissions("view_products", "create_products")
    service = ProductService(db_session)

    dialog = ProductFormDialog(service, actor)
    qtbot.addWidget(dialog)
    dialog._sku_input.setText("SKU-001")
    dialog._name_input.setText("Coca-Cola")
    dialog._save()

    assert service.product_repo.count_active() == 1


@pytest.mark.ui
def test_edit_flow_prepopulates(qtbot, db_session, user_with_permissions):
    actor = user_with_permissions("view_products", "create_products", "edit_products")
    service = ProductService(db_session)
    product = service.create(_form_dto("SKU-001", "Coca-Cola"), actor)

    dialog = ProductFormDialog(service, actor, product=product)
    qtbot.addWidget(dialog)

    assert dialog._sku_input.text() == "SKU-001"
    assert dialog._name_input.text() == "Coca-Cola"
    assert dialog._barcode_input.text() == "4800000000001"


@pytest.mark.ui
def test_validation_error_displayed(qtbot, db_session, user_with_permissions):
    actor = user_with_permissions("view_products", "create_products")
    service = ProductService(db_session)

    dialog = ProductFormDialog(service, actor)
    qtbot.addWidget(dialog)
    dialog._sku_input.setText("")
    dialog._name_input.setText("Test Product")
    dialog._save()

    assert "SKU" in dialog._error_label.text()
    assert service.product_repo.count_active() == 0
