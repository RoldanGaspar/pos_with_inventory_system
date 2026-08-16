"""
RetailFlow POS - Expense Dialog UI Tests (Phase 4)
Tests modal UI behavior, validation feedback, financial field locking,
category change hints, void confirmations, and service integration.
"""

from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtCore import Qt

from app.constants import ExpenseCategory, ExpenseStatus
from application.dto.expense_dto import CreateExpenseDTO
from application.services.expense_service import ExpenseService
from infrastructure.database.models.auth import User
from infrastructure.database.seeders.auth_seeder import seed_auth
from presentation.dialogs.expense_dialog import ExpenseDialog
from presentation.dialogs.void_expense_dialog import VoidExpenseDialog


@pytest.fixture(autouse=True)
def setup_auth(db_session):
    """Seed authentication tables before running dialog UI tests."""
    seed_auth(db_session)
    db_session.commit()


@pytest.fixture
def admin_user(db_session):
    return db_session.query(User).filter(User.username == "admin").first()


# ─── 1. ExpenseDialog Create Mode Tests ───

def test_expense_dialog_create_mode_ui(qtbot, db_session, admin_user):
    service = ExpenseService(db_session)
    dialog = ExpenseDialog(expense_service=service, current_actor=admin_user)
    qtbot.addWidget(dialog)

    assert dialog.lbl_hdr_title.text() == "Record Operating Expense"
    assert dialog.cmb_category.count() == 8
    assert dialog.cmb_payment_method.count() >= 5
    assert dialog.dt_expense_date.date().toPython() == date.today()
    assert dialog.btn_save.isEnabled() is True

    # Check OTHER category hint
    idx_other = dialog.cmb_category.findData(ExpenseCategory.OTHER.value)
    dialog.cmb_category.setCurrentIndex(idx_other)
    assert "Required" in dialog.lbl_desc.text()


def test_expense_dialog_create_validation_feedback(qtbot, db_session, admin_user):
    service = ExpenseService(db_session)
    dialog = ExpenseDialog(expense_service=service, current_actor=admin_user)
    qtbot.addWidget(dialog)
    dialog.show()

    # 1. Attempt save with empty payee & title
    dialog._on_save_clicked()
    assert dialog.error_banner.isVisible() is True
    assert "Payee" in dialog.error_lbl.text()

    # 2. Enter payee, but leave title empty
    dialog.txt_payee.setText("Meralco")
    dialog._on_save_clicked()
    assert dialog.error_banner.isVisible() is True
    assert "title is required" in dialog.error_lbl.text().lower()

    # 3. Enter title, select OTHER category without description
    dialog.txt_title.setText("Misc Office Purchase")
    idx_other = dialog.cmb_category.findData(ExpenseCategory.OTHER.value)
    dialog.cmb_category.setCurrentIndex(idx_other)
    dialog._on_save_clicked()
    assert dialog.error_banner.isVisible() is True
    assert "Description is required" in dialog.error_lbl.text()


def test_expense_dialog_create_success(qtbot, db_session, admin_user):
    service = ExpenseService(db_session)
    dialog = ExpenseDialog(expense_service=service, current_actor=admin_user)
    qtbot.addWidget(dialog)

    dialog.txt_title.setText("Store Water Supply")
    dialog.txt_payee.setText("Maynilad")
    dialog.spn_amount.setValue(1850.50)
    dialog.txt_reference.setText("REF-MAY-001")
    dialog.txt_notes.setText("Petty cash voucher")

    idx_util = dialog.cmb_category.findData(ExpenseCategory.UTILITIES.value)
    dialog.cmb_category.setCurrentIndex(idx_util)

    # Click Save
    dialog._on_save_clicked()

    assert dialog.result_dto is not None
    assert dialog.result_dto.title == "Store Water Supply"
    assert dialog.result_dto.payee == "Maynilad"
    assert dialog.result_dto.amount == Decimal("1850.50")
    assert dialog.result_dto.voucher_number.startswith("EXP-")
    assert dialog.result_dto.status == "paid"


# ─── 2. ExpenseDialog Edit Metadata Mode Tests ───

def test_expense_dialog_edit_mode_financial_locking(qtbot, db_session, admin_user):
    service = ExpenseService(db_session)
    exp = service.create_expense(
        CreateExpenseDTO(
            category="rent",
            title="Monthly Warehouse Rent",
            payee="Old Landlord",
            amount=Decimal("25000.00"),
            expense_date=date.today(),
            reference_number="REF-001",
            notes="Initial note",
        ),
        actor=admin_user,
    )

    dialog = ExpenseDialog(expense_service=service, current_actor=admin_user, expense_data=exp)
    qtbot.addWidget(dialog)

    assert "Edit Voucher" in dialog.lbl_hdr_title.text()

    # Verify financial fields locked
    assert dialog.spn_amount.isEnabled() is False
    assert dialog.cmb_category.isEnabled() is False
    assert dialog.cmb_payment_method.isEnabled() is False
    assert dialog.dt_expense_date.isEnabled() is False
    assert dialog.txt_title.isEnabled() is False

    # Verify metadata fields enabled
    assert dialog.txt_payee.isEnabled() is True
    assert dialog.txt_reference.isEnabled() is True
    assert dialog.txt_notes.isEnabled() is True

    # Edit metadata
    dialog.txt_payee.setText("New Real Estate Corp")
    dialog.txt_notes.setText("Updated lease reference")
    dialog._on_save_clicked()

    assert dialog.result_dto is not None
    assert dialog.result_dto.payee == "New Real Estate Corp"
    assert dialog.result_dto.notes == "Updated lease reference"
    assert dialog.result_dto.amount == Decimal("25000.00")  # Strictly unchanged


# ─── 3. ExpenseDialog View Mode on VOID Voucher Tests ───

def test_expense_dialog_view_mode_on_void_record(qtbot, db_session, admin_user):
    service = ExpenseService(db_session)
    exp = service.create_expense(
        CreateExpenseDTO(category="supplies", title="Tape", payee="Vendor", amount=Decimal("300.00"), expense_date=date.today()),
        actor=admin_user,
    )
    from application.dto.expense_dto import VoidExpenseDTO
    voided_exp = service.void_expense(VoidExpenseDTO(expense_id=exp.id, void_reason="Cancelled purchase"), actor=admin_user)

    dialog = ExpenseDialog(expense_service=service, current_actor=admin_user, expense_data=voided_exp)
    qtbot.addWidget(dialog)

    assert dialog._view_only is True
    assert not hasattr(dialog, "btn_save")  # Save button not created in view mode
    assert dialog.btn_cancel.text() == "Close"
    assert dialog.txt_payee.isEnabled() is False
    assert dialog.txt_description.isReadOnly() is True


# ─── 4. VoidExpenseDialog Tests ───

def test_void_expense_dialog_ui_and_reason_validation(qtbot, db_session, admin_user):
    service = ExpenseService(db_session)
    exp = service.create_expense(
        CreateExpenseDTO(category="utilities", title="Electric Bill", payee="Meralco", amount=Decimal("4500.00"), expense_date=date.today()),
        actor=admin_user,
    )

    dialog = VoidExpenseDialog(expense_service=service, current_actor=admin_user, expense_data=exp)
    qtbot.addWidget(dialog)

    # Initial state: button disabled
    assert dialog.btn_confirm.isEnabled() is False
    assert "0 / 5" in dialog.lbl_char_count.text()

    # Enter 3 chars: still disabled
    dialog.txt_reason.setPlainText("bad")
    assert dialog.btn_confirm.isEnabled() is False
    assert "3 / 5" in dialog.lbl_char_count.text()

    # Enter 20 chars: button enabled
    dialog.txt_reason.setPlainText("Duplicate voucher recorded by error")
    assert dialog.btn_confirm.isEnabled() is True
    assert "characters" in dialog.lbl_char_count.text()

    # Click confirm
    dialog._on_confirm_clicked()

    assert dialog.result_dto is not None
    assert dialog.result_dto.status == "void"
    assert dialog.result_dto.void_reason == "Duplicate voucher recorded by error"
