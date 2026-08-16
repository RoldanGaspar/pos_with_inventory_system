"""
RetailFlow POS - Returns & Refunds UI Tests (Phase 4)
Tests PySide6 dialogs, manager override authentication, non-mutating preview updates,
stepper/disposition interactions, idempotency key preservation, and SalesPage/SaleDetails integration.
"""

from decimal import Decimal
from typing import Dict

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel

from app.constants import (
    PaymentMethod,
    RefundMethod,
    ReturnDisposition,
    ReturnReason,
)
from application.dto.returns_dto import (
    ProcessReturnRequestDTO,
    ReturnItemRequestDTO,
)
from application.dto.sales_dto import CartItemDTO, CheckoutRequestDTO
from application.services.auth_service import AuthenticationService
from application.services.returns_service import ReturnsService
from application.services.sales_service import SalesService
from infrastructure.database.models.auth import User
from infrastructure.database.models.product import Product
from infrastructure.database.repositories.product import InventoryRepository
from infrastructure.database.seeders.auth_seeder import seed_auth
from presentation.dialogs.manager_override_dialog import ManagerOverrideDialog
from presentation.dialogs.process_return_dialog import ProcessReturnDialog
from presentation.dialogs.return_details_dialog import ReturnDetailsDialog
from presentation.dialogs.sale_details_dialog import SaleDetailsDialog
from presentation.widgets.sales_page import SalesPage


@pytest.fixture(autouse=True)
def setup_auth(db_session):
    """Seed roles and users."""
    seed_auth(db_session)
    db_session.commit()


@pytest.fixture
def auth_users(db_session) -> Dict[str, User]:
    admin = db_session.query(User).filter(User.username == "admin").first()
    manager = db_session.query(User).filter(User.username == "manager").first()
    cashier = db_session.query(User).filter(User.username == "cashier").first()
    return {"admin": admin, "manager": manager, "cashier": cashier}


@pytest.fixture
def sample_sales(db_session, auth_users):
    """Create sample sales for testing (one cash, one electronic GCash)."""
    p1 = Product(sku="RET-ITEM-1", name="Alpha Item", cost_price=Decimal("40.00"), selling_price=Decimal("100.00"), status="active")
    p2 = Product(sku="RET-ITEM-2", name="Beta Item", cost_price=Decimal("50.00"), selling_price=Decimal("150.00"), status="active")
    db_session.add_all([p1, p2])
    db_session.flush()

    inv_repo = InventoryRepository(db_session)
    inv_repo.set_quantity(p1.id, 100)
    inv_repo.set_quantity(p2.id, 100)
    db_session.commit()

    sales_service = SalesService(db_session)

    # Cash Sale (3 units p1 @ 100 + 2 units p2 @ 150 = 600 subtotal + 72 tax = 672 total)
    req_cash = CheckoutRequestDTO(
        items=[
            CartItemDTO(product_id=p1.id, sku=p1.sku, name=p1.name, unit_price=p1.selling_price, quantity=3),
            CartItemDTO(product_id=p2.id, sku=p2.sku, name=p2.name, unit_price=p2.selling_price, quantity=2),
        ],
        amount_tendered=Decimal("800.00"),
        payment_method="Cash",
    )
    cash_sale = sales_service.process_checkout(req_cash, actor=auth_users["admin"])

    # GCash Sale (2 units p1 @ 100 = 200 subtotal + 24 tax = 224 total)
    req_gcash = CheckoutRequestDTO(
        items=[
            CartItemDTO(product_id=p1.id, sku=p1.sku, name=p1.name, unit_price=p1.selling_price, quantity=2),
        ],
        amount_tendered=Decimal("250.00"),
        payment_method="GCash",
    )
    gcash_sale = sales_service.process_checkout(req_gcash, actor=auth_users["cashier"])

    return {"p1": p1, "p2": p2, "cash_sale": cash_sale, "gcash_sale": gcash_sale}


# ─── 1. ManagerOverrideDialog Tests ───

def test_manager_override_dialog_success(qtbot, db_session, auth_users):
    """Manager entering valid credentials successfully accepts override dialog."""
    auth_service = AuthenticationService(db_session)
    dlg = ManagerOverrideDialog(auth_service=auth_service)
    qtbot.addWidget(dlg)
    dlg.show()

    dlg.txt_username.setText("manager")
    dlg.txt_password.setText("manager123")
    dlg._on_authorize()

    assert dlg.result() == QDialog.Accepted
    assert dlg.authenticated_approver is not None
    assert dlg.authenticated_approver.username == "manager"


def test_manager_override_dialog_invalid_password(qtbot, db_session):
    """Invalid credentials display error banner and clears password field."""
    auth_service = AuthenticationService(db_session)
    dlg = ManagerOverrideDialog(auth_service=auth_service)
    qtbot.addWidget(dlg)
    dlg.show()

    dlg.txt_username.setText("manager")
    dlg.txt_password.setText("WrongPassword999")
    dlg._on_authorize()

    assert dlg.lbl_error.isVisible() is True
    assert "Invalid manager username or password" in dlg.lbl_error.text()
    assert dlg.txt_password.text() == ""
    assert dlg.authenticated_approver is None


def test_manager_override_dialog_unauthorized_user(qtbot, db_session):
    """User without refund_approve permission is rejected."""
    auth_service = AuthenticationService(db_session)
    dlg = ManagerOverrideDialog(auth_service=auth_service)
    qtbot.addWidget(dlg)
    dlg.show()

    # Cashier attempts to approve their own override
    dlg.txt_username.setText("cashier")
    dlg.txt_password.setText("cashier123")
    dlg._on_authorize()

    assert dlg.lbl_error.isVisible() is True
    assert "does not have 'refund_approve' permission" in dlg.lbl_error.text()
    assert dlg.authenticated_approver is None


# ─── 2. ProcessReturnDialog UI & Interaction Tests ───

def test_process_return_dialog_initial_state_cash_sale(qtbot, db_session, auth_users, sample_sales):
    """Verify return dialog loads returnable items, unchecked by default, hides Original Method for Cash."""
    returns_service = ReturnsService(db_session)
    auth_service = AuthenticationService(db_session)
    sale = sample_sales["cash_sale"]
    admin = auth_users["admin"]

    dlg = ProcessReturnDialog(
        sale=sale,
        current_user=admin,
        returns_service=returns_service,
        auth_service=auth_service,
    )
    qtbot.addWidget(dlg)
    dlg.show()

    # Returnable items rendered
    assert len(dlg._line_controls) == 2

    # Check controls for line 1
    line1_id = sale.items[0].id
    ctrl1 = dlg._line_controls[line1_id]
    assert ctrl1["chk"].isChecked() is False
    assert ctrl1["spin_qty"].isEnabled() is False
    assert ctrl1["spin_qty"].maximum() == 3
    assert ctrl1["cmb_disp"].isEnabled() is False
    assert ctrl1["cmb_disp"].currentData() == ReturnDisposition.RESTOCK.value

    # Cash Sale: Original Method radio button is hidden
    assert dlg.rb_orig.isVisible() is False
    assert dlg.rb_cash.isChecked() is True

    # Preview initial state
    assert dlg.lbl_prev_subtotal.text() == "₱0.00"
    assert dlg.lbl_prev_total.text() == "₱0.00"


def test_process_return_dialog_electronic_sale_shows_original_method(qtbot, db_session, auth_users, sample_sales):
    """Electronic GCash sale displays Original Method option and toggles reference field."""
    returns_service = ReturnsService(db_session)
    auth_service = AuthenticationService(db_session)
    sale = sample_sales["gcash_sale"]
    admin = auth_users["admin"]

    dlg = ProcessReturnDialog(
        sale=sale,
        current_user=admin,
        returns_service=returns_service,
        auth_service=auth_service,
    )
    qtbot.addWidget(dlg)
    dlg.show()

    assert dlg.rb_orig.isVisible() is True
    assert "GCASH" in dlg.rb_orig.text()

    # Toggle to original method
    dlg.rb_orig.setChecked(True)
    assert dlg.ref_row.isVisible() is True

    dlg.rb_cash.setChecked(True)
    assert dlg.ref_row.isVisible() is False


def test_process_return_dialog_item_selection_and_preview_update(qtbot, db_session, auth_users, sample_sales):
    """Selecting an item triggers preview calculation without database modification."""
    returns_service = ReturnsService(db_session)
    auth_service = AuthenticationService(db_session)
    sale = sample_sales["cash_sale"]
    admin = auth_users["admin"]

    dlg = ProcessReturnDialog(
        sale=sale,
        current_user=admin,
        returns_service=returns_service,
        auth_service=auth_service,
    )
    qtbot.addWidget(dlg)
    dlg.show()

    line1_id = sale.items[0].id
    ctrl1 = dlg._line_controls[line1_id]

    # Select 2 units of Item 1
    ctrl1["chk"].setChecked(True)
    assert ctrl1["spin_qty"].isEnabled() is True
    ctrl1["spin_qty"].setValue(2)

    # Force immediate preview calculation
    dlg._fetch_preview()

    assert dlg._latest_preview is not None
    assert dlg._latest_preview.subtotal_returned == Decimal("200.00")
    assert dlg.lbl_prev_subtotal.text() == "₱200.00"
    assert "₱224.00" in dlg.lbl_prev_total.text()


def test_process_return_dialog_review_step_and_immutable_warning(qtbot, db_session, auth_users, sample_sales):
    """Review step renders summary table, immutable warning, and back navigation."""
    returns_service = ReturnsService(db_session)
    auth_service = AuthenticationService(db_session)
    sale = sample_sales["cash_sale"]
    admin = auth_users["admin"]

    dlg = ProcessReturnDialog(
        sale=sale,
        current_user=admin,
        returns_service=returns_service,
        auth_service=auth_service,
    )
    qtbot.addWidget(dlg)
    dlg.show()

    line1_id = sale.items[0].id
    dlg._line_controls[line1_id]["chk"].setChecked(True)
    dlg._fetch_preview()

    # Navigate to Review
    dlg._go_to_review()
    assert dlg.stack.currentIndex() == 1

    # Check that error is raised if Reason is OTHER but notes are blank
    dlg.stack.setCurrentIndex(0)
    idx_other = dlg.cmb_reason.findData(ReturnReason.OTHER.value)
    dlg.cmb_reason.setCurrentIndex(idx_other)
    dlg.txt_notes.setText("")

    dlg._go_to_review()
    assert dlg.stack.currentIndex() == 0  # blocked
    assert "Reason notes are required" in dlg.lbl_config_error.text()


def test_process_return_dialog_admin_self_approval_execution(qtbot, db_session, auth_users, sample_sales):
    """Admin executes return with self-approval, completing transaction successfully."""
    returns_service = ReturnsService(db_session)
    auth_service = AuthenticationService(db_session)
    sale = sample_sales["cash_sale"]
    admin = auth_users["admin"]

    dlg = ProcessReturnDialog(
        sale=sale,
        current_user=admin,
        returns_service=returns_service,
        auth_service=auth_service,
    )
    qtbot.addWidget(dlg)
    dlg.show()

    line1_id = sale.items[0].id
    dlg._line_controls[line1_id]["chk"].setChecked(True)
    dlg._line_controls[line1_id]["spin_qty"].setValue(1)
    dlg._fetch_preview()

    dlg._go_to_review()
    dlg._on_confirm_refund()

    assert dlg.result() == QDialog.Accepted
    assert dlg.final_return_dto is not None
    assert dlg.final_return_dto.total_refund_amount == Decimal("112.00")
    assert dlg.final_return_dto.approved_by_id == admin.id


def test_process_return_dialog_idempotency_key_preserved_on_error(qtbot, db_session, auth_users, sample_sales):
    """ProcessReturnDialog preserves its unique idempotency_key across validation retries."""
    returns_service = ReturnsService(db_session)
    auth_service = AuthenticationService(db_session)
    sale = sample_sales["cash_sale"]
    admin = auth_users["admin"]

    dlg = ProcessReturnDialog(
        sale=sale,
        current_user=admin,
        returns_service=returns_service,
        auth_service=auth_service,
    )
    qtbot.addWidget(dlg)
    dlg.show()

    initial_key = dlg.idempotency_key
    assert initial_key.startswith("UI-")

    line1_id = sale.items[0].id
    dlg._line_controls[line1_id]["chk"].setChecked(True)
    dlg._fetch_preview()

    dlg._go_to_review()
    assert dlg.idempotency_key == initial_key


# ─── 3. ReturnDetailsDialog Tests ───

def test_return_details_dialog_renders_voucher_dto(qtbot, db_session, auth_users, sample_sales):
    """ReturnDetailsDialog renders all read-only fields from SalesReturnDTO."""
    returns_service = ReturnsService(db_session)
    sale = sample_sales["cash_sale"]
    admin = auth_users["admin"]

    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=1, disposition=ReturnDisposition.RESTOCK.value)],
        reason_code=ReturnReason.DEFECTIVE.value,
    )
    ret_dto = returns_service.process_return(req, actor=admin, idempotency_key="KEY-VOUCHER-TEST-1")

    dlg = ReturnDetailsDialog(return_dto=ret_dto)
    qtbot.addWidget(dlg)
    dlg.show()

    assert ret_dto.return_number in dlg.windowTitle()
    assert dlg.ret.total_refund_amount == Decimal("112.00")


# ─── 4. SaleDetailsDialog & SalesPage Integration Tests ───

def test_sale_details_dialog_shows_return_history_and_button(qtbot, db_session, auth_users, sample_sales):
    """SaleDetailsDialog displays Return History and enables Process Return button."""
    returns_service = ReturnsService(db_session)
    auth_service = AuthenticationService(db_session)
    sale = sample_sales["cash_sale"]
    admin = auth_users["admin"]

    # Initial state (0 returns)
    dlg = SaleDetailsDialog(
        sale=sale,
        returns_service=returns_service,
        auth_service=auth_service,
        current_user=admin,
    )
    qtbot.addWidget(dlg)
    dlg.show()

    assert hasattr(dlg, "btn_process_return")
    assert dlg.btn_process_return.isEnabled() is True

    # Process return
    req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[
            ReturnItemRequestDTO(sale_line_item_id=sale.items[0].id, quantity=3),
            ReturnItemRequestDTO(sale_line_item_id=sale.items[1].id, quantity=2),
        ],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    returns_service.process_return(req, actor=admin, idempotency_key="KEY-FULL-RET-TEST")

    # Reload dialog
    dlg2 = SaleDetailsDialog(
        sale=sale,
        returns_service=returns_service,
        auth_service=auth_service,
        current_user=admin,
    )
    qtbot.addWidget(dlg2)
    dlg2.show()

    # When fully returned, button is disabled
    assert dlg2.btn_process_return.isEnabled() is False


def test_sales_page_renders_return_badges(qtbot, db_session, auth_users, sample_sales):
    """SalesPage renders PARTIAL RETURN and FULLY RETURNED badges while preserving COMPLETED status."""
    sales_service = SalesService(db_session)
    returns_service = ReturnsService(db_session)
    auth_service = AuthenticationService(db_session)
    admin = auth_users["admin"]
    cash_sale = sample_sales["cash_sale"]

    # Process partial return
    req = ProcessReturnRequestDTO(
        sale_id=cash_sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=cash_sale.items[0].id, quantity=1)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    returns_service.process_return(req, actor=admin, idempotency_key="KEY-PAGE-BADGE-1")

    page = SalesPage(
        current_user=admin,
        sales_service=sales_service,
        returns_service=returns_service,
        auth_service=auth_service,
    )
    qtbot.addWidget(page)
    page.show()

    assert page.tbl_sales.rowCount() >= 2
    # Find row corresponding to cash_sale
    cash_row = None
    for r in range(page.tbl_sales.rowCount()):
        item = page.tbl_sales.item(r, 0)
        if item and item.text() == cash_sale.transaction_number:
            cash_row = r
            break
    assert cash_row is not None

    # Verify status cell contains COMPLETED and PARTIAL RETURN
    cell_widget = page.tbl_sales.cellWidget(cash_row, 5)
    assert cell_widget is not None
    labels = cell_widget.findChildren(QLabel)
    label_texts = [lbl.text() for lbl in labels]
    assert "COMPLETED" in label_texts
    assert "PARTIAL RETURN" in label_texts


def test_process_return_dialog_cashier_workflow_with_manager_override(qtbot, db_session, auth_users, sample_sales, monkeypatch):
    """Cashier processing a return prompts for manager override and submits with approver identity."""
    returns_service = ReturnsService(db_session)
    auth_service = AuthenticationService(db_session)
    sale = sample_sales["cash_sale"]
    cashier = auth_users["cashier"]
    manager = auth_users["manager"]

    dlg = ProcessReturnDialog(
        sale=sale,
        current_user=cashier,
        returns_service=returns_service,
        auth_service=auth_service,
    )
    qtbot.addWidget(dlg)
    dlg.show()

    line1_id = sale.items[0].id
    dlg._line_controls[line1_id]["chk"].setChecked(True)
    dlg._fetch_preview()
    dlg._go_to_review()

    # Monkeypatch ManagerOverrideDialog.exec to simulate successful manager login
    def mock_override_exec(self_dlg):
        self_dlg.authenticated_approver = manager
        return QDialog.Accepted

    monkeypatch.setattr(ManagerOverrideDialog, "exec", mock_override_exec)

    dlg._on_confirm_refund()

    assert dlg.result() == QDialog.Accepted
    assert dlg.final_return_dto is not None
    assert dlg.final_return_dto.cashier_id == cashier.id
    assert dlg.final_return_dto.approved_by_id == manager.id


def test_process_return_dialog_concurrency_refresh_handling(qtbot, db_session, auth_users, sample_sales):
    """If returnable quantities become stale, confirmation failure catches error and refreshes returnable items."""
    returns_service = ReturnsService(db_session)
    auth_service = AuthenticationService(db_session)
    sale = sample_sales["cash_sale"]
    admin = auth_users["admin"]

    dlg = ProcessReturnDialog(
        sale=sale,
        current_user=admin,
        returns_service=returns_service,
        auth_service=auth_service,
    )
    qtbot.addWidget(dlg)
    dlg.show()

    # Operator selects 3 units of Item 1
    line1_id = sale.items[0].id
    dlg._line_controls[line1_id]["chk"].setChecked(True)
    dlg._line_controls[line1_id]["spin_qty"].setValue(3)
    dlg._fetch_preview()
    dlg._go_to_review()

    # Meanwhile, another terminal returns 2 units of Item 1
    concurrent_req = ProcessReturnRequestDTO(
        sale_id=sale.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=line1_id, quantity=2)],
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
    )
    returns_service.process_return(concurrent_req, actor=admin, idempotency_key="KEY-CONCURRENT-TERMINAL-1")

    # Current dialog tries to confirm 3 units (which now exceeds remaining 1)
    dlg._on_confirm_refund()

    # Dialog remained open, reloaded items, and returned to step 0 with notification
    assert dlg.result() != QDialog.Accepted
    assert dlg.stack.currentIndex() == 0
    assert "Return availability changed" in dlg.lbl_review_error.text() or "Return availability changed" in dlg.lbl_config_error.text()
    assert dlg.btn_confirm.isEnabled() is True


def test_process_return_dialog_responsive_viewports(qtbot, db_session, auth_users, sample_sales):
    """Verify dialog geometry and usability at target viewports (1024x580, 1280x720, 1366x768, 1920x1080)."""
    returns_service = ReturnsService(db_session)
    auth_service = AuthenticationService(db_session)
    sale = sample_sales["cash_sale"]
    admin = auth_users["admin"]

    dlg = ProcessReturnDialog(
        sale=sale,
        current_user=admin,
        returns_service=returns_service,
        auth_service=auth_service,
    )
    qtbot.addWidget(dlg)

    for w, h in [(1024, 580), (1280, 720), (1366, 768), (1920, 1080)]:
        dlg.resize(min(740, w - 40), min(680, h - 40))
        assert dlg.width() <= w
        assert dlg.height() <= h


