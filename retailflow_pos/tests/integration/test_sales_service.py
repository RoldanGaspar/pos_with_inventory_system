"""
RetailFlow POS - Sales Service Integration Tests
Tests checkout workflow, stock deduction, validation, and sales reporting.
"""

from decimal import Decimal

import pytest

from application.dto.sales_dto import CartItemDTO, CheckoutRequestDTO
from application.services.product_service import ProductService
from application.services.sales_service import SalesService
from domain.exceptions import InsufficientStockError, PaymentError, ValidationError
from infrastructure.database.models.product import Product
from infrastructure.database.repositories.product import InventoryRepository


@pytest.fixture
def sales_service(db_session):
    return SalesService(db_session)


@pytest.fixture
def product_with_stock(db_session):
    product = Product(
        sku="TEST-SKU-100",
        name="Test Product 100",
        cost_price=Decimal("5.00"),
        selling_price=Decimal("10.00"),
        status="active",
        reorder_level=2,
    )
    db_session.add(product)
    db_session.flush()

    inv_repo = InventoryRepository(db_session)
    inv_repo.set_quantity(product.id, 10)
    db_session.commit()
    return product


def test_checkout_successful(sales_service, db_session, user_with_permissions, product_with_stock):
    user = user_with_permissions("process_sale")
    cart_item = CartItemDTO(
        product_id=product_with_stock.id,
        sku=product_with_stock.sku,
        name=product_with_stock.name,
        unit_price=product_with_stock.selling_price,
        quantity=2,
        available_stock=10,
    )

    # Subtotal = 20.00, Tax 12% = 2.40 -> Total = 22.40
    checkout_req = CheckoutRequestDTO(
        items=[cart_item],
        payment_method="CASH",
        amount_tendered=Decimal("30.00"),
        discount_amount=Decimal("0.00"),
        cashier_id=user.id,
    )

    response = sales_service.process_checkout(checkout_req, user)

    assert response.transaction_number.startswith("TXN-")
    assert response.subtotal == Decimal("20.00")
    assert response.tax_amount == Decimal("2.40")
    assert response.total_amount == Decimal("22.40")
    assert response.amount_paid == Decimal("30.00")
    assert response.change_given == Decimal("7.60")

    # Check stock deduction
    inv_repo = InventoryRepository(db_session)
    inv = inv_repo.get_by_product_id(product_with_stock.id)
    assert inv.quantity_on_hand == 8


def test_checkout_empty_cart_raises(sales_service, user_with_permissions):
    user = user_with_permissions("process_sale")
    req = CheckoutRequestDTO(
        items=[],
        payment_method="CASH",
        amount_tendered=Decimal("10.00"),
    )
    with pytest.raises(ValidationError):
        sales_service.process_checkout(req, user)


def test_checkout_insufficient_stock_raises(sales_service, user_with_permissions, product_with_stock):
    user = user_with_permissions("process_sale")
    cart_item = CartItemDTO(
        product_id=product_with_stock.id,
        sku=product_with_stock.sku,
        name=product_with_stock.name,
        unit_price=product_with_stock.selling_price,
        quantity=15,  # Stock is only 10
        available_stock=10,
    )
    req = CheckoutRequestDTO(
        items=[cart_item],
        payment_method="CASH",
        amount_tendered=Decimal("200.00"),
    )
    with pytest.raises(InsufficientStockError):
        sales_service.process_checkout(req, user)


def test_checkout_insufficient_payment_raises(sales_service, user_with_permissions, product_with_stock):
    user = user_with_permissions("process_sale")
    cart_item = CartItemDTO(
        product_id=product_with_stock.id,
        sku=product_with_stock.sku,
        name=product_with_stock.name,
        unit_price=product_with_stock.selling_price,
        quantity=1,
        available_stock=10,
    )
    # Total due = 11.20, tendered = 5.00
    req = CheckoutRequestDTO(
        items=[cart_item],
        payment_method="CASH",
        amount_tendered=Decimal("5.00"),
    )
    with pytest.raises(PaymentError):
        sales_service.process_checkout(req, user)


def test_today_sales_summary(sales_service, user_with_permissions, product_with_stock):
    user = user_with_permissions("process_sale")
    cart_item = CartItemDTO(
        product_id=product_with_stock.id,
        sku=product_with_stock.sku,
        name=product_with_stock.name,
        unit_price=product_with_stock.selling_price,
        quantity=1,
        available_stock=10,
    )
    req = CheckoutRequestDTO(
        items=[cart_item],
        payment_method="CASH",
        amount_tendered=Decimal("20.00"),
    )
    sales_service.process_checkout(req, user)

    rev, count = sales_service.get_today_summary()
    assert count == 1
    assert rev == Decimal("11.20")
