"""
RetailFlow POS - MainWindow Expenses Integration & E2E Smoke Tests (Phase 6)
Tests MainWindow service injection, sidebar routing, permission enforcement,
and complete administrative lifecycle workflows.
"""

from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtCore import Qt

from app.constants import ExpenseCategory, ExpenseStatus
from application.dto.expense_dto import CreateExpenseDTO, UpdateExpenseMetadataDTO, VoidExpenseDTO
from application.services.expense_service import ExpenseService
from infrastructure.database.models.auth import AuditLog, Permission, Role, User
from infrastructure.database.seeders.auth_seeder import seed_auth
from infrastructure.database.seeders.expense_seeder import seed_expenses
from presentation.widgets.expenses_page import ExpensesPage
from presentation.windows.main_window import MainWindow


@pytest.fixture(autouse=True)
def setup_data(db_session):
    """Seed authentication and demo expenses."""
    seed_auth(db_session)
    seed_expenses(db_session)
    db_session.commit()


@pytest.fixture
def admin_user(db_session):
    return db_session.query(User).filter(User.username == "admin").first()


@pytest.fixture
def restricted_user(db_session):
    """User without view_expenses permission."""
    role = Role(name="Restricted Role", code="restricted_role", permissions=[])
    user = User(username="restricted_user", email="res@test.com", password_hash="h", full_name="Restricted User", roles=[role])
    db_session.add_all([role, user])
    db_session.commit()
    return user


def test_main_window_expenses_routing(qtbot, db_session, admin_user):
    window = MainWindow(current_user=admin_user, session=db_session)
    qtbot.addWidget(window)
    window.show()

    assert "expenses" in window.nav_buttons
    assert hasattr(window, "_expense_service")
    assert isinstance(window._expense_service, ExpenseService)

    # Navigate to expenses page
    window.navigate_to("expenses")

    current_page = window.stack.currentWidget()
    assert isinstance(current_page, ExpensesPage)
    assert window.page_title.text() == "Expenses"
    assert current_page.table.rowCount() == 10


def test_main_window_expenses_restricted_navigation(qtbot, db_session, restricted_user):
    window = MainWindow(current_user=restricted_user, session=db_session)
    qtbot.addWidget(window)
    window.show()

    # Nav item for expenses must be disabled
    expenses_nav = window.nav_buttons.get("expenses")
    assert expenses_nav is not None
    assert expenses_nav.is_disabled is True


def test_main_window_admin_e2e_workflow(qtbot, db_session, admin_user):
    window = MainWindow(current_user=admin_user, session=db_session)
    qtbot.addWidget(window)
    window.show()

    window.navigate_to("expenses")
    expenses_page: ExpensesPage = window.stack.currentWidget()

    # 1. Verify Initial Seed State (10 vouchers, 9 active, ₱68,235.63 total)
    assert expenses_page.table.rowCount() == 10
    assert expenses_page.card_total._value_label.text() == "₱68,235.63"
    assert expenses_page.card_vouchers._value_label.text() == "9"

    # 2. CREATE WORKFLOW: Record a new expense voucher
    create_dto = CreateExpenseDTO(
        category=ExpenseCategory.UTILITIES.value,
        title="Globe Business Internet Backup Line",
        payee="Globe Telecom",
        amount=Decimal("1899.00"),
        expense_date=date.today(),
        payment_method="bank_transfer",
        reference_number="GLB-REF-9901",
        notes="Primary backup line for POS connectivity",
    )
    new_exp = window._expense_service.create_expense(create_dto, actor=admin_user)
    assert new_exp.voucher_number.startswith("EXP-")
    assert new_exp.status == "paid"

    # Reload page
    expenses_page.load_expenses()
    assert expenses_page.table.rowCount() == 11
    assert expenses_page.card_total._value_label.text() == "₱70,134.63"
    assert expenses_page.card_vouchers._value_label.text() == "10"

    # Verify CREATE_EXPENSE audit entry
    log_create = (
        db_session.query(AuditLog)
        .filter(AuditLog.record_id == new_exp.id, AuditLog.action == "CREATE_EXPENSE")
        .first()
    )
    assert log_create is not None
    assert "₱1,899.00" in log_create.new_value

    # 3. EDIT WORKFLOW: Update metadata
    update_dto = UpdateExpenseMetadataDTO(
        payee="Globe Business Corporate",
        reference_number="GLB-REF-9901-FINAL",
        notes="Updated billing account number",
    )
    updated_exp = window._expense_service.update_expense_metadata(new_exp.id, update_dto, actor=admin_user)
    assert updated_exp.payee == "Globe Business Corporate"

    expenses_page.load_expenses()
    # Financial total remains unchanged
    assert expenses_page.card_total._value_label.text() == "₱70,134.63"

    # Verify UPDATE_EXPENSE audit entry
    log_update = (
        db_session.query(AuditLog)
        .filter(AuditLog.record_id == new_exp.id, AuditLog.action == "UPDATE_EXPENSE")
        .first()
    )
    assert log_update is not None

    # 4. VOID WORKFLOW: Permanently cancel the test voucher
    void_dto = VoidExpenseDTO(
        expense_id=new_exp.id,
        void_reason="Test voucher created during E2E verification",
    )
    voided_exp = window._expense_service.void_expense(void_dto, actor=admin_user)
    assert voided_exp.status == "void"

    expenses_page.load_expenses()
    # Table still has 11 rows (All Statuses shows both paid and void)
    assert expenses_page.table.rowCount() == 11
    # KPI totals deducted ₱1,899.00 and active vouchers decremented to 9
    assert expenses_page.card_total._value_label.text() == "₱68,235.63"
    assert expenses_page.card_vouchers._value_label.text() == "9"

    # Verify VOID_EXPENSE audit entry
    log_void = (
        db_session.query(AuditLog)
        .filter(AuditLog.record_id == new_exp.id, AuditLog.action == "VOID_EXPENSE")
        .first()
    )
    assert log_void is not None
    assert log_void.reason == "Test voucher created during E2E verification"


def test_main_window_roles_matrix(qtbot, db_session):
    """Verify Cashier, Manager, and Auditor permissions on MainWindow."""
    p_view = db_session.query(Permission).filter(Permission.code == "view_expenses").first()
    p_create = db_session.query(Permission).filter(Permission.code == "create_expenses").first()
    p_edit = db_session.query(Permission).filter(Permission.code == "edit_expenses").first()
    p_void = db_session.query(Permission).filter(Permission.code == "void_expenses").first()

    r_mgr = Role(name="Manager Role", code="r_mgr", permissions=[p_view, p_create, p_edit, p_void])
    r_csh = Role(name="Cashier Role", code="r_csh", permissions=[p_view, p_create])
    r_aud = Role(name="Auditor Role", code="r_aud", permissions=[p_view])

    u_mgr = User(username="u_mgr", email="mgr@test.com", password_hash="h", full_name="Store Manager", roles=[r_mgr])
    u_csh = User(username="u_csh", email="csh@test.com", password_hash="h", full_name="Store Cashier", roles=[r_csh])
    u_aud = User(username="u_aud", email="aud@test.com", password_hash="h", full_name="Store Auditor", roles=[r_aud])

    db_session.add_all([r_mgr, r_csh, r_aud, u_mgr, u_csh, u_aud])
    db_session.commit()

    # 1. Manager: Has full operating permissions
    win_mgr = MainWindow(current_user=u_mgr, session=db_session)
    qtbot.addWidget(win_mgr)
    win_mgr.navigate_to("expenses")
    page_mgr: ExpensesPage = win_mgr.stack.currentWidget()
    assert page_mgr.btn_new_expense.isEnabled() is True
    assert win_mgr.nav_buttons["expenses"].is_disabled is False

    # 2. Cashier: Can create expenses, but cannot edit or void existing
    win_csh = MainWindow(current_user=u_csh, session=db_session)
    qtbot.addWidget(win_csh)
    win_csh.navigate_to("expenses")
    page_csh: ExpensesPage = win_csh.stack.currentWidget()
    assert page_csh.btn_new_expense.isEnabled() is True
    assert win_csh.nav_buttons["expenses"].is_disabled is False

    # 3. Auditor: Read-only access (Record Expense disabled)
    win_aud = MainWindow(current_user=u_aud, session=db_session)
    qtbot.addWidget(win_aud)
    win_aud.navigate_to("expenses")
    page_aud: ExpensesPage = win_aud.stack.currentWidget()
    assert page_aud.btn_new_expense.isEnabled() is False
    assert win_aud.nav_buttons["expenses"].is_disabled is False

