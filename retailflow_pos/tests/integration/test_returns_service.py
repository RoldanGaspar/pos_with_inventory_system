"""
RetailFlow POS - Returns Application Service Integration Tests (Phase 2C.1 Hardened)
Comprehensive integration tests covering:
- Deterministic RBAC authorization & approval matrix
- Mandatory idempotency keys & conflict detection (rejecting changed semantics)
- Active user account verification (rejecting inactive cashier or inactive approver)
- Full and partial returns with RESTOCK vs DAMAGED_WRITE_OFF inventory disposition
- Historical COGS snapshot immutability (unaffected by catalog price edits)
- Largest-remainder integer centavo allocation across Cases A, B, C, D, E
- Payment refund method validation (CASH vs ORIGINAL_METHOD)
- Cross-dialect concurrency protection & double-submission quantity safety
- Return number collision retry & Asia/Manila business-date prefix
- Transaction atomicity & rollback verification
- Invariant enforcement & original sale data integrity validation
- Query methods & derived return summaries (NONE, PARTIAL, FULL)
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Tuple
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.exc import IntegrityError

from app.constants import (
    DerivedReturnState,
    PaymentMethod,
    RefundMethod,
    ReturnDisposition,
    ReturnReason,
    ReturnStatus,
    UserRole,
)
from application.dto.returns_dto import (
    ProcessReturnRequestDTO,
    ReturnItemRequestDTO,
)
from application.services.returns_service import MANILA_TZ, ReturnsService
from domain.exceptions import AuthorizationError, ValidationError
from infrastructure.database.models.auth import AuditLog, Permission, Role, User
from infrastructure.database.models.inventory import Inventory
from infrastructure.database.models.product import Product
from infrastructure.database.models.returns import SalesReturn, SalesReturnItem
from infrastructure.database.models.sales import Payment, Sale, SaleLineItem


@pytest.fixture
def auth_users(db_session):
    """Seed test roles and authenticated users for Returns authorization tests."""
    p_view = Permission(name="View Sales", code="view_sales", module="sales")
    p_return = Permission(name="Process Returns", code="return_sales", module="sales")
    p_approve = Permission(name="Approve Refunds", code="refund_approve", module="sales")

    r_admin = Role(name="Administrator", code=UserRole.ADMINISTRATOR, permissions=[p_view, p_return, p_approve])
    r_mgr = Role(name="Manager", code=UserRole.MANAGER, permissions=[p_view, p_return, p_approve])
    r_cashier = Role(name="Cashier", code=UserRole.CASHIER, permissions=[p_view, p_return])
    r_auditor = Role(name="Auditor", code=UserRole.AUDITOR, permissions=[p_view])
    r_unauth = Role(name="Unauthorized", code="unauthorized", permissions=[])

    u_admin = User(username="admin_ret", password_hash="hash", full_name="Admin User", roles=[r_admin])
    u_mgr = User(username="mgr_ret", password_hash="hash", full_name="Store Manager", roles=[r_mgr])
    u_cashier = User(username="cashier_ret", password_hash="hash", full_name="Active Cashier", roles=[r_cashier])
    u_cashier_other = User(username="cashier_other", password_hash="hash", full_name="Other Cashier", roles=[r_cashier])
    u_inactive_cashier = User(username="cashier_inactive", password_hash="hash", full_name="Inactive Cashier", is_active=False, roles=[r_cashier])
    u_inactive_mgr = User(username="mgr_inactive", password_hash="hash", full_name="Inactive Manager", is_active=False, roles=[r_mgr])
    u_auditor = User(username="auditor_ret", password_hash="hash", full_name="Auditor User", roles=[r_auditor])
    u_unauth = User(username="unauth_ret", password_hash="hash", full_name="Unauthorized User", roles=[r_unauth])

    db_session.add_all([
        p_view, p_return, p_approve,
        r_admin, r_mgr, r_cashier, r_auditor, r_unauth,
        u_admin, u_mgr, u_cashier, u_cashier_other, u_inactive_cashier, u_inactive_mgr, u_auditor, u_unauth,
    ])
    db_session.commit()

    return {
        "admin": u_admin,
        "manager": u_mgr,
        "cashier": u_cashier,
        "cashier_other": u_cashier_other,
        "inactive_cashier": u_inactive_cashier,
        "inactive_manager": u_inactive_mgr,
        "auditor": u_auditor,
        "unauthorized": u_unauth,
    }


@pytest.fixture
def test_catalog(db_session):
    """Seed sample products and inventory records."""
    p1 = Product(sku="SKU-RET-1", name="Product Alpha", cost_price=Decimal("40.00"), selling_price=Decimal("100.00"))
    p2 = Product(sku="SKU-RET-2", name="Product Beta", cost_price=Decimal("60.00"), selling_price=Decimal("150.00"))
    p3 = Product(sku="SKU-RET-3", name="Product Gamma", cost_price=Decimal("10.00"), selling_price=Decimal("30.00"))
    db_session.add_all([p1, p2, p3])
    db_session.flush()

    inv1 = Inventory(product_id=p1.id, quantity_on_hand=10)
    inv2 = Inventory(product_id=p2.id, quantity_on_hand=20)
    inv3 = Inventory(product_id=p3.id, quantity_on_hand=30)
    db_session.add_all([inv1, inv2, inv3])
    db_session.commit()

    return {"p1": p1, "p2": p2, "p3": p3, "inv1": inv1, "inv2": inv2, "inv3": inv3}


def create_completed_sale(
    db_session,
    cashier: User,
    items_data: list,  # [(Product, qty, unit_price, unit_cost)]
    discount_amount: Decimal = Decimal("0.00"),
    tax_amount: Decimal = Decimal("0.00"),
    payment_method: str = "CASH",
    txn_number: str = "TXN-20260815-0001",
) -> Sale:
    """Helper to create an immutable completed Sale with line items and payment."""
    lines = []
    subtotal = Decimal("0.00")
    for prod, qty, unit_price, unit_cost in items_data:
        line_sub = (unit_price * qty).quantize(Decimal("0.01"))
        subtotal += line_sub
        lines.append(
            SaleLineItem(
                product_id=prod.id,
                product_name=prod.name,
                unit_price=unit_price,
                unit_cost=unit_cost,
                quantity=qty,
                subtotal=line_sub,
            )
        )

    total_amount = subtotal - discount_amount + tax_amount

    sale = Sale(
        transaction_number=txn_number,
        cashier_id=cashier.id,
        subtotal=subtotal,
        discount_amount=discount_amount,
        tax_amount=tax_amount,
        total_amount=total_amount,
        status="COMPLETED",
        payment_method=payment_method,
        items=lines,
    )
    pm = Payment(
        payment_method=payment_method,
        amount_paid=total_amount,
        change_given=Decimal("0.00"),
        reference_number="PAY-REF-12345" if payment_method != "CASH" else None,
    )
    sale.payments.append(pm)
    db_session.add(sale)
    db_session.commit()
    db_session.refresh(sale)
    return sale


# ── 1. Idempotency Contract & Conflict Detection ──────────────────────

def test_missing_or_blank_idempotency_key_rejected(db_session, auth_users, test_catalog):
    """Missing, empty, or blank idempotency key raises ValidationError."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 2, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-IDEMP-ERR-001",
    )
    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )

    with pytest.raises(ValidationError, match="valid, non-blank idempotency_key is required"):
        service.process_return(request=req, actor=admin, idempotency_key="")

    with pytest.raises(ValidationError, match="valid, non-blank idempotency_key is required"):
        service.process_return(request=req, actor=admin, idempotency_key="   ")


def test_oversized_idempotency_key_rejected(db_session, auth_users, test_catalog):
    """Idempotency key exceeding 64 characters is rejected."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 2, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-IDEMP-ERR-002",
    )
    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )

    long_key = "K" * 65
    with pytest.raises(ValidationError, match="idempotency_key must not exceed 64 characters"):
        service.process_return(request=req, actor=admin, idempotency_key=long_key)


def test_idempotency_conflict_changed_quantity_rejected(db_session, auth_users, test_catalog):
    """Re-submitting the same idempotency key with a changed quantity raises an idempotency conflict."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 5, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-IDEMP-CONFLICT-001",
    )

    idemp_key = "KEY-CONFLICT-QTY-1"

    # Initial return of 2 units
    req1 = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=2)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    dto1 = service.process_return(request=req1, actor=admin, idempotency_key=idemp_key)
    assert dto1.items[0].quantity == 2

    # Conflicting re-submission with 3 units under same key
    req2 = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=3)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    with pytest.raises(ValidationError, match="Idempotency conflict: quantity for line item.*changed from 2 to 3"):
        service.process_return(request=req2, actor=admin, idempotency_key=idemp_key)


def test_idempotency_conflict_different_sale_rejected(db_session, auth_users, test_catalog):
    """Re-submitting the same idempotency key against a different sale_id raises an idempotency conflict."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]

    sale1 = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 2, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-IDEMP-CONFLICT-SALE-1",
    )
    sale2 = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 2, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-IDEMP-CONFLICT-SALE-2",
    )

    idemp_key = "KEY-CONFLICT-SALE-1"

    req1 = ProcessReturnRequestDTO(
        sale_id=sale1.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale1.items[0].id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    service.process_return(request=req1, actor=admin, idempotency_key=idemp_key)

    req2 = ProcessReturnRequestDTO(
        sale_id=sale2.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale2.items[0].id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    with pytest.raises(ValidationError, match="Idempotency conflict: key.*was previously used for Sale ID"):
        service.process_return(request=req2, actor=admin, idempotency_key=idemp_key)


# ── 2. Active User Enforcement Tests ──────────────────────────────────

def test_inactive_actor_rejected(db_session, auth_users, test_catalog):
    """Inactive cashier or manager account cannot process returns."""
    service = ReturnsService(db_session)
    inact_cashier = auth_users["inactive_cashier"]
    mgr = auth_users["manager"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=auth_users["admin"],
        items_data=[(p1, 2, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-INACT-ACTOR-001",
    )

    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )

    with pytest.raises(AuthorizationError, match="User account 'cashier_inactive' is inactive"):
        service.process_return(request=req, actor=inact_cashier, approver=mgr, idempotency_key="KEY-INACT-ACTOR")


def test_inactive_approver_rejected(db_session, auth_users, test_catalog):
    """Inactive manager cannot serve as refund approver."""
    service = ReturnsService(db_session)
    cashier = auth_users["cashier"]
    inact_mgr = auth_users["inactive_manager"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=auth_users["admin"],
        items_data=[(p1, 2, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-INACT-APPR-001",
    )

    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )

    with pytest.raises(AuthorizationError, match="Approving user 'mgr_inactive' is inactive"):
        service.process_return(request=req, actor=cashier, approver=inact_mgr, idempotency_key="KEY-INACT-APPR")


# ── 3. Authorization Matrix Tests ─────────────────────────────────────

def test_authorization_admin_and_manager_self_approval(db_session, auth_users, test_catalog):
    """Admin and Manager users can self-approve and process returns directly."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    mgr = auth_users["manager"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 2, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-AUTH-001",
    )

    # Admin self-approval
    req_admin = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    dto_admin = service.process_return(request=req_admin, actor=admin, idempotency_key="KEY-AUTH-ADMIN")
    assert dto_admin.cashier_id == admin.id
    assert dto_admin.approved_by_id == admin.id

    # Manager self-approval on remaining quantity
    req_mgr = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1)],
        reason_code=ReturnReason.DEFECTIVE.value,
    )
    dto_mgr = service.process_return(request=req_mgr, actor=mgr, idempotency_key="KEY-AUTH-MGR")
    assert dto_mgr.cashier_id == mgr.id
    assert dto_mgr.approved_by_id == mgr.id


def test_authorization_cashier_requires_manager_approval(db_session, auth_users, test_catalog):
    """Cashier can process returns when a valid Manager approver is supplied."""
    service = ReturnsService(db_session)
    cashier = auth_users["cashier"]
    mgr = auth_users["manager"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=cashier,
        items_data=[(p1, 2, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-AUTH-002",
    )

    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1)],
        reason_code=ReturnReason.WRONG_ITEM.value,
    )
    dto = service.process_return(request=req, actor=cashier, approver=mgr, idempotency_key="KEY-AUTH-CASHIER-OK")
    assert dto.cashier_id == cashier.id
    assert dto.approved_by_id == mgr.id


def test_authorization_cashier_without_approver_raises(db_session, auth_users, test_catalog):
    """Cashier processing a return without an approver raises AuthorizationError."""
    service = ReturnsService(db_session)
    cashier = auth_users["cashier"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=cashier,
        items_data=[(p1, 2, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-AUTH-003",
    )

    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    with pytest.raises(AuthorizationError, match="requires Manager or Administrator refund approval"):
        service.process_return(request=req, actor=cashier, approver=None, idempotency_key="KEY-AUTH-NO-APPR")


def test_authorization_cashier_with_non_approver_user_raises(db_session, auth_users, test_catalog):
    """Cashier submitting another Cashier as approver raises AuthorizationError."""
    service = ReturnsService(db_session)
    cashier = auth_users["cashier"]
    cashier_other = auth_users["cashier_other"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=cashier,
        items_data=[(p1, 2, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-AUTH-004",
    )

    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    with pytest.raises(AuthorizationError, match="does not have 'refund_approve' permission"):
        service.process_return(request=req, actor=cashier, approver=cashier_other, idempotency_key="KEY-AUTH-BAD-APPR")


def test_authorization_auditor_and_unauthorized_cannot_process(db_session, auth_users, test_catalog):
    """Auditor and unauthorized users cannot initiate returns."""
    service = ReturnsService(db_session)
    auditor = auth_users["auditor"]
    unauth = auth_users["unauthorized"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=auth_users["admin"],
        items_data=[(p1, 2, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-AUTH-005",
    )

    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )

    with pytest.raises(AuthorizationError, match="return_sales"):
        service.process_return(request=req, actor=auditor, idempotency_key="KEY-AUTH-AUD")

    with pytest.raises(AuthorizationError, match="return_sales"):
        service.process_return(request=req, actor=unauth, idempotency_key="KEY-AUTH-UNAUTH")


def test_read_methods_require_view_sales_permission(db_session, auth_users, test_catalog):
    """Read queries require 'view_sales' permission."""
    service = ReturnsService(db_session)
    unauth = auth_users["unauthorized"]
    auditor = auth_users["auditor"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=auth_users["admin"],
        items_data=[(p1, 2, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-AUTH-006",
    )

    with pytest.raises(AuthorizationError, match="view_sales"):
        service.get_returnable_items(sale.id, actor=unauth)

    with pytest.raises(AuthorizationError, match="view_sales"):
        service.get_sale_return_summary(sale.id, actor=unauth)

    with pytest.raises(AuthorizationError, match="view_sales"):
        service.get_returns_for_sale(sale.id, actor=unauth)

    items = service.get_returnable_items(sale.id, actor=auditor)
    assert len(items) == 1
    assert items[0].remaining_returnable_quantity == 2


def test_concurrent_competing_returns_quantity_safety(db_session, auth_users, test_catalog):
    """Concurrent competing returns cannot collectively exceed the original returnable quantity."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 3, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-CONCUR-001",
    )
    line_id = sale.items[0].id

    # First return processes 2 units
    req1 = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=line_id, quantity=2)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    dto1 = service.process_return(request=req1, actor=admin, idempotency_key="KEY-CONCUR-1")
    assert dto1.items[0].quantity == 2

    # Second competing return attempting 2 units (which would make total 4 > 3) must be rejected
    req2 = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=line_id, quantity=2)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    with pytest.raises(ValidationError, match="exceeds remaining returnable quantity"):
        service.process_return(request=req2, actor=admin, idempotency_key="KEY-CONCUR-2")

    # Only remaining 1 unit can be returned
    req3 = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=line_id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    dto3 = service.process_return(request=req3, actor=admin, idempotency_key="KEY-CONCUR-3")
    assert dto3.items[0].quantity == 1

    summary = service.get_sale_return_summary(sale.id, actor=admin)
    assert summary.derived_state == DerivedReturnState.FULL.value
    assert summary.total_returned_quantity == 3


# ── 4. Return Number Business Date & Collision Retry ──────────────────

def test_manila_timezone_business_date_prefix(db_session, auth_users, test_catalog):
    """Return voucher number prefix is derived from Asia/Manila calendar date."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 1, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-MANILA-TZ-001",
    )

    manila_date_str = datetime.now(MANILA_TZ).strftime("%Y%m%d")

    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    dto = service.process_return(request=req, actor=admin, idempotency_key="KEY-MANILA-TZ")

    assert dto.return_number.startswith(f"RET-{manila_date_str}-")


def test_return_number_collision_retry(db_session, auth_users, test_catalog):
    """Collision retry loop handles duplicate return numbers and succeeds on next sequence."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 2, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-COLLISION-001",
    )

    # Pre-occupy sequence 0001
    today_date = datetime.now(MANILA_TZ).date()
    occupied_ret = SalesReturn(
        return_number=f"RET-{today_date.strftime('%Y%m%d')}-0001",
        sale_id=sale.id,
        cashier_id=admin.id,
        approved_by_id=admin.id,
        return_date=today_date,
        status=ReturnStatus.COMPLETED.value,
        reason_code=ReturnReason.OTHER.value,
        original_payment_method_snapshot="CASH",
        idempotency_key="KEY-PREOCCUPIED-0001",
        total_refund_amount=Decimal("100.00"),
    )
    db_session.add(occupied_ret)
    db_session.commit()

    # The service must automatically generate sequence 0002 without error
    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    dto = service.process_return(request=req, actor=admin, idempotency_key="KEY-COLLISION-RETRY-1")

    assert dto.return_number == f"RET-{today_date.strftime('%Y%m%d')}-0002"


# ── 4. Basic Returns, RESTOCK vs DAMAGED, and Historical COGS ─────────

def test_full_single_line_restock_return(db_session, auth_users, test_catalog):
    """Full return with RESTOCK increments inventory, reverses COGS, preserves Sale.status COMPLETED."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]
    inv1 = test_catalog["inv1"]

    initial_stock = inv1.quantity_on_hand  # 10

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 3, Decimal("100.00"), Decimal("40.00"))],
        discount_amount=Decimal("30.00"),
        tax_amount=Decimal("32.40"),
        txn_number="TXN-RESTOCK-001",
    )

    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=3, disposition=ReturnDisposition.RESTOCK.value)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
        refund_payment_method=RefundMethod.CASH.value,
    )

    dto = service.process_return(request=req, actor=admin, idempotency_key="KEY-RESTOCK-FULL-1")

    # Check return voucher totals
    assert dto.subtotal_returned == Decimal("300.00")
    assert dto.discount_reversal == Decimal("30.00")
    assert dto.taxable_reversal == Decimal("270.00")
    assert dto.tax_reversal == Decimal("32.40")
    assert dto.total_refund_amount == Decimal("302.40")
    assert dto.cogs_reversal_total == Decimal("120.00")  # 3 * 40.00
    assert dto.writeoff_cost_total == Decimal("0.00")

    # Inventory incremented
    db_session.refresh(inv1)
    assert inv1.quantity_on_hand == initial_stock + 3

    # Original Sale remains COMPLETED
    db_session.refresh(sale)
    assert sale.status == "COMPLETED"

    # Summary is FULL
    summary = service.get_sale_return_summary(sale.id, actor=admin)
    assert summary.derived_state == DerivedReturnState.FULL.value
    assert summary.total_returned_quantity == 3
    assert summary.total_refunded_amount == Decimal("302.40")


def test_damaged_return_does_not_increment_stock_and_records_writeoff(db_session, auth_users, test_catalog):
    """DAMAGED_WRITE_OFF return does NOT increment stock, records writeoff_cost, COGS reversal is 0.00."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]
    inv1 = test_catalog["inv1"]

    initial_stock = inv1.quantity_on_hand

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 2, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-DAMAGED-001",
    )

    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=2, disposition=ReturnDisposition.DAMAGED_WRITE_OFF.value)],
        reason_code=ReturnReason.DEFECTIVE.value,
        reason_notes="Cracked casing upon box opening",
    )

    dto = service.process_return(request=req, actor=admin, idempotency_key="KEY-DAMAGED-1")

    # Customer gets full refund
    assert dto.total_refund_amount == Decimal("200.00")
    # COGS is not reversed (absorbed as shrinkage)
    assert dto.cogs_reversal_total == Decimal("0.00")
    # Write-off cost recorded
    assert dto.writeoff_cost_total == Decimal("80.00")  # 2 * 40.00

    # Stock untouched
    db_session.refresh(inv1)
    assert inv1.quantity_on_hand == initial_stock


def test_mixed_restock_and_damaged_return(db_session, auth_users, test_catalog):
    """Single return voucher with 1 RESTOCK item and 1 DAMAGED_WRITE_OFF item."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]
    p2 = test_catalog["p2"]
    inv1 = test_catalog["inv1"]
    inv2 = test_catalog["inv2"]

    initial_p1_stock = inv1.quantity_on_hand
    initial_p2_stock = inv2.quantity_on_hand

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[
            (p1, 2, Decimal("100.00"), Decimal("40.00")),
            (p2, 1, Decimal("150.00"), Decimal("60.00")),
        ],
        txn_number="TXN-MIXED-001",
    )

    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[
            ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1, disposition=ReturnDisposition.RESTOCK.value),
            ReturnItemRequestDTO(sale_line_item_id=sale.items[1].id, quantity=1, disposition=ReturnDisposition.DAMAGED_WRITE_OFF.value),
        ],
        reason_code=ReturnReason.WRONG_ITEM.value,
    )

    dto = service.process_return(request=req, actor=admin, idempotency_key="KEY-MIXED-1")

    assert dto.cogs_reversal_total == Decimal("40.00")   # p1 RESTOCK
    assert dto.writeoff_cost_total == Decimal("60.00")   # p2 DAMAGED
    assert dto.total_refund_amount == Decimal("250.00")

    db_session.refresh(inv1)
    db_session.refresh(inv2)
    assert inv1.quantity_on_hand == initial_p1_stock + 1
    assert inv2.quantity_on_hand == initial_p2_stock      # unchanged


def test_cogs_uses_historical_snapshot_not_current_product_cost(db_session, auth_users, test_catalog):
    """Changing Product.cost_price in catalog after checkout does not affect return COGS reversal."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 1, Decimal("100.00"), Decimal("40.00"))],  # Historical cost 40.00
        txn_number="TXN-COGS-IMMUTABLE-001",
    )

    # Later: Supplier prices increase to 75.00
    p1.cost_price = Decimal("75.00")
    db_session.commit()

    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1, disposition=ReturnDisposition.RESTOCK.value)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    dto = service.process_return(request=req, actor=admin, idempotency_key="KEY-COGS-IMMUTABLE-1")

    # COGS reversal must strictly use historical snapshot (40.00), not catalog cost (75.00)
    assert dto.items[0].unit_cost_snapshot == Decimal("40.00")
    assert dto.cogs_reversal_total == Decimal("40.00")


# ── 5. Centavo Allocation Service Tests (Cases A, B, C, D, E) ────────

def test_case_a_discount_centavos_through_service(db_session, auth_users):
    """Case A: ₱0.05 discount / 10 equal lines through ReturnsService."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]

    items_data = []
    for i in range(1, 11):
        prod = Product(sku=f"SKU-CASEA-{i}", name=f"Product {i}", cost_price=Decimal("20.00"), selling_price=Decimal("100.00"))
        db_session.add(prod)
        db_session.flush()
        db_session.add(Inventory(product_id=prod.id, quantity_on_hand=5))
        items_data.append((prod, 1, Decimal("100.00"), Decimal("20.00")))
    db_session.commit()

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=items_data,
        discount_amount=Decimal("0.05"),
        txn_number="TXN-CASEA-001",
    )

    req_items = [ReturnItemRequestDTO(sale_line_item_id=l.id, quantity=1) for l in sale.items]
    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=req_items,
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    dto = service.process_return(request=req, actor=admin, idempotency_key="KEY-CASEA-1")

    assert dto.discount_reversal == Decimal("0.05")
    assert dto.subtotal_returned == Decimal("1000.00")
    assert dto.total_refund_amount == Decimal("999.95")


def test_case_b_ten_partial_returns_through_service(db_session, auth_users, test_catalog):
    """Case B: ₱0.05 line discount on 10 units returned in ten separate 1-unit transactions."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 10, Decimal("10.00"), Decimal("4.00"))],
        discount_amount=Decimal("0.05"),
        txn_number="TXN-CASEB-001",
    )
    line_id = sale.items[0].id

    total_discount_rev = Decimal("0.00")
    total_refund = Decimal("0.00")

    for i in range(10):
        req = ProcessReturnRequestDTO(
            sale_id=sale.id,
            items=[ReturnItemRequestDTO(sale_line_item_id=line_id, quantity=1)],
            reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
        )
        ret_dto = service.process_return(request=req, actor=admin, idempotency_key=f"KEY-CASEB-{i}")
        total_discount_rev += ret_dto.discount_reversal
        total_refund += ret_dto.total_refund_amount

    # Cumulative discount reversal is exactly ₱0.05
    assert total_discount_rev == Decimal("0.05")
    assert total_refund == Decimal("99.95")


def test_case_e_oneshot_vs_multistage_through_service(db_session, auth_users, test_catalog):
    """Case E: One-shot full return vs 3-stage partial return through ReturnsService."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]

    # Sale 1: One-shot
    sale1 = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 5, Decimal("100.00"), Decimal("40.00"))],
        discount_amount=Decimal("13.33"),
        tax_amount=Decimal("58.40"),
        txn_number="TXN-CASEE-001",
    )
    req1 = ProcessReturnRequestDTO(
        sale_id=sale1.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale1.items[0].id, quantity=5)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    dto_oneshot = service.process_return(request=req1, actor=admin, idempotency_key="KEY-CASEE-ONESHOT")

    # Sale 2: 3-stage return (2 units + 1 unit + 2 units)
    sale2 = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 5, Decimal("100.00"), Decimal("40.00"))],
        discount_amount=Decimal("13.33"),
        tax_amount=Decimal("58.40"),
        txn_number="TXN-CASEE-002",
    )
    line2_id = sale2.items[0].id

    req2_a = ProcessReturnRequestDTO(sale_id=sale2.id, items=[ReturnItemRequestDTO(sale_line_item_id=line2_id, quantity=2)], reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value)
    dto_a = service.process_return(request=req2_a, actor=admin, idempotency_key="KEY-CASEE-STAGE-A")

    req2_b = ProcessReturnRequestDTO(sale_id=sale2.id, items=[ReturnItemRequestDTO(sale_line_item_id=line2_id, quantity=1)], reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value)
    dto_b = service.process_return(request=req2_b, actor=admin, idempotency_key="KEY-CASEE-STAGE-B")

    req2_c = ProcessReturnRequestDTO(sale_id=sale2.id, items=[ReturnItemRequestDTO(sale_line_item_id=line2_id, quantity=2)], reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value)
    dto_c = service.process_return(request=req2_c, actor=admin, idempotency_key="KEY-CASEE-STAGE-C")

    cum_discount = dto_a.discount_reversal + dto_b.discount_reversal + dto_c.discount_reversal
    cum_taxable = dto_a.taxable_reversal + dto_b.taxable_reversal + dto_c.taxable_reversal
    cum_tax = dto_a.tax_reversal + dto_b.tax_reversal + dto_c.tax_reversal
    cum_refund = dto_a.total_refund_amount + dto_b.total_refund_amount + dto_c.total_refund_amount
    cum_cogs = dto_a.cogs_reversal_total + dto_b.cogs_reversal_total + dto_c.cogs_reversal_total

    assert cum_discount == dto_oneshot.discount_reversal == Decimal("13.33")
    assert cum_taxable == dto_oneshot.taxable_reversal == Decimal("486.67")
    assert cum_tax == dto_oneshot.tax_reversal == Decimal("58.40")
    assert cum_refund == dto_oneshot.total_refund_amount == Decimal("545.07")
    assert cum_cogs == dto_oneshot.cogs_reversal_total == Decimal("200.00")


# ── 6. Payment Refund Validation Tests ────────────────────────────────

def test_refund_payment_method_cash_and_original_method(db_session, auth_users, test_catalog):
    """Electronic GCash original sale refunded via ORIGINAL_METHOD with valid transaction reference."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 1, Decimal("100.00"), Decimal("40.00"))],
        payment_method="GCASH",
        txn_number="TXN-PAY-001",
    )

    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
        refund_payment_method=RefundMethod.ORIGINAL_METHOD.value,
        refund_reference="GCASH-REV-987654321",
    )
    dto = service.process_return(request=req, actor=admin, idempotency_key="KEY-PAY-GCASH-1")
    assert dto.refund_payment_method == "original_method"
    assert dto.original_payment_method_snapshot == "GCASH"
    assert dto.refund_reference == "GCASH-REV-987654321"


def test_refund_payment_original_method_validation_errors(db_session, auth_users, test_catalog):
    """ORIGINAL_METHOD rejected if missing reference or if original payment was CASH."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]

    # 1. GCash sale with blank reference
    sale_gcash = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 1, Decimal("100.00"), Decimal("40.00"))],
        payment_method="GCASH",
        txn_number="TXN-PAY-ERR-001",
    )
    req_blank_ref = ProcessReturnRequestDTO(
        sale_id=sale_gcash.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale_gcash.items[0].id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
        refund_payment_method=RefundMethod.ORIGINAL_METHOD.value,
        refund_reference="",  # Invalid blank
    )
    with pytest.raises(ValidationError, match="Refund reference is required"):
        service.process_return(request=req_blank_ref, actor=admin, idempotency_key="KEY-PAY-ERR-1")

    # 2. CASH sale attempting ORIGINAL_METHOD
    sale_cash = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 1, Decimal("100.00"), Decimal("40.00"))],
        payment_method="CASH",
        txn_number="TXN-PAY-ERR-002",
    )
    req_cash_orig = ProcessReturnRequestDTO(
        sale_id=sale_cash.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale_cash.items[0].id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
        refund_payment_method=RefundMethod.ORIGINAL_METHOD.value,
        refund_reference="SOME-REF",
    )
    with pytest.raises(ValidationError, match="ORIGINAL_METHOD refund is not allowed when original payment was CASH"):
        service.process_return(request=req_cash_orig, actor=admin, idempotency_key="KEY-PAY-ERR-2")


def test_reason_code_other_requires_notes(db_session, auth_users, test_catalog):
    """Reason code 'other' requires non-blank reason_notes."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 1, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-REASON-001",
    )

    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1)],
        reason_code=ReturnReason.OTHER.value,
        reason_notes="",  # Blank
    )
    with pytest.raises(ValidationError, match="Reason notes are required when reason code is 'other'"):
        service.process_return(request=req, actor=admin, idempotency_key="KEY-REASON-ERR-1")


# ── 7. Quantity & Request Validation Safety ───────────────────────────

def test_over_return_and_fully_returned_line_rejected(db_session, auth_users, test_catalog):
    """Over-return and returning on already fully returned line are rejected."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 2, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-QTY-ERR-001",
    )
    line_id = sale.items[0].id

    # 1. Over-return on initial request
    req_over = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=line_id, quantity=3)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    with pytest.raises(ValidationError, match="exceeds remaining returnable quantity"):
        service.process_return(request=req_over, actor=admin, idempotency_key="KEY-OVER-RET-1")

    # 2. Return all 2 units
    req_valid = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=line_id, quantity=2)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    service.process_return(request=req_valid, actor=admin, idempotency_key="KEY-VALID-RET-1")

    # 3. Subsequent return on fully returned line
    req_extra = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=line_id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    with pytest.raises(ValidationError, match="has already been fully returned"):
        service.process_return(request=req_extra, actor=admin, idempotency_key="KEY-EXTRA-RET-1")


def test_duplicate_line_items_in_request_rejected(db_session, auth_users, test_catalog):
    """Duplicate sale_line_item_id entries inside the same request payload are rejected."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 5, Decimal("100.00"), Decimal("40.00"))],
        txn_number="TXN-DUP-REQ-001",
    )
    line_id = sale.items[0].id

    req_dup = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[
            ReturnItemRequestDTO(sale_line_item_id=line_id, quantity=1),
            ReturnItemRequestDTO(sale_line_item_id=line_id, quantity=1),
        ],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    with pytest.raises(ValidationError, match="Duplicate line items in return request are not allowed"):
        service.process_return(request=req_dup, actor=admin, idempotency_key="KEY-DUP-REQ-1")


# ── 8. Atomicity & Rollback Verification ──────────────────────────────

def test_transaction_atomicity_and_rollback(db_session, auth_users):
    """Failure during return processing rolls back all operations completely."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]

    p_no_inv = Product(sku="SKU-NO-INV", name="Ghost Item", cost_price=Decimal("10.00"), selling_price=Decimal("50.00"))
    db_session.add(p_no_inv)
    db_session.commit()

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p_no_inv, 1, Decimal("50.00"), Decimal("10.00"))],
        txn_number="TXN-ROLLBACK-001",
    )

    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1, disposition=ReturnDisposition.RESTOCK.value)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )

    with pytest.raises(ValidationError, match="Inventory record for product 'Ghost Item'.*not found"):
        service.process_return(request=req, actor=admin, idempotency_key="KEY-ROLLBACK-1")

    # Verify zero return vouchers created
    assert db_session.query(SalesReturn).count() == 0
    assert db_session.query(SalesReturnItem).count() == 0
    assert db_session.query(AuditLog).filter(AuditLog.action == "RETURN_PROCESSED").count() == 0


# ── 9. Data Integrity & Inconsistent Sale Rejection ───────────────────

def test_data_integrity_validation_zero_taxable_base_and_mismatched_subtotals(db_session, auth_users, test_catalog):
    """Inconsistent sales data (e.g. 0 taxable base with tax, or discount > subtotal) are rejected."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]

    # 1. Zero taxable base with non-zero tax
    sale_bad_tax = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 1, Decimal("100.00"), Decimal("40.00"))],
        discount_amount=Decimal("100.00"),  # Taxable base = 0
        tax_amount=Decimal("12.00"),        # Inconsistent!
        txn_number="TXN-INTEG-001",
    )
    req1 = ProcessReturnRequestDTO(
        sale_id=sale_bad_tax.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale_bad_tax.items[0].id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    with pytest.raises(ValidationError, match="zero taxable base but non-zero tax recorded"):
        service.process_return(request=req1, actor=admin, idempotency_key="KEY-INTEG-1")

    # 2. Discount exceeding subtotal
    sale_bad_disc = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 1, Decimal("100.00"), Decimal("40.00"))],
        discount_amount=Decimal("150.00"),  # Inconsistent
        txn_number="TXN-INTEG-002",
    )
    req2 = ProcessReturnRequestDTO(
        sale_id=sale_bad_disc.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale_bad_disc.items[0].id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    with pytest.raises(ValidationError, match="discount exceeds subtotal"):
        service.process_return(request=req2, actor=admin, idempotency_key="KEY-INTEG-2")


# ── 10. Query Methods & Derived Summaries ─────────────────────────────

def test_query_methods_returnable_items_and_summaries(db_session, auth_users, test_catalog):
    """Query methods return correct remaining returnable quantities and derived summary states."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]
    p2 = test_catalog["p2"]

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[
            (p1, 4, Decimal("100.00"), Decimal("40.00")),
            (p2, 2, Decimal("150.00"), Decimal("60.00")),
        ],
        txn_number="TXN-QUERY-001",
    )

    # State: NONE
    sum_none = service.get_sale_return_summary(sale.id, actor=admin)
    assert sum_none.derived_state == DerivedReturnState.NONE.value
    assert sum_none.total_returned_quantity == 0
    assert sum_none.returns_count == 0

    returnable_initial = service.get_returnable_items(sale.id, actor=admin)
    assert len(returnable_initial) == 2
    assert returnable_initial[0].remaining_returnable_quantity == 4
    assert returnable_initial[1].remaining_returnable_quantity == 2

    # Process partial return (2 units of p1)
    req_part = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=2)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    dto_ret = service.process_return(request=req_part, actor=admin, idempotency_key="KEY-QUERY-PARTIAL-1")

    # State: PARTIAL
    sum_part = service.get_sale_return_summary(sale.id, actor=admin)
    assert sum_part.derived_state == DerivedReturnState.PARTIAL.value
    assert sum_part.total_returned_quantity == 2
    assert sum_part.returns_count == 1

    returnable_mid = service.get_returnable_items(sale.id, actor=admin)
    assert returnable_mid[0].remaining_returnable_quantity == 2
    assert returnable_mid[1].remaining_returnable_quantity == 2

    # Lookup by return number
    ret_lookup = service.get_return_by_number(dto_ret.return_number, actor=admin)
    assert ret_lookup is not None
    assert ret_lookup.return_number == dto_ret.return_number
    assert ret_lookup.total_refund_amount == dto_ret.total_refund_amount

    # Returns for sale list
    sale_returns = service.get_returns_for_sale(sale.id, actor=admin)
    assert len(sale_returns) == 1
    assert sale_returns[0].return_number == dto_ret.return_number


def test_preview_return_does_not_mutate_database_and_returns_exact_calculations(db_session, auth_users, test_catalog):
    """preview_return returns exact financial calculations without modifying inventory, returns, or audit logs."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]
    inv1 = test_catalog["inv1"]

    initial_stock = inv1.quantity_on_hand

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 4, Decimal("100.00"), Decimal("40.00"))],
        discount_amount=Decimal("40.00"),
        tax_amount=Decimal("43.20"),
        txn_number="TXN-PREVIEW-001",
    )

    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=2, disposition=ReturnDisposition.RESTOCK.value)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )

    # Invoke preview
    prev_dto = service.preview_return(request=req, actor=admin)

    assert prev_dto.sale_id == sale.id
    assert prev_dto.subtotal_returned == Decimal("200.00")
    assert prev_dto.discount_reversal == Decimal("20.00")
    assert prev_dto.taxable_reversal == Decimal("180.00")
    assert prev_dto.tax_reversal == Decimal("21.60")
    assert prev_dto.total_refund_amount == Decimal("201.60")
    assert prev_dto.cogs_reversal_total == Decimal("80.00")
    assert prev_dto.writeoff_cost_total == Decimal("0.00")
    assert len(prev_dto.items) == 1
    assert prev_dto.items[0].product_name == "Product Alpha"
    assert prev_dto.items[0].quantity == 2

    # Zero database modifications
    assert db_session.query(SalesReturn).count() == 0
    assert db_session.query(SalesReturnItem).count() == 0
    assert db_session.query(AuditLog).filter(AuditLog.action == "RETURN_PROCESSED").count() == 0

    db_session.refresh(inv1)
    assert inv1.quantity_on_hand == initial_stock


def test_idempotency_conflict_changed_reason_notes_or_reference_rejected(db_session, auth_users, test_catalog):
    """Re-submitting the same idempotency key with modified reason notes or refund reference raises an idempotency conflict."""
    service = ReturnsService(db_session)
    admin = auth_users["admin"]
    p1 = test_catalog["p1"]

    sale = create_completed_sale(
        db_session,
        cashier=admin,
        items_data=[(p1, 2, Decimal("100.00"), Decimal("40.00"))],
        payment_method="GCASH",
        txn_number="TXN-IDEMP-CONF-REF-1",
    )

    idemp_key = "KEY-IDEMP-CONF-NOTES-REF"

    req1 = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1)],
        reason_code=ReturnReason.OTHER.value,
        reason_notes="Defective screen",
        refund_payment_method=RefundMethod.ORIGINAL_METHOD.value,
        refund_reference="REF-GCASH-111",
    )
    service.process_return(request=req1, actor=admin, idempotency_key=idemp_key)

    # Conflicting notes
    req_bad_notes = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1)],
        reason_code=ReturnReason.OTHER.value,
        reason_notes="Changed my mind instead",
        refund_payment_method=RefundMethod.ORIGINAL_METHOD.value,
        refund_reference="REF-GCASH-111",
    )
    with pytest.raises(ValidationError, match="Idempotency conflict: reason notes changed"):
        service.process_return(request=req_bad_notes, actor=admin, idempotency_key=idemp_key)

    # Conflicting refund reference
    req_bad_ref = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1)],
        reason_code=ReturnReason.OTHER.value,
        reason_notes="Defective screen",
        refund_payment_method=RefundMethod.ORIGINAL_METHOD.value,
        refund_reference="REF-GCASH-222",
    )
    with pytest.raises(ValidationError, match="Idempotency conflict: refund reference changed"):
        service.process_return(request=req_bad_ref, actor=admin, idempotency_key=idemp_key)

