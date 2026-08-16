"""
RetailFlow POS - Purchasing Page UI Tests
Tests PySide6 PurchasingPage rendering, search, status filtering, and stock intake receiving.
"""

from decimal import Decimal

import pytest
from PySide6.QtCore import Qt

from application.dto.purchasing_dto import CreatePOItemDTO, CreatePurchaseOrderDTO
from application.dto.supplier_dto import CreateSupplierDTO
from application.services.product_service import ProductService
from application.services.purchasing_service import PurchasingService
from application.services.supplier_service import SupplierService
from infrastructure.database.models.inventory import Inventory
from infrastructure.database.models.product import Product
from presentation.widgets.purchasing_page import PurchasingPage


@pytest.fixture
def purchasing_sample(db_session, user_with_permissions):
    admin = user_with_permissions(
        "view_purchase_orders", "create_purchase_orders", "approve_purchase_orders", "view_products"
    )
    supplier_service = SupplierService(db_session)
    product_service = ProductService(db_session)
    purchasing_service = PurchasingService(db_session)

    # 1. Create Supplier
    sup = supplier_service.create_supplier(
        CreateSupplierDTO(
            code="SUP-001",
            name="Coca-Cola Beverages PH",
            contact_person="Eduardo",
            phone="+63 2 8888 1234",
            email="orders@coca-cola.com.ph",
        ),
        actor=admin,
    )

    # 2. Create Product
    prod = Product(
        sku="BEV-001",
        name="Coca-Cola 330ml Can",
        cost_price=Decimal("25.00"),
        selling_price=Decimal("35.00"),
        status="active",
    )
    db_session.add(prod)
    db_session.flush()

    inv = Inventory(product_id=prod.id, quantity_on_hand=10)
    db_session.add(inv)
    db_session.commit()

    # 3. Create PO
    po = purchasing_service.create_po(
        CreatePurchaseOrderDTO(
            supplier_id=sup.id,
            status="ORDERED",
            items=[
                CreatePOItemDTO(
                    product_id=prod.id,
                    quantity=40,
                    unit_cost=Decimal("25.00"),
                )
            ],
            notes="Restock delivery",
        ),
        actor=admin,
    )
    db_session.commit()

    return admin, purchasing_service, supplier_service, product_service, po, prod


def test_purchasing_page_renders_table(qtbot, purchasing_sample):
    admin, purchasing_service, supplier_service, product_service, po, prod = purchasing_sample
    page = PurchasingPage(admin, purchasing_service, supplier_service, product_service)
    qtbot.addWidget(page)

    assert page.tbl_pos.rowCount() >= 1
    assert int(page.card_total._value_label.text()) >= 1


def test_purchasing_page_search_filtering(qtbot, purchasing_sample):
    admin, purchasing_service, supplier_service, product_service, po, prod = purchasing_sample
    page = PurchasingPage(admin, purchasing_service, supplier_service, product_service)
    qtbot.addWidget(page)

    page.txt_search.setText(po.po_number)
    assert page.tbl_pos.rowCount() == 1

    page.txt_search.setText("NON_EXISTENT_PO_NUMBER_9999")
    assert page.tbl_pos.rowCount() == 0


def test_purchasing_page_status_filtering(qtbot, purchasing_sample):
    admin, purchasing_service, supplier_service, product_service, po, prod = purchasing_sample
    page = PurchasingPage(admin, purchasing_service, supplier_service, product_service)
    qtbot.addWidget(page)

    idx = page.cmb_status.findData("ORDERED")
    if idx >= 0:
        page.cmb_status.setCurrentIndex(idx)
        assert page.tbl_pos.rowCount() >= 1


def test_purchasing_service_receive_stock_increments_inventory(purchasing_sample, db_session):
    admin, purchasing_service, supplier_service, product_service, po, prod = purchasing_sample

    initial_inv = db_session.query(Inventory).filter(Inventory.product_id == prod.id).first()
    assert initial_inv.quantity_on_hand == 10

    # Receive PO of 40 units -> inventory should become 50
    updated_po = purchasing_service.receive_stock(po.id, actor=admin)
    assert updated_po.status == "RECEIVED"

    db_session.refresh(initial_inv)
    assert initial_inv.quantity_on_hand == 50
