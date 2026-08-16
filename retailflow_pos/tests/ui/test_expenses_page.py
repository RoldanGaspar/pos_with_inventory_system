"""
RetailFlow POS - Expenses Workstation Page UI Tests (Phase 5)
Tests workstation page initialization, KPI card calculations, live search filtering,
category quick chips, status/payment dropdowns, pagination, and role-based action button permissions.
"""

from decimal import Decimal

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from app.constants import ExpenseCategory, ExpenseStatus, UserRole
from application.services.expense_service import ExpenseService
from infrastructure.database.models.auth import Permission, Role, User
from infrastructure.database.seeders.auth_seeder import seed_auth
from infrastructure.database.seeders.expense_seeder import seed_expenses
from presentation.widgets.expenses_page import ExpensesPage


@pytest.fixture(autouse=True)
def setup_auth_and_expenses(db_session):
    """Seed authentication tables and demo expenses before running workstation tests."""
    seed_auth(db_session)
    seed_expenses(db_session)
    db_session.commit()


@pytest.fixture
def users_map(db_session):
    """Fetch test users across roles."""
    p_view = db_session.query(Permission).filter(Permission.code == "view_expenses").first()
    p_create = db_session.query(Permission).filter(Permission.code == "create_expenses").first()
    p_edit = db_session.query(Permission).filter(Permission.code == "edit_expenses").first()
    p_void = db_session.query(Permission).filter(Permission.code == "void_expenses").first()

    r_cashier = Role(name="Test Cashier", code="test_cashier", permissions=[p_view, p_create])
    r_auditor = Role(name="Test Auditor", code="test_auditor", permissions=[p_view])

    u_admin = db_session.query(User).filter(User.username == "admin").first()
    u_manager = db_session.query(User).filter(User.username == "manager").first() or u_admin
    u_cashier = User(username="t_cashier", email="csh@test.com", password_hash="h", full_name="Cashier Staff", roles=[r_cashier])
    u_auditor = User(username="t_auditor", email="aud@test.com", password_hash="h", full_name="Auditor Staff", roles=[r_auditor])

    db_session.add_all([r_cashier, r_auditor, u_cashier, u_auditor])
    db_session.commit()

    return {
        "admin": u_admin,
        "manager": u_manager,
        "cashier": u_cashier,
        "auditor": u_auditor,
    }


# ─── 1. Instantiation & KPI Cards Tests ───

def test_expenses_page_instantiation_and_kpis(qtbot, db_session, users_map):
    service = ExpenseService(db_session)
    page = ExpensesPage(current_user=users_map["admin"], expense_service=service)
    qtbot.addWidget(page)
    page.show()

    # Verify KPI stat cards from seeded data
    assert page.card_total._value_label.text() == "₱68,235.63"
    assert page.card_vouchers._value_label.text() == "9"
    assert page.card_top_cat._value_label.text() == "Store & Warehouse Rent"
    assert "₱" in page.card_month._value_label.text()

    # Verify 10 seeded rows rendered in table
    assert page.table.rowCount() == 10
    assert page.btn_new_expense.isEnabled() is True


# ─── 2. Search Filtering Tests ───

def test_expenses_page_search_filtering(qtbot, db_session, users_map):
    service = ExpenseService(db_session)
    page = ExpensesPage(current_user=users_map["admin"], expense_service=service)
    qtbot.addWidget(page)
    page.show()

    # 1. Search by title keyword "Meralco"
    page.txt_search.setText("Meralco")
    page._perform_search()
    assert page.table.rowCount() == 1

    # 2. Search by reference number "OR-AYL"
    page.txt_search.setText("OR-AYL")
    page._perform_search()
    assert page.table.rowCount() == 1

    # 3. Search non-existent query -> empty state
    page.txt_search.setText("NON_EXISTENT_VOUCHER_123")
    page._perform_search()
    assert page.table.rowCount() == 0
    assert page.empty_frame.isVisible() is True
    assert page.empty_title.text() == "No Matching Expenses"

    # 4. Clear search
    page.txt_search.clear()
    page._perform_search()
    assert page.table.rowCount() == 10
    assert page.empty_frame.isVisible() is False


# ─── 3. Category Chip Filtering Tests ───

def test_expenses_page_category_chip_filtering(qtbot, db_session, users_map):
    service = ExpenseService(db_session)
    page = ExpensesPage(current_user=users_map["admin"], expense_service=service)
    qtbot.addWidget(page)
    page.show()

    # Click "Utilities" chip (3 vouchers)
    page._on_chip_clicked(ExpenseCategory.UTILITIES.value)
    assert page.table.rowCount() == 3

    # Click "Store Rent" chip (1 voucher)
    page._on_chip_clicked(ExpenseCategory.RENT.value)
    assert page.table.rowCount() == 1

    # Click "All Expenses" chip
    page._on_chip_clicked("all")
    assert page.table.rowCount() == 10


# ─── 4. Status & Payment Dropdown Filtering Tests ───

def test_expenses_page_status_and_payment_dropdowns(qtbot, db_session, users_map):
    service = ExpenseService(db_session)
    page = ExpensesPage(current_user=users_map["admin"], expense_service=service)
    qtbot.addWidget(page)
    page.show()

    # 1. Filter by PAID status
    idx_paid = page.cmb_status.findData(ExpenseStatus.PAID.value)
    page.cmb_status.setCurrentIndex(idx_paid)
    assert page.table.rowCount() == 9

    # 2. Filter by VOID status
    idx_void = page.cmb_status.findData(ExpenseStatus.VOID.value)
    page.cmb_status.setCurrentIndex(idx_void)
    assert page.table.rowCount() == 1

    # 3. Filter by Payment Method (BANK_TRANSFER has 3 vouchers: Meralco, PLDT, Rent)
    page.cmb_status.setCurrentIndex(0)  # All Statuses
    idx_bank = page.cmb_payment.findData("bank_transfer")
    page.cmb_payment.setCurrentIndex(idx_bank)
    assert page.table.rowCount() == 3

    # 4. Clear all filters button
    assert page.btn_clear_filters.isVisible() is True
    page._clear_filters()
    assert page.table.rowCount() == 10
    assert page.btn_clear_filters.isVisible() is False


# ─── 5. Role-Based Permissions & Action Buttons Tests ───

def test_expenses_page_permission_aware_actions(qtbot, db_session, users_map):
    service = ExpenseService(db_session)

    # 1. Admin/Manager: sees Edit and Void on PAID vouchers, View on VOID voucher
    page_admin = ExpensesPage(current_user=users_map["admin"], expense_service=service)
    qtbot.addWidget(page_admin)
    page_admin.show()

    # Find a PAID row action widget
    row_paid_actions = page_admin.table.cellWidget(0, 7)
    buttons_admin = row_paid_actions.findChildren(QPushButton)
    btn_texts_admin = [b.text() for b in buttons_admin]
    assert "Edit" in btn_texts_admin
    assert "Void" in btn_texts_admin

    # 2. Cashier: Record button enabled, but table rows only have View button
    page_cashier = ExpensesPage(current_user=users_map["cashier"], expense_service=service)
    qtbot.addWidget(page_cashier)
    page_cashier.show()

    assert page_cashier.btn_new_expense.isEnabled() is True
    row_csh_actions = page_cashier.table.cellWidget(0, 7)
    buttons_csh = row_csh_actions.findChildren(QPushButton)
    btn_texts_csh = [b.text() for b in buttons_csh]
    assert "View" in btn_texts_csh
    assert "Edit" not in btn_texts_csh
    assert "Void" not in btn_texts_csh

    # 3. Auditor: Record button disabled, table rows only have View button
    page_auditor = ExpensesPage(current_user=users_map["auditor"], expense_service=service)
    qtbot.addWidget(page_auditor)
    page_auditor.show()

    assert page_auditor.btn_new_expense.isEnabled() is False
    row_aud_actions = page_auditor.table.cellWidget(0, 7)
    buttons_aud = row_aud_actions.findChildren(QPushButton)
    btn_texts_aud = [b.text() for b in buttons_aud]
    assert "View" in btn_texts_aud


# ─── 6. Pagination UI Tests ───

def test_expenses_page_pagination(qtbot, db_session, users_map):
    service = ExpenseService(db_session)
    page = ExpensesPage(current_user=users_map["admin"], expense_service=service)
    page._page_size = 4  # 10 total -> 3 pages (4, 4, 2)
    qtbot.addWidget(page)
    page.show()
    page.load_expenses()

    assert page.table.rowCount() == 4
    assert page.btn_prev.isEnabled() is False
    assert page.btn_next.isEnabled() is True
    assert "Page 1 of 3" in page.lbl_page_number.text()

    # Go to Page 2
    page._next_page()
    assert page.table.rowCount() == 4
    assert page.btn_prev.isEnabled() is True
    assert page.btn_next.isEnabled() is True
    assert "Page 2 of 3" in page.lbl_page_number.text()

    # Go to Page 3
    page._next_page()
    assert page.table.rowCount() == 2
    assert page.btn_prev.isEnabled() is True
    assert page.btn_next.isEnabled() is False
    assert "Page 3 of 3" in page.lbl_page_number.text()

    # Go back to Page 2
    page._prev_page()
    assert page.table.rowCount() == 4
    assert "Page 2 of 3" in page.lbl_page_number.text()
