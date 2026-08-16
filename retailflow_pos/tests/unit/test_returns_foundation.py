"""
RetailFlow POS - Returns Foundation & ORM Model Unit Tests (Phase 2B.1)
Verifies Returns V1 constants, normalized reason codes, non-destructive ORM relationships,
database constraints, DTO immutability, and preservation of immutable completed Sale records.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.constants import (
    DerivedReturnState,
    RefundMethod,
    ReturnDisposition,
    ReturnReason,
    ReturnStatus,
)
from application.dto.returns_dto import (
    ProcessReturnRequestDTO,
    ReturnableLineItemDTO,
    ReturnItemRequestDTO,
    SaleReturnSummaryDTO,
    SalesReturnDTO,
    SalesReturnItemDTO,
)
from infrastructure.database.models.auth import Role, User
from infrastructure.database.models.product import Product
from infrastructure.database.models.returns import SalesReturn, SalesReturnItem
from infrastructure.database.models.sales import Payment, Sale, SaleLineItem


@pytest.fixture
def test_user(db_session):
    user = User(
        username="cashier_test",
        password_hash="dummy",
        full_name="Cashier Test User",
    )
    manager = User(
        username="manager_test",
        password_hash="dummy",
        full_name="Manager Test User",
    )
    db_session.add_all([user, manager])
    db_session.commit()
    return user, manager


@pytest.fixture
def test_sale(db_session, test_user):
    cashier, _ = test_user
    prod = Product(
        sku="RET-TEST-SKU-1",
        name="Return Test Product",
        cost_price=Decimal("40.00"),
        selling_price=Decimal("100.00"),
    )
    db_session.add(prod)
    db_session.flush()

    line = SaleLineItem(
        product_id=prod.id,
        product_name=prod.name,
        unit_price=Decimal("100.00"),
        unit_cost=Decimal("40.00"),
        quantity=5,
        subtotal=Decimal("500.00"),
    )
    sale = Sale(
        transaction_number="TXN-20260815-9999",
        cashier_id=cashier.id,
        subtotal=Decimal("500.00"),
        discount_amount=Decimal("50.00"),
        tax_amount=Decimal("54.00"),
        total_amount=Decimal("504.00"),
        status="COMPLETED",
        payment_method="CASH",
        items=[line],
    )
    payment = Payment(
        sale_id=sale.id,
        payment_method="CASH",
        amount_paid=Decimal("504.00"),
        change_given=Decimal("0.00"),
    )
    sale.payments.append(payment)
    db_session.add(sale)
    db_session.commit()
    return sale, line, prod


# ── 1. Constants Verification ─────────────────────────────────────────

def test_returns_constants_values():
    """Verify all canonical Returns V1 constants."""
    assert ReturnStatus.COMPLETED == "completed"
    assert ReturnDisposition.RESTOCK == "restock"
    assert ReturnDisposition.DAMAGED_WRITE_OFF == "damaged_write_off"
    assert RefundMethod.CASH == "cash"
    assert RefundMethod.ORIGINAL_METHOD == "original_method"
    assert DerivedReturnState.NONE == "none"
    assert DerivedReturnState.PARTIAL == "partial"
    assert DerivedReturnState.FULL == "full"
    assert ReturnReason.DEFECTIVE == "defective"
    assert ReturnReason.WRONG_ITEM == "wrong_item"
    assert ReturnReason.CUSTOMER_CHANGE_MIND == "customer_change_mind"
    assert ReturnReason.EXPIRED == "expired"
    assert ReturnReason.OTHER == "other"


# ── 2. ORM Model Creation & Relationships ────────────────────────────

def test_sales_return_orm_persistence(db_session, test_user, test_sale):
    """SalesReturn and SalesReturnItem persist with valid fields, reason codes, and relationships."""
    cashier, manager = test_user
    sale, line, prod = test_sale

    ret_header = SalesReturn(
        return_number="RET-20260815-0001",
        sale_id=sale.id,
        cashier_id=cashier.id,
        approved_by_id=manager.id,
        return_date=date(2026, 8, 15),
        status=ReturnStatus.COMPLETED.value,
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
        reason_notes="Customer preferred blue color",
        refund_payment_method=RefundMethod.CASH.value,
        original_payment_method_snapshot="CASH",
        refund_reference="Cash drawer refund",
        subtotal_returned=Decimal("200.00"),
        discount_reversal=Decimal("20.00"),
        taxable_reversal=Decimal("180.00"),
        tax_reversal=Decimal("21.60"),
        total_refund_amount=Decimal("201.60"),
        cogs_reversal_total=Decimal("80.00"),
        writeoff_cost_total=Decimal("0.00"),
    )

    ret_item = SalesReturnItem(
        sale_line_item_id=line.id,
        product_id=prod.id,
        product_name=prod.name,
        quantity=2,
        unit_price_snapshot=Decimal("100.00"),
        unit_cost_snapshot=Decimal("40.00"),
        gross_amount_reversal=Decimal("200.00"),
        discount_reversal=Decimal("20.00"),
        taxable_reversal=Decimal("180.00"),
        tax_reversal=Decimal("21.60"),
        total_refund_amount=Decimal("201.60"),
        cogs_reversal=Decimal("80.00"),
        writeoff_cost=Decimal("0.00"),
        disposition=ReturnDisposition.RESTOCK.value,
    )
    ret_header.items.append(ret_item)

    db_session.add(ret_header)
    db_session.commit()

    # Query back
    saved_ret = db_session.query(SalesReturn).filter(SalesReturn.return_number == "RET-20260815-0001").first()
    assert saved_ret is not None
    assert saved_ret.cashier.username == "cashier_test"
    assert saved_ret.approved_by.username == "manager_test"
    assert saved_ret.sale.transaction_number == "TXN-20260815-9999"
    assert saved_ret.reason_code == "customer_change_mind"
    assert saved_ret.reason_notes == "Customer preferred blue color"
    assert len(saved_ret.items) == 1
    assert saved_ret.items[0].product_name == "Return Test Product"
    assert saved_ret.items[0].quantity == 2
    assert saved_ret.items[0].total_refund_amount == Decimal("201.60")

    # Parent sale relationship navigation
    assert len(sale.returns) == 1
    assert sale.returns[0].return_number == "RET-20260815-0001"
    # Original Sale status remains COMPLETED
    assert sale.status == "COMPLETED"


def test_sales_return_non_destructive_cascade_immutability(db_session, test_user, test_sale):
    """Removing a child from Python items list does not delete the child without explicit session action."""
    cashier, manager = test_user
    sale, line, prod = test_sale

    ret = SalesReturn(
        return_number="RET-NON-CASCADE-TEST",
        sale_id=sale.id,
        cashier_id=cashier.id,
        approved_by_id=manager.id,
        return_date=date(2026, 8, 15),
        status=ReturnStatus.COMPLETED.value,
        reason_code=ReturnReason.WRONG_ITEM.value,
        refund_payment_method=RefundMethod.CASH.value,
        original_payment_method_snapshot="CASH",
        total_refund_amount=Decimal("100.00"),
    )
    item = SalesReturnItem(
        sale_line_item_id=line.id,
        product_id=prod.id,
        product_name=prod.name,
        quantity=1,
        unit_price_snapshot=Decimal("100.00"),
        unit_cost_snapshot=Decimal("40.00"),
        total_refund_amount=Decimal("100.00"),
        disposition=ReturnDisposition.RESTOCK.value,
    )
    ret.items.append(item)
    db_session.add(ret)
    db_session.commit()

    ret_id = ret.id
    item_id = item.id

    # Verify no delete-orphan cascade config on relationship
    mapper = SalesReturn.__mapper__
    items_prop = mapper.relationships["items"]
    assert "delete-orphan" not in items_prop.cascade
    assert "delete" not in items_prop.cascade

    # Query item independently
    saved_item = db_session.query(SalesReturnItem).filter(SalesReturnItem.id == item_id).first()
    assert saved_item is not None
    assert saved_item.sales_return_id == ret_id


def test_sales_return_unique_number_constraint(db_session, test_user, test_sale):
    """return_number must be unique across all records."""
    cashier, manager = test_user
    sale, _, _ = test_sale

    ret1 = SalesReturn(
        return_number="RET-DUPLICATE-TEST",
        sale_id=sale.id,
        cashier_id=cashier.id,
        approved_by_id=manager.id,
        return_date=date(2026, 8, 15),
        status=ReturnStatus.COMPLETED.value,
        reason_code=ReturnReason.DEFECTIVE.value,
        refund_payment_method=RefundMethod.CASH.value,
        original_payment_method_snapshot="CASH",
        total_refund_amount=Decimal("100.00"),
    )
    db_session.add(ret1)
    db_session.commit()

    ret2 = SalesReturn(
        return_number="RET-DUPLICATE-TEST",
        sale_id=sale.id,
        cashier_id=cashier.id,
        approved_by_id=manager.id,
        return_date=date(2026, 8, 15),
        status=ReturnStatus.COMPLETED.value,
        reason_code=ReturnReason.EXPIRED.value,
        refund_payment_method=RefundMethod.CASH.value,
        original_payment_method_snapshot="CASH",
        total_refund_amount=Decimal("100.00"),
    )
    db_session.add(ret2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ── 3. Database Check Constraints ────────────────────────────────────

def test_sales_return_invalid_reason_code_constraint(db_session, test_user, test_sale):
    """Invalid reason_code value is rejected by check constraint."""
    cashier, manager = test_user
    sale, _, _ = test_sale

    invalid_ret = SalesReturn(
        return_number="RET-INVALID-REASON",
        sale_id=sale.id,
        cashier_id=cashier.id,
        approved_by_id=manager.id,
        return_date=date(2026, 8, 15),
        status=ReturnStatus.COMPLETED.value,
        reason_code="NONEXISTENT_REASON",
        refund_payment_method=RefundMethod.CASH.value,
        original_payment_method_snapshot="CASH",
        total_refund_amount=Decimal("100.00"),
    )
    db_session.add(invalid_ret)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_sales_return_negative_refund_check_constraint(db_session, test_user, test_sale):
    """Negative refund amounts are rejected by database check constraint."""
    cashier, manager = test_user
    sale, _, _ = test_sale

    invalid_ret = SalesReturn(
        return_number="RET-NEG-TEST",
        sale_id=sale.id,
        cashier_id=cashier.id,
        approved_by_id=manager.id,
        return_date=date(2026, 8, 15),
        status=ReturnStatus.COMPLETED.value,
        reason_code=ReturnReason.OTHER.value,
        refund_payment_method=RefundMethod.CASH.value,
        original_payment_method_snapshot="CASH",
        total_refund_amount=Decimal("-50.00"),
    )
    db_session.add(invalid_ret)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_sales_return_item_zero_quantity_check_constraint(db_session, test_user, test_sale):
    """Return item quantity <= 0 is rejected by check constraint."""
    cashier, manager = test_user
    sale, line, prod = test_sale

    ret = SalesReturn(
        return_number="RET-ZERO-QTY-TEST",
        sale_id=sale.id,
        cashier_id=cashier.id,
        approved_by_id=manager.id,
        return_date=date(2026, 8, 15),
        status=ReturnStatus.COMPLETED.value,
        reason_code=ReturnReason.OTHER.value,
        refund_payment_method=RefundMethod.CASH.value,
        original_payment_method_snapshot="CASH",
        total_refund_amount=Decimal("0.00"),
    )
    item = SalesReturnItem(
        sale_line_item_id=line.id,
        product_id=prod.id,
        product_name=prod.name,
        quantity=0,  # Invalid
        unit_price_snapshot=Decimal("100.00"),
        unit_cost_snapshot=Decimal("40.00"),
        disposition=ReturnDisposition.RESTOCK.value,
    )
    ret.items.append(item)
    db_session.add(ret)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_sales_return_item_invalid_disposition_constraint(db_session, test_user, test_sale):
    """Invalid disposition value is rejected by database check constraint."""
    cashier, manager = test_user
    sale, line, prod = test_sale

    ret = SalesReturn(
        return_number="RET-DISP-TEST",
        sale_id=sale.id,
        cashier_id=cashier.id,
        approved_by_id=manager.id,
        return_date=date(2026, 8, 15),
        status=ReturnStatus.COMPLETED.value,
        reason_code=ReturnReason.OTHER.value,
        refund_payment_method=RefundMethod.CASH.value,
        original_payment_method_snapshot="CASH",
        total_refund_amount=Decimal("100.00"),
    )
    item = SalesReturnItem(
        sale_line_item_id=line.id,
        product_id=prod.id,
        product_name=prod.name,
        quantity=1,
        unit_price_snapshot=Decimal("100.00"),
        unit_cost_snapshot=Decimal("40.00"),
        disposition="INVALID_DISPOSITION",
    )
    ret.items.append(item)
    db_session.add(ret)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ── 4. DTO Foundation Contracts ──────────────────────────────────────

def test_returns_dto_contracts_immutability():
    """Verify DTO schemas are strictly typed, immutable, and use Decimal for money."""
    req_item = ReturnItemRequestDTO(
        sale_line_item_id=1,
        quantity=2,
        disposition=ReturnDisposition.RESTOCK.value,
    )
    assert req_item.quantity == 2

    # Verify frozen
    with pytest.raises(Exception):
        req_item.quantity = 3

    dto = ProcessReturnRequestDTO(
        sale_id=10,
        items=[req_item],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
        reason_notes="Wrong size",
        refund_payment_method=RefundMethod.CASH.value,
    )
    assert dto.sale_id == 10
    assert dto.reason_code == "customer_change_mind"
    assert dto.reason_notes == "Wrong size"
    assert dto.refund_payment_method == "cash"

    summary_dto = SaleReturnSummaryDTO(
        sale_id=10,
        transaction_number="TXN-20260815-0001",
        total_original_quantity=5,
        total_returned_quantity=2,
        derived_state=DerivedReturnState.PARTIAL.value,
        total_refunded_amount=Decimal("201.60"),
        returns_count=1,
    )
    assert summary_dto.derived_state == "partial"
    assert summary_dto.total_refunded_amount == Decimal("201.60")


def test_verify_credentials_one_shot_override(db_session, test_user):
    """verify_credentials verifies password and permission without creating user_sessions or mutating last_login_at."""
    from application.services.auth_service import AuthenticationService
    from infrastructure.database.models.auth import Permission, Role, UserSession
    from infrastructure.security.hashing import hash_password
    from domain.exceptions import AuthenticationError, AuthorizationError, AccountInactiveError

    cashier, manager = test_user
    perm = Permission(code="refund_approve", name="Approve Returns", module="sales")
    db_session.add(perm)
    db_session.flush()

    mgr_role = Role(name="Manager", code="manager", permissions=[perm])
    db_session.add(mgr_role)
    manager.roles = [mgr_role]
    manager.password_hash = hash_password("ValidPassword123!")
    db_session.commit()

    auth_service = AuthenticationService(db_session)

    session_count_before = db_session.query(UserSession).count()
    last_login_before = manager.last_login_at

    # 1. Successful verification
    user = auth_service.verify_credentials("manager_test", "ValidPassword123!", required_permission="refund_approve")
    assert user.id == manager.id

    # No session created, last_login untouched
    assert db_session.query(UserSession).count() == session_count_before
    assert manager.last_login_at == last_login_before

    # 2. Invalid password
    with pytest.raises(AuthenticationError):
        auth_service.verify_credentials("manager_test", "WrongPassword123!", required_permission="refund_approve")

    # 3. Missing required permission
    cashier.password_hash = hash_password("CashierPassword123!")
    db_session.commit()
    with pytest.raises(AuthorizationError):
        auth_service.verify_credentials("cashier_test", "CashierPassword123!", required_permission="refund_approve")

    # 4. Inactive account
    manager.is_active = False
    db_session.commit()
    with pytest.raises(AccountInactiveError):
        auth_service.verify_credentials("manager_test", "ValidPassword123!", required_permission="refund_approve")

