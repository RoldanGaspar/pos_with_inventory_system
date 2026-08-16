"""
RetailFlow POS - Expense Service Integration & Hardening Tests (Phase 2 & 2.5)
Comprehensive test suite testing creation boundaries, voucher collisions & retry,
transaction atomicity & rollbacks, metadata immutability, void workflows,
P&L reporting boundaries, search/filter contracts, and role-permission matrices.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.constants import (
    ExpenseCategory,
    ExpenseSource,
    ExpenseStatus,
    PaymentMethod,
    UserRole,
)
from application.dto.expense_dto import (
    CreateExpenseDTO,
    ExpenseFilterDTO,
    UpdateExpenseMetadataDTO,
    VoidExpenseDTO,
)
from application.services.expense_service import ExpenseService
from domain.exceptions import AuthorizationError, RetailFlowError, ValidationError
from infrastructure.database.models.auth import AuditLog, Permission, Role, User
from infrastructure.database.models.expense import Expense


@pytest.fixture
def expense_users(db_session):
    """Seed test roles and users for permission matrix verification."""
    p_view = Permission(name="View Expenses", code="view_expenses", module="expenses")
    p_create = Permission(name="Create Expenses", code="create_expenses", module="expenses")
    p_edit = Permission(name="Edit Expenses", code="edit_expenses", module="expenses")
    p_void = Permission(name="Void Expenses", code="void_expenses", module="expenses")

    r_admin = Role(name="Administrator", code=UserRole.ADMINISTRATOR, permissions=[p_view, p_create, p_edit, p_void])
    r_mgr = Role(name="Manager", code=UserRole.MANAGER, permissions=[p_view, p_create, p_edit, p_void])
    r_cashier = Role(name="Cashier", code=UserRole.CASHIER, permissions=[p_view, p_create])
    r_auditor = Role(name="Auditor", code=UserRole.AUDITOR, permissions=[p_view])
    r_unauth = Role(name="Unauthorized", code="unauthorized", permissions=[])

    u_admin = User(username="admin_user", email="adm@test.com", password_hash="h", full_name="Admin", roles=[r_admin])
    u_mgr = User(username="mgr_user", email="mgr@test.com", password_hash="h", full_name="Manager", roles=[r_mgr])
    u_cashier = User(username="cashier_user", email="csh@test.com", password_hash="h", full_name="Cashier", roles=[r_cashier])
    u_auditor = User(username="auditor_user", email="aud@test.com", password_hash="h", full_name="Auditor", roles=[r_auditor])
    u_unauth = User(username="unauth_user", email="unauth@test.com", password_hash="h", full_name="Unauthorized", roles=[r_unauth])

    db_session.add_all([
        p_view, p_create, p_edit, p_void,
        r_admin, r_mgr, r_cashier, r_auditor, r_unauth,
        u_admin, u_mgr, u_cashier, u_auditor, u_unauth,
    ])
    db_session.commit()

    return {
        "admin": u_admin,
        "manager": u_mgr,
        "cashier": u_cashier,
        "auditor": u_auditor,
        "unauth": u_unauth,
    }


# ─── 1. Creation Boundary & Validation Tests ───

def test_create_expense_boundary_values(db_session, expense_users):
    service = ExpenseService(db_session)

    # 1. Minimum amount ₱0.01 accepted
    dto_min = CreateExpenseDTO(
        category="supplies",
        title="Rubber Band",
        payee="Stationery Store",
        amount=Decimal("0.01"),
        expense_date=date.today(),
    )
    resp_min = service.create_expense(dto_min, actor=expense_users["admin"])
    assert resp_min.amount == Decimal("0.01")

    # 2. Maximum amount ₱999,999,999.99 accepted
    dto_max = CreateExpenseDTO(
        category="rent",
        title="Property Acquisition",
        payee="Prime Estates",
        amount=Decimal("999999999.99"),
        expense_date=date.today(),
    )
    resp_max = service.create_expense(dto_max, actor=expense_users["admin"])
    assert resp_max.amount == Decimal("999999999.99")

    # 3. Amount above maximum rejected
    dto_over = CreateExpenseDTO(
        category="rent",
        title="Excessive Spend",
        payee="Vendor",
        amount=Decimal("1000000000.00"),
        expense_date=date.today(),
    )
    with pytest.raises(ValidationError, match="exceeds allowable maximum"):
        service.create_expense(dto_over, actor=expense_users["admin"])


def test_create_expense_invalid_inputs_rejected(db_session, expense_users):
    service = ExpenseService(db_session)

    # Empty / whitespace-only title
    with pytest.raises(ValidationError, match="Expense title is required"):
        service.create_expense(
            CreateExpenseDTO(category="utilities", title="   ", payee="Meralco", amount=Decimal("100"), expense_date=date.today()),
            actor=expense_users["admin"],
        )

    # Empty / whitespace-only payee
    with pytest.raises(ValidationError, match="Payee / Vendor name is required"):
        service.create_expense(
            CreateExpenseDTO(category="utilities", title="Power", payee="   ", amount=Decimal("100"), expense_date=date.today()),
            actor=expense_users["admin"],
        )

    # Invalid category
    with pytest.raises(ValidationError, match="Invalid expense category"):
        service.create_expense(
            CreateExpenseDTO(category="crypto_speculation", title="Power", payee="Meralco", amount=Decimal("100"), expense_date=date.today()),
            actor=expense_users["admin"],
        )

    # Invalid payment method
    with pytest.raises(ValidationError, match="Invalid payment method"):
        service.create_expense(
            CreateExpenseDTO(category="utilities", title="Power", payee="Meralco", amount=Decimal("100"), expense_date=date.today(), payment_method="BITCOIN"),
            actor=expense_users["admin"],
        )

    # Tomorrow rejected
    tomorrow = date.today() + timedelta(days=1)
    with pytest.raises(ValidationError, match="cannot be in the future"):
        service.create_expense(
            CreateExpenseDTO(category="utilities", title="Power", payee="Meralco", amount=Decimal("100"), expense_date=tomorrow),
            actor=expense_users["admin"],
        )

    # OTHER category without description rejected
    with pytest.raises(ValidationError, match="Description is required when category is 'other'"):
        service.create_expense(
            CreateExpenseDTO(category="other", title="Misc", payee="Store", amount=Decimal("100"), expense_date=date.today(), description="   "),
            actor=expense_users["admin"],
        )


# ─── 2. Voucher Collision & Concurrency Retry Tests ───

def test_voucher_collision_retry_and_recovery(db_session, expense_users):
    """
    Simulate a concurrent writer scenario where attempt #1 collides on an existing voucher number,
    rolls back cleanly, and attempt #2 successfully generates the next sequence.
    """
    service = ExpenseService(db_session)
    today_str = datetime.now().strftime("%Y%m%d")
    existing_v = f"EXP-{today_str}-0001"

    # Pre-insert existing_v
    exp1 = Expense(
        voucher_number=existing_v,
        category="utilities",
        title="Existing Voucher",
        payee="Vendor A",
        amount=Decimal("1000.00"),
        expense_date=date.today(),
        status="paid",
    )
    db_session.add(exp1)
    db_session.commit()

    # Mock _generate_voucher_number to simulate collision on 1st call, then return next on 2nd
    mock_gen = MagicMock(side_effect=[existing_v, f"EXP-{today_str}-0002"])
    service._generate_voucher_number = mock_gen

    dto = CreateExpenseDTO(
        category="supplies",
        title="Office Tape",
        payee="Stationery Inc",
        amount=Decimal("350.00"),
        expense_date=date.today(),
    )

    resp = service.create_expense(dto, actor=expense_users["admin"])

    assert resp.voucher_number == f"EXP-{today_str}-0002"
    assert mock_gen.call_count == 2

    # Verify database state & session usability
    all_expenses = db_session.query(Expense).all()
    assert len(all_expenses) == 2
    assert {e.voucher_number for e in all_expenses} == {existing_v, f"EXP-{today_str}-0002"}


# ─── 3. Atomic Transaction & Rollback Tests ───

def test_create_transaction_rollback_when_audit_fails(db_session, expense_users):
    service = ExpenseService(db_session)
    dto = CreateExpenseDTO(category="supplies", title="Plastic bags", payee="Bag vendor", amount=Decimal("800.00"), expense_date=date.today())

    service._audit_repo.log_action = MagicMock(side_effect=Exception("Database audit disk full error"))

    with pytest.raises(Exception, match="Database audit disk full error"):
        service.create_expense(dto, actor=expense_users["admin"])

    # Verify no expense was persisted
    assert db_session.query(Expense).filter(Expense.title == "Plastic bags").first() is None
    assert db_session.query(AuditLog).count() == 0


def test_update_transaction_rollback_when_audit_fails(db_session, expense_users):
    service = ExpenseService(db_session)
    dto = CreateExpenseDTO(category="rent", title="Store Rent", payee="Landlord Inc", amount=Decimal("12000.00"), expense_date=date.today())
    exp = service.create_expense(dto, actor=expense_users["admin"])

    # Simulate audit failure during update
    service._audit_repo.log_action = MagicMock(side_effect=Exception("Audit crash during update"))

    update_dto = UpdateExpenseMetadataDTO(payee="New Landlord LLC", notes="Updated payee details")
    with pytest.raises(Exception, match="Audit crash during update"):
        service.update_expense_metadata(exp.id, update_dto, actor=expense_users["admin"])

    # Verify metadata change was rolled back in DB
    refreshed = db_session.get(Expense, exp.id)
    assert refreshed.payee == "Landlord Inc"
    assert refreshed.notes is None


def test_void_transaction_rollback_when_audit_fails(db_session, expense_users):
    service = ExpenseService(db_session)
    dto = CreateExpenseDTO(category="utilities", title="Electric", payee="Meralco", amount=Decimal("4000.00"), expense_date=date.today())
    exp = service.create_expense(dto, actor=expense_users["manager"])

    # Simulate audit failure during void
    service._audit_repo.log_action = MagicMock(side_effect=Exception("Audit crash during void"))

    void_dto = VoidExpenseDTO(expense_id=exp.id, void_reason="Wrong meter reading billed")
    with pytest.raises(Exception, match="Audit crash during void"):
        service.void_expense(void_dto, actor=expense_users["manager"])

    # Verify status and void fields remain completely unset
    refreshed = db_session.get(Expense, exp.id)
    assert refreshed.status == "paid"
    assert refreshed.void_reason is None
    assert refreshed.voided_at is None
    assert refreshed.voided_by_id is None


# ─── 4. Metadata Update & Financial Immutability Tests ───

def test_update_metadata_no_op_does_not_audit(db_session, expense_users):
    service = ExpenseService(db_session)
    dto = CreateExpenseDTO(
        category="maintenance",
        title="Printer Repair",
        payee="Tech Services",
        amount=Decimal("1500.00"),
        expense_date=date.today(),
        description="Head replacement",
        reference_number="INV-101",
        notes="30-day warranty",
    )
    exp = service.create_expense(dto, actor=expense_users["manager"])
    audit_count_before = db_session.query(AuditLog).count()

    # Issue identical update (no-op)
    no_op_dto = UpdateExpenseMetadataDTO(
        payee="Tech Services",
        description="Head replacement",
        reference_number="INV-101",
        notes="30-day warranty",
    )
    resp = service.update_expense_metadata(exp.id, no_op_dto, actor=expense_users["manager"])
    assert resp.payee == "Tech Services"

    # Verify NO new audit log was written for no-op update
    audit_count_after = db_session.query(AuditLog).count()
    assert audit_count_after == audit_count_before


def test_update_metadata_cannot_modify_financial_fields(db_session, expense_users):
    service = ExpenseService(db_session)
    dto = CreateExpenseDTO(category="salaries", title="Staff Stipend", payee="John Doe", amount=Decimal("2500.00"), expense_date=date.today())
    exp = service.create_expense(dto, actor=expense_users["manager"])

    update_dto = UpdateExpenseMetadataDTO(payee="Johnathan Doe", description="Corrected legal name")
    updated = service.update_expense_metadata(exp.id, update_dto, actor=expense_users["manager"])

    assert updated.payee == "Johnathan Doe"
    assert updated.amount == Decimal("2500.00")
    assert updated.category == "salaries"
    assert updated.status == "paid"
    assert updated.voucher_number == exp.voucher_number


def test_update_metadata_on_void_record_rejected(db_session, expense_users):
    service = ExpenseService(db_session)
    exp = service.create_expense(CreateExpenseDTO(category="rent", title="Rent", payee="Landlord", amount=Decimal("5000"), expense_date=date.today()), actor=expense_users["admin"])
    service.void_expense(VoidExpenseDTO(expense_id=exp.id, void_reason="Payment cancelled"), actor=expense_users["admin"])

    with pytest.raises(ValidationError, match="Cannot edit a voided expense voucher"):
        service.update_expense_metadata(exp.id, UpdateExpenseMetadataDTO(payee="New Landlord"), actor=expense_users["admin"])


# ─── 5. Void Workflow Tests ───

def test_void_expense_validations(db_session, expense_users):
    service = ExpenseService(db_session)
    exp = service.create_expense(CreateExpenseDTO(category="utilities", title="Internet", payee="ISP", amount=Decimal("2000.00"), expense_date=date.today()), actor=expense_users["manager"])

    # Reason under 5 chars rejected
    with pytest.raises(ValidationError, match="minimum 5 characters"):
        service.void_expense(VoidExpenseDTO(expense_id=exp.id, void_reason="err"), actor=expense_users["manager"])

    # Valid void
    voided = service.void_expense(VoidExpenseDTO(expense_id=exp.id, void_reason="Billed on wrong corporate account"), actor=expense_users["manager"])
    assert voided.status == "void"
    assert voided.void_reason == "Billed on wrong corporate account"
    assert voided.voided_at is not None

    # Double void rejected
    with pytest.raises(ValidationError, match="already voided"):
        service.void_expense(VoidExpenseDTO(expense_id=exp.id, void_reason="Attempt second void"), actor=expense_users["manager"])


# ─── 6. get_expense() Tests ───

def test_get_expense_by_id(db_session, expense_users):
    service = ExpenseService(db_session)
    exp = service.create_expense(CreateExpenseDTO(category="marketing", title="Flyers", payee="Print Shop", amount=Decimal("1200.00"), expense_date=date.today()), actor=expense_users["admin"])

    # Retrieve active
    retrieved = service.get_expense(exp.id, actor=expense_users["auditor"])
    assert retrieved.id == exp.id
    assert retrieved.title == "Flyers"

    # Void and retrieve voided
    service.void_expense(VoidExpenseDTO(expense_id=exp.id, void_reason="Wrong print batch"), actor=expense_users["admin"])
    retrieved_void = service.get_expense(exp.id, actor=expense_users["auditor"])
    assert retrieved_void.status == "void"

    # Non-existent ID raises ValidationError
    with pytest.raises(ValidationError, match="not found"):
        service.get_expense(99999, actor=expense_users["admin"])

    # Unauthorized user raises AuthorizationError
    with pytest.raises(AuthorizationError):
        service.get_expense(exp.id, actor=expense_users["unauth"])


# ─── 7. Search & Multi-Filter Query Tests ───

def test_search_expenses_comprehensive_filtering(db_session, expense_users):
    service = ExpenseService(db_session)
    d_past = date.today() - timedelta(days=10)
    d_today = date.today()

    e1 = service.create_expense(CreateExpenseDTO(category="utilities", title="Meralco Power", payee="Meralco", amount=Decimal("5000.00"), expense_date=d_past, payment_method="CASH", reference_number="REF-POWER-01"), actor=expense_users["admin"])
    e2 = service.create_expense(CreateExpenseDTO(category="utilities", title="Maynilad Water", payee="Maynilad", amount=Decimal("1500.00"), expense_date=d_today, payment_method="GCASH", reference_number="REF-WATER-02"), actor=expense_users["admin"])
    e3 = service.create_expense(CreateExpenseDTO(category="rent", title="Store Rent", payee="Prime Landlord", amount=Decimal("20000.00"), expense_date=d_today, payment_method="BANK_TRANSFER", reference_number="CHECK-999"), actor=expense_users["admin"])
    e4 = service.create_expense(CreateExpenseDTO(category="supplies", title="Tape & Bags", payee="Metro Supplies", amount=Decimal("800.00"), expense_date=d_today, payment_method="CASH"), actor=expense_users["admin"])
    service.void_expense(VoidExpenseDTO(expense_id=e4.id, void_reason="Cancelled purchase order"), actor=expense_users["admin"])

    # 1. Keyword search matches title OR payee OR voucher OR reference
    res_kw = service.search_expenses(ExpenseFilterDTO(keyword="POWER"), actor=expense_users["admin"])
    assert res_kw.total == 1
    assert res_kw.items[0].id == e1.id

    res_ref = service.search_expenses(ExpenseFilterDTO(keyword="CHECK-999"), actor=expense_users["admin"])
    assert res_ref.total == 1
    assert res_ref.items[0].id == e3.id

    # 2. Category filter
    res_cat = service.search_expenses(ExpenseFilterDTO(category="utilities"), actor=expense_users["admin"])
    assert res_cat.total == 2
    assert {i.id for i in res_cat.items} == {e1.id, e2.id}

    # 3. Status filter
    res_void = service.search_expenses(ExpenseFilterDTO(status="void"), actor=expense_users["admin"])
    assert res_void.total == 1
    assert res_void.items[0].id == e4.id

    # 4. Date range filter
    res_date = service.search_expenses(ExpenseFilterDTO(start_date=d_today, end_date=d_today), actor=expense_users["admin"])
    assert res_date.total == 3  # e2, e3, e4

    # 5. Combined AND filters: Category UTILITIES AND Payment GCASH
    res_combined = service.search_expenses(ExpenseFilterDTO(category="utilities", payment_method="GCASH"), actor=expense_users["admin"])
    assert res_combined.total == 1
    assert res_combined.items[0].id == e2.id

    # 6. Pagination test
    res_p1 = service.search_expenses(ExpenseFilterDTO(page=1, page_size=2), actor=expense_users["admin"])
    assert res_p1.total == 4
    assert len(res_p1.items) == 2
    assert res_p1.has_next is True
    assert res_p1.has_previous is False

    res_p2 = service.search_expenses(ExpenseFilterDTO(page=2, page_size=2), actor=expense_users["admin"])
    assert len(res_p2.items) == 2
    assert res_p2.has_next is False
    assert res_p2.has_previous is True

    # 7. Empty result
    res_empty = service.search_expenses(ExpenseFilterDTO(keyword="NONEXISTENT_QUERY"), actor=expense_users["admin"])
    assert res_empty.total == 0
    assert len(res_empty.items) == 0


# ─── 8. Reporting Boundary Tests ───

def test_reporting_inclusive_date_boundaries(db_session, expense_users):
    service = ExpenseService(db_session)
    today = date.today()
    d_start = today - timedelta(days=10)
    d_mid = today - timedelta(days=5)
    d_end = today
    d_before = today - timedelta(days=11)
    # For testing boundary after, query a sub-window [d_start, d_mid] where d_end is outside (after)
    # Range tested: [d_start, d_mid]

    # Within range [d_start, d_mid]
    service.create_expense(CreateExpenseDTO(category="utilities", title="Start Day Bill", payee="V1", amount=Decimal("100.00"), expense_date=d_start), actor=expense_users["admin"])
    service.create_expense(CreateExpenseDTO(category="utilities", title="Mid Day Bill", payee="V2", amount=Decimal("200.00"), expense_date=d_mid), actor=expense_users["admin"])

    # Outside range [d_start, d_mid]
    service.create_expense(CreateExpenseDTO(category="utilities", title="Before Bill", payee="V3", amount=Decimal("1000.00"), expense_date=d_before), actor=expense_users["admin"])
    service.create_expense(CreateExpenseDTO(category="rent", title="After Range Bill", payee="V4", amount=Decimal("2000.00"), expense_date=d_end), actor=expense_users["admin"])

    # Inside range [d_start, d_mid] but VOIDED
    e_void = service.create_expense(CreateExpenseDTO(category="salaries", title="Voided Mid Bill", payee="V5", amount=Decimal("5000.00"), expense_date=d_mid), actor=expense_users["admin"])
    service.void_expense(VoidExpenseDTO(expense_id=e_void.id, void_reason="Cancelled payroll error"), actor=expense_users["admin"])

    # Query for [d_start, d_mid]
    total_opex = service.get_total_opex(d_start, d_mid)
    assert total_opex == Decimal("300.00")  # 100 + 200 (before 1000, after 2000, and voided 5000 excluded)

    breakdown = service.get_category_breakdown(d_start, d_mid)
    assert breakdown["utilities"] == Decimal("300.00")
    assert "rent" not in breakdown
    assert "salaries" not in breakdown


# ─── 9. Permission Matrix Enforcement Tests ───

def test_full_permission_matrix(db_session, expense_users):
    service = ExpenseService(db_session)
    dto = CreateExpenseDTO(category="supplies", title="Pens", payee="Stationery", amount=Decimal("150.00"), expense_date=date.today())

    # 1. Administrator: allowed for everything
    e_adm = service.create_expense(dto, actor=expense_users["admin"])
    assert service.get_expense(e_adm.id, actor=expense_users["admin"]).id == e_adm.id
    service.update_expense_metadata(e_adm.id, UpdateExpenseMetadataDTO(payee="Stationery Corp"), actor=expense_users["admin"])
    service.void_expense(VoidExpenseDTO(expense_id=e_adm.id, void_reason="Voided by admin"), actor=expense_users["admin"])

    # 2. Manager: allowed for create, edit, void, get, search
    e_mgr = service.create_expense(dto, actor=expense_users["manager"])
    assert service.get_expense(e_mgr.id, actor=expense_users["manager"]).id == e_mgr.id
    service.update_expense_metadata(e_mgr.id, UpdateExpenseMetadataDTO(payee="Stationery Hub"), actor=expense_users["manager"])
    service.void_expense(VoidExpenseDTO(expense_id=e_mgr.id, void_reason="Voided by manager"), actor=expense_users["manager"])

    # 3. Cashier: allowed for create, get, search; CANNOT edit or void
    e_csh = service.create_expense(dto, actor=expense_users["cashier"])
    assert service.get_expense(e_csh.id, actor=expense_users["cashier"]).id == e_csh.id
    with pytest.raises(AuthorizationError):
        service.update_expense_metadata(e_csh.id, UpdateExpenseMetadataDTO(payee="Cashier Edit Attempt"), actor=expense_users["cashier"])
    with pytest.raises(AuthorizationError):
        service.void_expense(VoidExpenseDTO(expense_id=e_csh.id, void_reason="Cashier Void Attempt"), actor=expense_users["cashier"])

    # 4. Auditor: allowed for get, search; CANNOT create, edit, or void
    assert service.get_expense(e_csh.id, actor=expense_users["auditor"]).id == e_csh.id
    with pytest.raises(AuthorizationError):
        service.create_expense(dto, actor=expense_users["auditor"])

    # 5. Unauthorized: CANNOT do any operation
    with pytest.raises(AuthorizationError):
        service.create_expense(dto, actor=expense_users["unauth"])
    with pytest.raises(AuthorizationError):
        service.get_expense(e_csh.id, actor=expense_users["unauth"])
    with pytest.raises(AuthorizationError):
        service.search_expenses(ExpenseFilterDTO(), actor=expense_users["unauth"])
    with pytest.raises(AuthorizationError):
        service.get_expense_metrics(actor=expense_users["unauth"])
