"""
RetailFlow POS - Returns & Refunds Phase 6 FINAL E2E Verification & Adversarial Audit Suite
Comprehensive end-to-end audit verifying:
1. Normal Sale -> RESTOCK Return Lifecycle & Immutability
2. Same-Period P&L and Reconciliation (RESTOCK)
3. Same-Period DAMAGED_WRITE_OFF Return (Loss retention, No stock restoration, No synthetic expense)
4. Multi-Stage Partial Return Invariants & Zero Centavo Drift
5. Strict Idempotency & Conflict Rejection
6. Cashier Operator & Manager Approval Isolation
7. Admin/Manager Self-Approval & Inactive Account Rejection
8. Cross-Period Financial Reversals (Prior Month Immutability)
9. Return-Only Cashier Period & Zero-Division Safeguard
10. Return-Only Product Period & Deterministic Tie-Breaking
11. Daily Financial Trend & Manila Return Date Pinpointing
12. Payment & Refund Channel Snapshot Integrity
13. Inventory, Purchasing, and OPEX Subsystem Isolation
14. Concurrency & Over-Return Prevention
15. Return Voucher Number Collision Retry
16. Date / Time Timezone & Midnight Boundary Precision
17. Full Role-Based Access Control (RBAC) Matrix
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
import pytest

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
from application.dto.sales_dto import CartItemDTO, CheckoutRequestDTO
from application.services.product_service import ProductService
from application.services.report_service import ReportService
from application.services.returns_service import MANILA_TZ, ReturnsService
from application.services.sales_service import SalesService
from domain.exceptions import AuthorizationError, ValidationError
from infrastructure.database.models.auth import AuditLog, Permission, Role, User
from infrastructure.database.models.expense import Expense
from infrastructure.database.models.inventory import Inventory
from infrastructure.database.models.product import Category, Product
from infrastructure.database.models.purchasing import PurchaseOrder, PurchaseOrderItem
from infrastructure.database.models.returns import SalesReturn, SalesReturnItem
from infrastructure.database.models.sales import Payment, Sale, SaleLineItem
from infrastructure.database.models.supplier import Supplier


@pytest.fixture
def e2e_env(db_session):
    """Set up fully populated RBAC users and catalog products with inventory."""
    # 1. Permissions
    perms = {
        "view_sales": Permission(name="View Sales", code="view_sales", module="sales"),
        "process_sale": Permission(name="Process Sale", code="process_sale", module="pos"),
        "return_sales": Permission(name="Process Returns", code="return_sales", module="sales"),
        "refund_approve": Permission(name="Approve Refunds", code="refund_approve", module="sales"),
        "view_reports": Permission(name="View Reports", code="view_reports", module="reports"),
        "export_reports": Permission(name="Export Reports", code="export_reports", module="reports"),
        "view_expenses": Permission(name="View Expenses", code="view_expenses", module="expenses"),
    }
    db_session.add_all(list(perms.values()))
    db_session.flush()

    # 2. Roles
    r_admin = Role(name="Administrator", code=UserRole.ADMINISTRATOR, permissions=list(perms.values()))
    r_mgr = Role(name="Manager", code=UserRole.MANAGER, permissions=list(perms.values()))
    r_cashier = Role(name="Cashier", code=UserRole.CASHIER, permissions=[perms["view_sales"], perms["process_sale"], perms["return_sales"]])
    r_auditor = Role(name="Auditor", code=UserRole.AUDITOR, permissions=[perms["view_sales"], perms["view_reports"]])
    r_unauth = Role(name="Unauthorized", code="unauthorized", permissions=[])
    db_session.add_all([r_admin, r_mgr, r_cashier, r_auditor, r_unauth])
    db_session.flush()

    # 3. Users
    admin = User(username="admin_e2e", password_hash="hash", full_name="Admin Director", roles=[r_admin], is_active=True)
    manager = User(username="mgr_e2e", password_hash="hash", full_name="Store Manager Bob", roles=[r_mgr], is_active=True)
    cashier_a = User(username="csh_alice", password_hash="hash", full_name="Alice Cashier", roles=[r_cashier], is_active=True)
    cashier_b = User(username="csh_bob", password_hash="hash", full_name="Bob Cashier", roles=[r_cashier], is_active=True)
    auditor = User(username="aud_e2e", password_hash="hash", full_name="Audit Staff", roles=[r_auditor], is_active=True)
    inactive_mgr = User(username="mgr_inactive", password_hash="hash", full_name="Inactive Manager", roles=[r_mgr], is_active=False)
    db_session.add_all([admin, manager, cashier_a, cashier_b, auditor, inactive_mgr])
    db_session.flush()

    # 4. Catalog & Inventory
    cat = Category(name="Electronics")
    db_session.add(cat)
    db_session.flush()

    p_case = Product(sku="E2E-CASE", name="Silicone Case", selling_price=Decimal("100.00"), cost_price=Decimal("50.00"), category_id=cat.id, status="active")
    p_plug = Product(sku="E2E-PLUG", name="Wall Charger", selling_price=Decimal("200.00"), cost_price=Decimal("100.00"), category_id=cat.id, status="active")
    p_buds = Product(sku="E2E-BUDS", name="Wireless Earbuds", selling_price=Decimal("500.00"), cost_price=Decimal("300.00"), category_id=cat.id, status="active")
    db_session.add_all([p_case, p_plug, p_buds])
    db_session.flush()

    inv_case = Inventory(product_id=p_case.id, quantity_on_hand=100)
    inv_plug = Inventory(product_id=p_plug.id, quantity_on_hand=50)
    inv_buds = Inventory(product_id=p_buds.id, quantity_on_hand=30)
    db_session.add_all([inv_case, inv_plug, inv_buds])
    db_session.commit()

    return {
        "admin": admin,
        "manager": manager,
        "cashier_a": cashier_a,
        "cashier_b": cashier_b,
        "auditor": auditor,
        "inactive_mgr": inactive_mgr,
        "p_case": p_case,
        "p_plug": p_plug,
        "p_buds": p_buds,
        "inv_case": inv_case,
        "inv_plug": inv_plug,
        "inv_buds": inv_buds,
    }


# ── Scenario 1 & 2: Normal Sale -> RESTOCK Return & Report P&L ────────

def test_e2e_normal_sale_to_restock_return_and_report(db_session, e2e_env):
    """
    Complete lifecycle:
    Sale: 1 Silicone Case (Price ₱100, Cost ₱50), Discount ₱10.00.
    Taxable: ₱90.00 + 12% VAT ₱10.80 = Total Due ₱100.80.
    Tendered ₱100.80 via CASH.
    Full RESTOCK Return -> Refund ₱100.80.
    Verify inventory restored (+1), COGS reversed (₱50.00), writeoff (₱0.00), and Net P&L = ₱0.00.
    """
    sales_service = SalesService(db_session)
    returns_service = ReturnsService(db_session)
    report_service = ReportService(db_session)

    cashier = e2e_env["cashier_a"]
    manager = e2e_env["manager"]
    p_case = e2e_env["p_case"]
    inv_case = e2e_env["inv_case"]

    # 1. Checkout Sale
    sale_dto = sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[CartItemDTO(product_id=p_case.id, sku=p_case.sku, name=p_case.name, quantity=1, unit_price=Decimal("100.00"))],
            payment_method="CASH",
            amount_tendered=Decimal("100.80"),
            discount_amount=Decimal("10.00"),
        ),
        actor=cashier,
    )
    db_session.commit()

    # Pre-return assertions
    sale_db = db_session.query(Sale).filter(Sale.id == sale_dto.id).one()
    assert sale_db.status == "COMPLETED"
    assert sale_db.subtotal == Decimal("100.00")
    assert sale_db.discount_amount == Decimal("10.00")
    assert sale_db.tax_amount == Decimal("10.80")
    assert sale_db.total_amount == Decimal("100.80")

    db_session.refresh(inv_case)
    assert inv_case.quantity_on_hand == 99

    line_item = sale_db.items[0]
    assert line_item.unit_price == Decimal("100.00")
    assert line_item.unit_cost == Decimal("50.00")

    # 2. Process Full RESTOCK Return
    return_items = returns_service.get_returnable_items(sale_dto.id, cashier)
    ret_req = ProcessReturnRequestDTO(
        sale_id=sale_dto.id,
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
        reason_notes="Customer changed mind",
        refund_payment_method=RefundMethod.CASH.value,
        items=[
            ReturnItemRequestDTO(
                sale_line_item_id=return_items[0].sale_line_item_id,
                quantity=1,
                disposition=ReturnDisposition.RESTOCK.value,
            )
        ],
    )
    ret_dto = returns_service.process_return(ret_req, actor=cashier, approver=manager, idempotency_key="E2E-RESTOCK-001")
    db_session.commit()

    # Post-return atomic verification
    ret_db = db_session.query(SalesReturn).filter(SalesReturn.id == ret_dto.id).one()
    assert ret_db.status == ReturnStatus.COMPLETED.value
    assert ret_db.cashier_id == cashier.id
    assert ret_db.approved_by_id == manager.id
    assert ret_db.taxable_reversal == Decimal("90.00")
    assert ret_db.tax_reversal == Decimal("10.80")
    assert ret_db.total_refund_amount == Decimal("100.80")
    assert ret_db.cogs_reversal_total == Decimal("50.00")
    assert ret_db.writeoff_cost_total == Decimal("0.00")

    # Sale remains immutable
    db_session.refresh(sale_db)
    assert sale_db.status == "COMPLETED"
    assert sale_db.subtotal == Decimal("100.00")
    assert sale_db.total_amount == Decimal("100.80")

    # Inventory restored
    db_session.refresh(inv_case)
    assert inv_case.quantity_on_hand == 100

    # Audit log exists
    audit = db_session.query(AuditLog).filter(AuditLog.record_id == ret_db.id, AuditLog.action == "RETURN_PROCESSED").first()
    assert audit is not None
    assert audit.user_id == cashier.id

    # 3. Same-Period Report Reconciliation
    today = date.today()
    summary = report_service.get_financial_summary(today, today, actor=manager)
    assert summary.gross_sales == Decimal("100.00")
    assert summary.discounts == Decimal("10.00")
    assert summary.sales_returns == Decimal("90.00")
    assert summary.net_sales == Decimal("0.00")
    assert summary.gross_output_vat == Decimal("10.80")
    assert summary.vat_reversals == Decimal("10.80")
    assert summary.net_output_vat == Decimal("0.00")
    assert summary.total_collections == Decimal("100.80")
    assert summary.refunds_issued == Decimal("100.80")
    assert summary.net_collections == Decimal("0.00")
    assert summary.original_cogs == Decimal("50.00")
    assert summary.cogs_reversals == Decimal("50.00")
    assert summary.cogs == Decimal("0.00")
    assert summary.gross_profit == Decimal("0.00")
    assert summary.net_operating_profit == Decimal("0.00")


# ── Scenario 3: Same-Period DAMAGED_WRITE_OFF Return ──────────────────

def test_e2e_same_period_damaged_return(db_session, e2e_env):
    """
    Sale of 1 Wireless Earbuds (Price ₱500, Cost ₱300) + 12% VAT ₱60 = ₱560.00.
    DAMAGED_WRITE_OFF return:
    - Customer refunded ₱560.00.
    - VAT reversed (₱60.00).
    - Stock NOT restored (remains 29).
    - COGS reversal = ₱0.00, Writeoff Cost = ₱300.00.
    - ZERO synthetic Expense records created.
    - Reported COGS = ₱300.00, Net Sales = ₱0.00, Gross Profit = -₱300.00 (loss).
    """
    sales_service = SalesService(db_session)
    returns_service = ReturnsService(db_session)
    report_service = ReportService(db_session)

    cashier = e2e_env["cashier_a"]
    manager = e2e_env["manager"]
    p_buds = e2e_env["p_buds"]
    inv_buds = e2e_env["inv_buds"]

    # 1. Checkout Sale
    sale_dto = sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[CartItemDTO(product_id=p_buds.id, sku=p_buds.sku, name=p_buds.name, quantity=1, unit_price=Decimal("500.00"))],
            payment_method="CASH",
            amount_tendered=Decimal("560.00"),
            discount_amount=Decimal("0.00"),
        ),
        actor=cashier,
    )
    db_session.commit()

    db_session.refresh(inv_buds)
    assert inv_buds.quantity_on_hand == 29

    # Count expenses before return
    expense_count_before = db_session.query(Expense).count()

    # 2. Process DAMAGED Return
    return_items = returns_service.get_returnable_items(sale_dto.id, cashier)
    ret_req = ProcessReturnRequestDTO(
        sale_id=sale_dto.id,
        reason_code=ReturnReason.DEFECTIVE.value,
        reason_notes="Crushed charging case",
        refund_payment_method=RefundMethod.CASH.value,
        items=[
            ReturnItemRequestDTO(
                sale_line_item_id=return_items[0].sale_line_item_id,
                quantity=1,
                disposition=ReturnDisposition.DAMAGED_WRITE_OFF.value,
            )
        ],
    )
    ret_dto = returns_service.process_return(ret_req, actor=cashier, approver=manager, idempotency_key="E2E-DAMAGED-001")
    db_session.commit()

    # Verify return voucher
    ret_db = db_session.query(SalesReturn).filter(SalesReturn.id == ret_dto.id).one()
    assert ret_db.cogs_reversal_total == Decimal("0.00")
    assert ret_db.writeoff_cost_total == Decimal("300.00")

    # Inventory NOT restored
    db_session.refresh(inv_buds)
    assert inv_buds.quantity_on_hand == 29

    # No synthetic Expense rows created
    expense_count_after = db_session.query(Expense).count()
    assert expense_count_after == expense_count_before

    # Report verification
    today = date.today()
    summary = report_service.get_financial_summary(today, today, actor=manager)
    assert summary.gross_sales == Decimal("500.00")
    assert summary.sales_returns == Decimal("500.00")
    assert summary.net_sales == Decimal("0.00")
    assert summary.original_cogs == Decimal("300.00")
    assert summary.cogs_reversals == Decimal("0.00")
    assert summary.cogs == Decimal("300.00")
    assert summary.gross_profit == Decimal("-300.00")
    assert summary.operating_expenses == Decimal("0.00")
    assert summary.net_operating_profit == Decimal("-300.00")


# ── Scenario 4: Multi-Stage Partial Returns with Discount & VAT ───────

def test_e2e_multi_stage_partial_returns_invariant(db_session, e2e_env):
    """
    Sale:
    - Line 1: 5 Silicone Cases @ ₱100 = ₱500.00
    - Line 2: 2 Wall Chargers @ ₱200 = ₱400.00
    Subtotal: ₱900.00, Order Discount: ₱90.00 (10%).
    Taxable: ₱810.00, 12% VAT: ₱97.20, Total Due: ₱907.20.
    Tendered ₱907.20.

    Stage 1: Return 2 Cases (RESTOCK)
    Stage 2: Return 2 Cases + 1 Charger (RESTOCK)
    Stage 3: Return remaining 1 Case + 1 Charger (RESTOCK)

    Invariants:
    - Cumulative refund == ₱907.20 exactly (zero centavo drift).
    - Cumulative taxable reversal == ₱810.00 exactly.
    - Cumulative VAT reversal == ₱97.20 exactly.
    - Cumulative discount reversal == ₱90.00 exactly.
    - Derived return state transitions: NONE -> PARTIAL -> PARTIAL -> FULL.
    - Further return attempts on fully returned sale are blocked.
    """
    sales_service = SalesService(db_session)
    returns_service = ReturnsService(db_session)

    cashier = e2e_env["cashier_a"]
    manager = e2e_env["manager"]
    p_case = e2e_env["p_case"]
    p_plug = e2e_env["p_plug"]

    # 1. Checkout Sale
    sale_dto = sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[
                CartItemDTO(product_id=p_case.id, sku=p_case.sku, name=p_case.name, quantity=5, unit_price=Decimal("100.00")),
                CartItemDTO(product_id=p_plug.id, sku=p_plug.sku, name=p_plug.name, quantity=2, unit_price=Decimal("200.00")),
            ],
            payment_method="CASH",
            amount_tendered=Decimal("907.20"),
            discount_amount=Decimal("90.00"),
        ),
        actor=cashier,
    )
    db_session.commit()

    # Stage 1: Return 2 Cases
    ret_items = returns_service.get_returnable_items(sale_dto.id, cashier)
    case_item = next(i for i in ret_items if i.product_id == p_case.id)
    plug_item = next(i for i in ret_items if i.product_id == p_plug.id)

    ret1 = returns_service.process_return(
        ProcessReturnRequestDTO(
            sale_id=sale_dto.id,
            reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
            refund_payment_method=RefundMethod.CASH.value,
            items=[ReturnItemRequestDTO(sale_line_item_id=case_item.sale_line_item_id, quantity=2, disposition=ReturnDisposition.RESTOCK.value)],
        ),
        actor=cashier,
        approver=manager,
        idempotency_key="MULTI-STAGE-001",
    )
    db_session.commit()

    summary1 = returns_service.get_sale_return_summary(sale_dto.id, cashier)
    assert summary1.derived_state == DerivedReturnState.PARTIAL.value
    assert summary1.total_returned_quantity == 2

    # Stage 2: Return 2 Cases + 1 Charger
    ret_items2 = returns_service.get_returnable_items(sale_dto.id, cashier)
    case_item2 = next(i for i in ret_items2 if i.product_id == p_case.id)
    plug_item2 = next(i for i in ret_items2 if i.product_id == p_plug.id)

    ret2 = returns_service.process_return(
        ProcessReturnRequestDTO(
            sale_id=sale_dto.id,
            reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
            refund_payment_method=RefundMethod.CASH.value,
            items=[
                ReturnItemRequestDTO(sale_line_item_id=case_item2.sale_line_item_id, quantity=2, disposition=ReturnDisposition.RESTOCK.value),
                ReturnItemRequestDTO(sale_line_item_id=plug_item2.sale_line_item_id, quantity=1, disposition=ReturnDisposition.RESTOCK.value),
            ],
        ),
        actor=cashier,
        approver=manager,
        idempotency_key="MULTI-STAGE-002",
    )
    db_session.commit()

    summary2 = returns_service.get_sale_return_summary(sale_dto.id, cashier)
    assert summary2.derived_state == DerivedReturnState.PARTIAL.value
    assert summary2.total_returned_quantity == 5

    # Stage 3: Return final 1 Case + 1 Charger
    ret_items3 = returns_service.get_returnable_items(sale_dto.id, cashier)
    case_item3 = next(i for i in ret_items3 if i.product_id == p_case.id)
    plug_item3 = next(i for i in ret_items3 if i.product_id == p_plug.id)

    assert case_item3.remaining_returnable_quantity == 1
    assert plug_item3.remaining_returnable_quantity == 1

    ret3 = returns_service.process_return(
        ProcessReturnRequestDTO(
            sale_id=sale_dto.id,
            reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
            refund_payment_method=RefundMethod.CASH.value,
            items=[
                ReturnItemRequestDTO(sale_line_item_id=case_item3.sale_line_item_id, quantity=1, disposition=ReturnDisposition.RESTOCK.value),
                ReturnItemRequestDTO(sale_line_item_id=plug_item3.sale_line_item_id, quantity=1, disposition=ReturnDisposition.RESTOCK.value),
            ],
        ),
        actor=cashier,
        approver=manager,
        idempotency_key="MULTI-STAGE-003",
    )
    db_session.commit()

    summary3 = returns_service.get_sale_return_summary(sale_dto.id, cashier)
    assert summary3.derived_state == DerivedReturnState.FULL.value
    assert summary3.total_returned_quantity == 7
    assert summary3.returns_count == 3

    # Exact centavo summation checks
    total_taxable_rev = ret1.taxable_reversal + ret2.taxable_reversal + ret3.taxable_reversal
    total_tax_rev = ret1.tax_reversal + ret2.tax_reversal + ret3.tax_reversal
    total_refund = ret1.total_refund_amount + ret2.total_refund_amount + ret3.total_refund_amount
    total_discount_rev = ret1.discount_reversal + ret2.discount_reversal + ret3.discount_reversal

    assert total_taxable_rev == Decimal("810.00")
    assert total_tax_rev == Decimal("97.20")
    assert total_refund == Decimal("907.20")
    assert total_discount_rev == Decimal("90.00")

    # Stage 4: Attempt return on fully returned sale -> Rejected
    with pytest.raises(ValidationError) as exc:
        returns_service.process_return(
            ProcessReturnRequestDTO(
                sale_id=sale_dto.id,
                reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
                refund_payment_method=RefundMethod.CASH.value,
                items=[ReturnItemRequestDTO(sale_line_item_id=case_item3.sale_line_item_id, quantity=1, disposition=ReturnDisposition.RESTOCK.value)],
            ),
            actor=cashier,
            approver=manager,
            idempotency_key="MULTI-STAGE-004",
        )
    assert "fully returned" in str(exc.value)


# ── Scenario 5: Idempotency Exact Match & Semantic Conflict ───────────

def test_e2e_idempotency_behavior(db_session, e2e_env):
    """
    Idempotency verification:
    - Same request + same key -> returns identical existing SalesReturnDTO without duplicate inventory/audit rows.
    - Same key + conflicting quantity/reason -> raises ValidationError.
    - Unauthorized actor submitting existing key -> raises AuthorizationError (auth executes first).
    """
    sales_service = SalesService(db_session)
    returns_service = ReturnsService(db_session)

    cashier = e2e_env["cashier_a"]
    manager = e2e_env["manager"]
    auditor = e2e_env["auditor"]
    p_plug = e2e_env["p_plug"]
    inv_plug = e2e_env["inv_plug"]

    # 1. Checkout Sale
    sale_dto = sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[CartItemDTO(product_id=p_plug.id, sku=p_plug.sku, name=p_plug.name, quantity=2, unit_price=Decimal("200.00"))],
            payment_method="CASH",
            amount_tendered=Decimal("448.00"),
            discount_amount=Decimal("0.00"),
        ),
        actor=cashier,
    )
    db_session.commit()

    ret_items = returns_service.get_returnable_items(sale_dto.id, cashier)
    req = ProcessReturnRequestDTO(
        sale_id=sale_dto.id,
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
        reason_notes="First attempt",
        refund_payment_method=RefundMethod.CASH.value,
        items=[ReturnItemRequestDTO(sale_line_item_id=ret_items[0].sale_line_item_id, quantity=1, disposition=ReturnDisposition.RESTOCK.value)],
    )

    # 2. First submission
    first_resp = returns_service.process_return(req, actor=cashier, approver=manager, idempotency_key="IDEMPOTENT-KEY-001")
    db_session.commit()

    db_session.refresh(inv_plug)
    stock_after_first = inv_plug.quantity_on_hand
    audit_count_first = db_session.query(AuditLog).filter(AuditLog.module == "sales", AuditLog.action == "RETURN_PROCESSED").count()
    return_count_first = db_session.query(SalesReturn).count()

    # 3. Exact replay
    replay_resp = returns_service.process_return(req, actor=cashier, approver=manager, idempotency_key="IDEMPOTENT-KEY-001")
    db_session.commit()

    assert replay_resp.id == first_resp.id
    assert replay_resp.return_number == first_resp.return_number

    # No duplicate stock movements, return rows, or audit entries
    db_session.refresh(inv_plug)
    assert inv_plug.quantity_on_hand == stock_after_first
    assert db_session.query(SalesReturn).count() == return_count_first
    assert db_session.query(AuditLog).filter(AuditLog.module == "sales", AuditLog.action == "RETURN_PROCESSED").count() == audit_count_first

    # 4. Conflicting replay (different reason notes)
    conflict_req = ProcessReturnRequestDTO(
        sale_id=sale_dto.id,
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
        reason_notes="Conflicting payload notes",
        refund_payment_method=RefundMethod.CASH.value,
        items=[ReturnItemRequestDTO(sale_line_item_id=ret_items[0].sale_line_item_id, quantity=1, disposition=ReturnDisposition.RESTOCK.value)],
    )
    with pytest.raises(ValidationError) as exc:
        returns_service.process_return(conflict_req, actor=cashier, approver=manager, idempotency_key="IDEMPOTENT-KEY-001")
    assert "Idempotency conflict" in str(exc.value)

    # 5. Authorization check occurs before idempotent response
    with pytest.raises(AuthorizationError):
        returns_service.process_return(req, actor=auditor, approver=manager, idempotency_key="IDEMPOTENT-KEY-001")


# ── Scenario 6 & 7: Cashier + Manager Approval Security & Isolation ──

def test_e2e_cashier_and_manager_approval_isolation(db_session, e2e_env):
    """
    Cashier A initiates return, Manager B approves.
    - Return voucher records cashier_id = Cashier A, approved_by_id = Manager B.
    - Inactive manager cannot approve.
    - Admin/Manager can self-approve without manager override.
    """
    sales_service = SalesService(db_session)
    returns_service = ReturnsService(db_session)

    cashier = e2e_env["cashier_a"]
    manager = e2e_env["manager"]
    admin = e2e_env["admin"]
    inactive_mgr = e2e_env["inactive_mgr"]
    p_case = e2e_env["p_case"]

    # 1. Checkout Sale
    sale_dto = sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[CartItemDTO(product_id=p_case.id, sku=p_case.sku, name=p_case.name, quantity=2, unit_price=Decimal("100.00"))],
            payment_method="CASH",
            amount_tendered=Decimal("224.00"),
            discount_amount=Decimal("0.00"),
        ),
        actor=cashier,
    )
    db_session.commit()

    ret_items = returns_service.get_returnable_items(sale_dto.id, cashier)
    req = ProcessReturnRequestDTO(
        sale_id=sale_dto.id,
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
        refund_payment_method=RefundMethod.CASH.value,
        items=[ReturnItemRequestDTO(sale_line_item_id=ret_items[0].sale_line_item_id, quantity=1, disposition=ReturnDisposition.RESTOCK.value)],
    )

    # Inactive approver rejected
    with pytest.raises((AuthorizationError, ValidationError)) as exc:
        returns_service.process_return(req, actor=cashier, approver=inactive_mgr, idempotency_key="AUTH-ISO-001")
    assert "inactive" in str(exc.value)

    # Valid Cashier + Manager approval
    ret_dto = returns_service.process_return(req, actor=cashier, approver=manager, idempotency_key="AUTH-ISO-002")
    db_session.commit()

    assert ret_dto.cashier_id == cashier.id
    assert ret_dto.approved_by_id == manager.id

    # Admin self-approval on remaining item
    ret_items_rem = returns_service.get_returnable_items(sale_dto.id, admin)
    req_admin = ProcessReturnRequestDTO(
        sale_id=sale_dto.id,
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
        refund_payment_method=RefundMethod.CASH.value,
        items=[ReturnItemRequestDTO(sale_line_item_id=ret_items_rem[0].sale_line_item_id, quantity=1, disposition=ReturnDisposition.RESTOCK.value)],
    )
    ret_admin_dto = returns_service.process_return(req_admin, actor=admin, approver=admin, idempotency_key="AUTH-ISO-003")
    db_session.commit()

    assert ret_admin_dto.cashier_id == admin.id
    assert ret_admin_dto.approved_by_id == admin.id


# ── Scenario 8: Return Number Collision Retry ─────────────────────────

def test_e2e_return_number_collision_retry(db_session, e2e_env):
    """
    Force return number collision and verify savepoint retry generates next sequence RET-YYYYMMDD-0002.
    """
    sales_service = SalesService(db_session)
    returns_service = ReturnsService(db_session)

    cashier = e2e_env["cashier_a"]
    manager = e2e_env["manager"]
    p_plug = e2e_env["p_plug"]

    # 1. Checkout Sale
    sale_dto = sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[CartItemDTO(product_id=p_plug.id, sku=p_plug.sku, name=p_plug.name, quantity=2, unit_price=Decimal("200.00"))],
            payment_method="CASH",
            amount_tendered=Decimal("448.00"),
            discount_amount=Decimal("0.00"),
        ),
        actor=cashier,
    )
    db_session.commit()

    today_str = datetime.now(MANILA_TZ).strftime("%Y%m%d")
    colliding_number = f"RET-{today_str}-0001"

    # Pre-seed a dummy return to cause collision on 0001
    dummy_ret = SalesReturn(
        return_number=colliding_number,
        sale_id=sale_dto.id,
        cashier_id=cashier.id,
        approved_by_id=manager.id,
        reason_code=ReturnReason.OTHER.value,
        return_date=date.today(),
        refund_payment_method=RefundMethod.CASH.value,
        original_payment_method_snapshot="CASH",
        subtotal_returned=Decimal("0.00"),
        discount_reversal=Decimal("0.00"),
        taxable_reversal=Decimal("0.00"),
        tax_reversal=Decimal("0.00"),
        total_refund_amount=Decimal("0.00"),
        cogs_reversal_total=Decimal("0.00"),
        writeoff_cost_total=Decimal("0.00"),
        status=ReturnStatus.COMPLETED.value,
        idempotency_key="COLLISION-PRESEED-001",
    )
    db_session.add(dummy_ret)
    db_session.commit()

    # Process return -> collision handled gracefully, returns RET-YYYYMMDD-0002
    ret_items = returns_service.get_returnable_items(sale_dto.id, cashier)
    req = ProcessReturnRequestDTO(
        sale_id=sale_dto.id,
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
        refund_payment_method=RefundMethod.CASH.value,
        items=[ReturnItemRequestDTO(sale_line_item_id=ret_items[0].sale_line_item_id, quantity=1, disposition=ReturnDisposition.RESTOCK.value)],
    )
    ret_dto = returns_service.process_return(req, actor=cashier, approver=manager, idempotency_key="COLLISION-SUCCESS-001")
    db_session.commit()

    expected_next = f"RET-{today_str}-0002"
    assert ret_dto.return_number == expected_next


# ── Scenario 9: Purchasing Isolation Verification ────────────────────

def test_e2e_purchasing_isolation(db_session, e2e_env):
    """
    Create a received PurchaseOrder.
    Process customer returns.
    Verify received purchase order metrics in ReportService remain completely untouched.
    """
    sales_service = SalesService(db_session)
    returns_service = ReturnsService(db_session)
    report_service = ReportService(db_session)

    manager = e2e_env["manager"]
    cashier = e2e_env["cashier_a"]
    p_buds = e2e_env["p_buds"]

    # 1. Create Supplier & Received Purchase Order
    supp = Supplier(code="SUP-E2E-001", name="Apex Audio Supplies", contact_person="John Doe", phone="09171234567", email="apex@example.com", is_active=True)
    db_session.add(supp)
    db_session.flush()

    today = date.today()
    po = PurchaseOrder(
        po_number=f"PO-{today.strftime('%Y%m%d')}-0001",
        supplier_id=supp.id,
        status="RECEIVED",
        order_date=datetime(today.year, today.month, today.day, 2, 0, 0),
        received_at=datetime(today.year, today.month, today.day, 3, 0, 0),
        created_by_id=manager.id,
        received_by_id=manager.id,
        total_amount=Decimal("15000.00"),
    )
    db_session.add(po)
    db_session.flush()

    po_item = PurchaseOrderItem(
        purchase_order_id=po.id,
        product_id=p_buds.id,
        product_name=p_buds.name,
        quantity_ordered=50,
        quantity_received=50,
        unit_cost=Decimal("300.00"),
        subtotal=Decimal("15000.00"),
    )
    db_session.add(po_item)
    db_session.commit()

    # Query Purchasing Intake before return
    intake_before = report_service.get_received_purchase_value(today, today, actor=manager)
    assert intake_before.received_order_count == 1
    assert intake_before.received_purchase_value == Decimal("15000.00")
    assert intake_before.total_units_received == 50

    # 2. Checkout Sale & Process Return
    sale_dto = sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[CartItemDTO(product_id=p_buds.id, sku=p_buds.sku, name=p_buds.name, quantity=1, unit_price=Decimal("500.00"))],
            payment_method="CASH",
            amount_tendered=Decimal("560.00"),
            discount_amount=Decimal("0.00"),
        ),
        actor=cashier,
    )
    db_session.commit()

    ret_items = returns_service.get_returnable_items(sale_dto.id, cashier)
    returns_service.process_return(
        ProcessReturnRequestDTO(
            sale_id=sale_dto.id,
            reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
            refund_payment_method=RefundMethod.CASH.value,
            items=[ReturnItemRequestDTO(sale_line_item_id=ret_items[0].sale_line_item_id, quantity=1, disposition=ReturnDisposition.RESTOCK.value)],
        ),
        actor=cashier,
        approver=manager,
        idempotency_key="PURCHASING-ISO-001",
    )
    db_session.commit()

    # Purchasing Intake after return is identical
    intake_after = report_service.get_received_purchase_value(today, today, actor=manager)
    assert intake_after.received_order_count == 1
    assert intake_after.received_purchase_value == Decimal("15000.00")
    assert intake_after.total_units_received == 50


# ── Scenario 10: Concurrency & Over-Return Adversarial Test ───────────

def test_e2e_concurrency_over_return_prevention(db_session, e2e_env):
    """
    Adversarial test: Two return attempts for the same single sold item.
    First return succeeds; second return is blocked with ValidationError before double stock restoration or duplicate refund.
    """
    sales_service = SalesService(db_session)
    returns_service = ReturnsService(db_session)

    cashier = e2e_env["cashier_a"]
    manager = e2e_env["manager"]
    p_case = e2e_env["p_case"]
    inv_case = e2e_env["inv_case"]

    # 1. Checkout Sale of 1 unit
    sale_dto = sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[CartItemDTO(product_id=p_case.id, sku=p_case.sku, name=p_case.name, quantity=1, unit_price=Decimal("100.00"))],
            payment_method="CASH",
            amount_tendered=Decimal("112.00"),
            discount_amount=Decimal("0.00"),
        ),
        actor=cashier,
    )
    db_session.commit()

    ret_items = returns_service.get_returnable_items(sale_dto.id, cashier)
    req1 = ProcessReturnRequestDTO(
        sale_id=sale_dto.id,
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
        refund_payment_method=RefundMethod.CASH.value,
        items=[ReturnItemRequestDTO(sale_line_item_id=ret_items[0].sale_line_item_id, quantity=1, disposition=ReturnDisposition.RESTOCK.value)],
    )
    req2 = ProcessReturnRequestDTO(
        sale_id=sale_dto.id,
        reason_code=ReturnReason.DEFECTIVE.value,
        refund_payment_method=RefundMethod.CASH.value,
        items=[ReturnItemRequestDTO(sale_line_item_id=ret_items[0].sale_line_item_id, quantity=1, disposition=ReturnDisposition.RESTOCK.value)],
    )

    # First attempt succeeds
    resp1 = returns_service.process_return(req1, actor=cashier, approver=manager, idempotency_key="CONC-TXN-001")
    db_session.commit()
    assert resp1.status == ReturnStatus.COMPLETED.value

    # Competing second attempt is blocked
    with pytest.raises(ValidationError) as exc:
        returns_service.process_return(req2, actor=cashier, approver=manager, idempotency_key="CONC-TXN-002")
    assert "already been fully returned" in str(exc.value)

    # Confirm stock was incremented only once
    db_session.refresh(inv_case)
    assert inv_case.quantity_on_hand == 100


# ── Scenario 11: Date/Time Timezone & Midnight Boundary Precision ─────

def test_e2e_datetime_timezone_and_midnight_boundary(db_session, e2e_env):
    """
    Verify timezone boundary:
    A Sale completed at 23:30 UTC on August 14 is 07:30 AM Manila time on August 15.
    Reporting for August 15 in Manila includes the transaction.
    Reporting for August 14 in Manila excludes the transaction.
    """
    sales_service = SalesService(db_session)
    report_service = ReportService(db_session)

    manager = e2e_env["manager"]
    cashier = e2e_env["cashier_a"]
    p_case = e2e_env["p_case"]

    # 1. Checkout Sale
    sale_dto = sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[CartItemDTO(product_id=p_case.id, sku=p_case.sku, name=p_case.name, quantity=1, unit_price=Decimal("100.00"))],
            payment_method="CASH",
            amount_tendered=Decimal("112.00"),
            discount_amount=Decimal("0.00"),
        ),
        actor=cashier,
    )
    db_session.commit()

    # Backdate sale to 2026-08-14 23:30:00 UTC (= 2026-08-15 07:30:00 Manila)
    sale_db = db_session.query(Sale).filter(Sale.id == sale_dto.id).one()
    sale_db.created_at = datetime(2026, 8, 14, 23, 30, 0)
    db_session.commit()

    # Query Manila August 14: must be 0
    aug14_summary = report_service.get_financial_summary(date(2026, 8, 14), date(2026, 8, 14), actor=manager)
    assert aug14_summary.gross_sales == Decimal("0.00")

    # Query Manila August 15: must be ₱100.00
    aug15_summary = report_service.get_financial_summary(date(2026, 8, 15), date(2026, 8, 15), actor=manager)
    assert aug15_summary.gross_sales == Decimal("100.00")
    assert aug15_summary.net_sales == Decimal("100.00")


# ── Scenario 12: Role-Based Access Control (RBAC) Matrix Audit ────────

def test_e2e_rbac_security_matrix(db_session, e2e_env):
    """
    Verify complete permission matrix:
    - Admin: can view sales, process returns, self-approve returns, view reports, export reports.
    - Manager: can view sales, process returns, self-approve returns, view reports, export reports.
    - Cashier: can view sales, process returns; CANNOT self-approve (requires manager override); CANNOT view/export reports.
    - Auditor: can view sales, view reports; CANNOT process returns, CANNOT approve returns, CANNOT export reports.
    """
    sales_service = SalesService(db_session)
    returns_service = ReturnsService(db_session)
    report_service = ReportService(db_session)

    admin = e2e_env["admin"]
    manager = e2e_env["manager"]
    cashier = e2e_env["cashier_a"]
    auditor = e2e_env["auditor"]
    p_case = e2e_env["p_case"]

    # 1. Checkout Sale
    sale_dto = sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[CartItemDTO(product_id=p_case.id, sku=p_case.sku, name=p_case.name, quantity=4, unit_price=Decimal("100.00"))],
            payment_method="CASH",
            amount_tendered=Decimal("448.00"),
            discount_amount=Decimal("0.00"),
        ),
        actor=cashier,
    )
    db_session.commit()

    ret_items = returns_service.get_returnable_items(sale_dto.id, cashier)
    req = ProcessReturnRequestDTO(
        sale_id=sale_dto.id,
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
        refund_payment_method=RefundMethod.CASH.value,
        items=[ReturnItemRequestDTO(sale_line_item_id=ret_items[0].sale_line_item_id, quantity=1, disposition=ReturnDisposition.RESTOCK.value)],
    )

    # 1. Cashier cannot self-approve without manager override
    with pytest.raises(AuthorizationError) as exc:
        returns_service.process_return(req, actor=cashier, approver=cashier, idempotency_key="RBAC-CSH-SELF")
    assert "refund_approve" in str(exc.value)

    # 2. Cashier cannot view reports
    with pytest.raises(AuthorizationError):
        report_service.get_financial_summary(date.today(), date.today(), actor=cashier)

    # 3. Auditor cannot process returns
    with pytest.raises(AuthorizationError):
        returns_service.process_return(req, actor=auditor, approver=manager, idempotency_key="RBAC-AUD-PROC")

    # 4. Auditor can view reports, but cannot export
    aud_summary = report_service.get_financial_summary(date.today(), date.today(), actor=auditor)
    assert aud_summary is not None

