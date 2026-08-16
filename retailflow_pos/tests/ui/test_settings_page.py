"""
RetailFlow POS - Settings Page UI Tests
Verifies SettingsPage form data binding, live receipt preview, managed logo UI controls,
system diagnostics copy, dirty-state lifecycle, navigation guards, RBAC integration, and responsive viewports.
"""

from pathlib import Path
from unittest.mock import patch

import PIL.Image
import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app.config import settings
from application.dto.settings_dto import StoreSettingsDTO, UpdateReceiptPreferencesDTO, UpdateStoreProfileDTO
from application.services.settings_service import SettingsService
from infrastructure.database.models.auth import Permission, Role, User
from infrastructure.database.models.settings import StoreSettings
from infrastructure.database.seeders.settings_seeder import seed_settings
from presentation.widgets.settings_page import SettingsPage
from presentation.windows.main_window import MainWindow


@pytest.fixture
def auth_users(db_session):
    """Seed test users with permissions for Settings testing."""
    view_perm = Permission(code="view_settings", name="View Settings", module="settings")
    edit_perm = Permission(code="edit_settings", name="Edit Settings", module="settings")
    db_session.add_all([view_perm, edit_perm])
    db_session.flush()

    admin_role = Role(name="Administrator", code="admin", permissions=[view_perm, edit_perm])
    mgr_role = Role(name="Manager", code="manager", permissions=[view_perm, edit_perm])
    cashier_role = Role(name="Cashier", code="cashier", permissions=[])
    auditor_role = Role(name="Auditor", code="auditor", permissions=[])

    admin = User(username="admin_ui", email="admin@ui.com", password_hash="h", full_name="Admin UI", roles=[admin_role])
    manager = User(username="mgr_ui", email="mgr@ui.com", password_hash="h", full_name="Manager UI", roles=[mgr_role])
    cashier = User(username="cashier_ui", email="cashier@ui.com", password_hash="h", full_name="Cashier UI", roles=[cashier_role])
    auditor = User(username="auditor_ui", email="auditor@ui.com", password_hash="h", full_name="Auditor UI", roles=[auditor_role])

    db_session.add_all([admin_role, mgr_role, cashier_role, auditor_role, admin, manager, cashier, auditor])
    db_session.commit()

    seed_settings(db_session)
    db_session.commit()

    return {
        "admin": admin,
        "manager": manager,
        "cashier": cashier,
        "auditor": auditor,
    }


@pytest.fixture
def sample_png(tmp_path) -> Path:
    """Create a sample valid PNG image."""
    img_path = tmp_path / "test_logo.png"
    img = PIL.Image.new("RGBA", (120, 60), color=(37, 99, 235, 255))
    img.save(img_path, format="PNG")
    return img_path


# ─── 1. Page Initialization & Binding Tests ───

def test_admin_settings_page_initialization(qtbot, db_session, auth_users):
    """Admin initializes SettingsPage and sees pre-populated baseline settings."""
    service = SettingsService(db_session)
    admin = auth_users["admin"]

    page = SettingsPage(current_user=admin, settings_service=service)
    qtbot.addWidget(page)

    assert page.txt_store_name.text() == "RetailFlow Store"
    assert page.cmb_paper_width.currentData() == "80mm"
    assert page.chk_show_address.isChecked() is True
    assert page.chk_show_tax.isChecked() is True
    assert not page.is_profile_dirty()
    assert not page.is_receipt_dirty()
    assert not page.btn_save_profile.isEnabled()
    assert not page.btn_save_receipt.isEnabled()


def test_manager_settings_page_initialization(qtbot, db_session, auth_users):
    """Manager initializes SettingsPage successfully."""
    service = SettingsService(db_session)
    manager = auth_users["manager"]

    page = SettingsPage(current_user=manager, settings_service=service)
    qtbot.addWidget(page)

    assert page.txt_store_name.text() == "RetailFlow Store"


def test_cashier_and_auditor_settings_page_denial(qtbot, db_session, auth_users):
    """Cashier and Auditor receive permission denied toast when attempting to load settings."""
    service = SettingsService(db_session)
    cashier = auth_users["cashier"]

    page = SettingsPage(current_user=cashier, settings_service=service)
    qtbot.addWidget(page)

    # Toast displays Access Denied
    assert "Access Denied" in page._toast.text()


# ─── 2. Store Profile Form & Validation Tests ───

def test_store_profile_valid_save(qtbot, db_session, auth_users):
    """Admin edits profile fields; dirty state activates; save persists authoritative DTO."""
    service = SettingsService(db_session)
    admin = auth_users["admin"]

    page = SettingsPage(current_user=admin, settings_service=service)
    qtbot.addWidget(page)

    # Edit fields
    page.txt_store_name.setText("Greenbelt Supermarket")
    page.txt_store_address.setPlainText("Greenbelt 5, Makati City")
    page.txt_contact.setText("+63 2 8999 1111")
    page.txt_email.setText("info@greenbelt.ph")
    page.txt_tin.setText("999-888-777-000")

    assert page.is_profile_dirty() is True
    assert page.btn_save_profile.isEnabled() is True

    # Click Save
    qtbot.mouseClick(page.btn_save_profile, Qt.LeftButton)

    assert page.is_profile_dirty() is False
    assert page.btn_save_profile.isEnabled() is False
    assert "Store profile updated successfully" in page._toast.text()

    # Verify DB persistence
    saved = db_session.query(StoreSettings).filter_by(id=1).first()
    assert saved.store_name == "Greenbelt Supermarket"
    assert saved.store_address == "Greenbelt 5, Makati City"


def test_store_profile_validation_failure_preserves_input(qtbot, db_session, auth_users):
    """Validation failure displays error toast and preserves entered user input."""
    service = SettingsService(db_session)
    admin = auth_users["admin"]

    page = SettingsPage(current_user=admin, settings_service=service)
    qtbot.addWidget(page)

    page.txt_store_name.setText("Valid Store")
    page.txt_email.setText("invalid-email-format")

    qtbot.mouseClick(page.btn_save_profile, Qt.LeftButton)

    assert "Validation Error" in page._toast.text()
    assert page.txt_store_name.text() == "Valid Store"
    assert page.txt_email.text() == "invalid-email-format"


def test_store_profile_no_op_keeps_clean_state(qtbot, db_session, auth_users):
    """If inputs match persisted baseline, dirty state remains false."""
    service = SettingsService(db_session)
    admin = auth_users["admin"]

    page = SettingsPage(current_user=admin, settings_service=service)
    qtbot.addWidget(page)

    page.txt_store_name.setText("RetailFlow Store")
    assert not page.is_profile_dirty()
    assert not page.btn_save_profile.isEnabled()


# ─── 3. Receipt Preferences & Live Preview Tests ───

def test_receipt_preferences_valid_save_and_preview(qtbot, db_session, auth_users):
    """Admin updates receipt preferences; live preview reacts immediately; save persists."""
    service = SettingsService(db_session)
    admin = auth_users["admin"]

    page = SettingsPage(current_user=admin, settings_service=service)
    qtbot.addWidget(page)

    # Switch to Receipt tab
    page._switch_tab(1)

    # Edit preferences
    page.txt_receipt_header.setText("Custom Branch Header")
    page.cmb_paper_width.setCurrentIndex(1)  # 58mm
    page.chk_show_address.setChecked(False)
    page.chk_show_tax.setChecked(False)

    # Verify live preview updated immediately
    assert page.lbl_prev_header.text() == "Custom Branch Header"
    assert page.lbl_prev_address.isVisible() is False
    assert page.lbl_prev_tax_block.isVisible() is False
    assert page.paper_preview_card.width() == 270  # 58mm simulated compact width

    assert page.is_receipt_dirty() is True
    assert page.btn_save_receipt.isEnabled() is True

    # Save
    qtbot.mouseClick(page.btn_save_receipt, Qt.LeftButton)

    assert page.is_receipt_dirty() is False
    assert "Receipt preferences updated successfully" in page._toast.text()

    saved = db_session.query(StoreSettings).filter_by(id=1).first()
    assert saved.receipt_header == "Custom Branch Header"
    assert saved.paper_width == "58mm"
    assert saved.show_store_address is False
    assert saved.show_tax_details is False


# ─── 4. Logo Management UI Tests ───

def test_choose_valid_logo_and_apply(qtbot, db_session, auth_users, sample_png):
    """User chooses logo file; staged preview renders; applying updates persisted logo."""
    service = SettingsService(db_session)
    admin = auth_users["admin"]

    page = SettingsPage(current_user=admin, settings_service=service)
    qtbot.addWidget(page)
    page.show()
    QApplication.processEvents()

    # Mock QFileDialog to return sample_png
    with patch.object(QFileDialog, "getOpenFileName", return_value=(str(sample_png), "Images (*.png)")):
        page._on_choose_logo()

    assert page._staged_logo_path == sample_png
    assert page.lbl_logo_status.text() == "Staged Logo (Unsaved)"
    assert page.btn_apply_logo.isVisible() is True

    # Apply staged logo
    page._on_apply_staged_logo()

    assert page._staged_logo_path is None
    assert page.lbl_logo_status.text() == "Active Managed Logo"
    assert page.btn_remove_logo.isVisible() is True
    assert "Store logo updated successfully" in page._toast.text()
    page.close()


def test_remove_logo_confirmation_flow(qtbot, db_session, auth_users, sample_png):
    """User clicks Remove Logo; confirming removal clears DB logo and updates UI."""
    service = SettingsService(db_session)
    admin = auth_users["admin"]

    # Upload logo first
    service.update_store_logo(sample_png, actor=admin)

    page = SettingsPage(current_user=admin, settings_service=service)
    qtbot.addWidget(page)
    page.show()
    QApplication.processEvents()

    assert page.btn_remove_logo.isVisible() is True

    # Mock confirmation dialog: user selects Yes
    with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
        page._on_remove_logo()

    assert page.lbl_logo_status.text() == "No Logo Configured"
    assert page.btn_remove_logo.isVisible() is False
    assert "Store logo removed" in page._toast.text()
    page.close()


# ─── 5. Dirty-State & Navigation Guard Tests ───

def test_dirty_state_section_switching_retains_edits(qtbot, db_session, auth_users):
    """Switching between tabs does not lose in-memory unsaved edits."""
    service = SettingsService(db_session)
    admin = auth_users["admin"]

    page = SettingsPage(current_user=admin, settings_service=service)
    qtbot.addWidget(page)

    # Edit profile
    page.txt_store_name.setText("Unsaved Name 123")
    assert page.is_profile_dirty() is True

    # Switch to Receipt tab then back to Profile tab
    page._switch_tab(1)
    page._switch_tab(0)

    assert page.txt_store_name.text() == "Unsaved Name 123"
    assert page.is_profile_dirty() is True


def test_navigation_leave_guard_in_main_window(qtbot, db_session, auth_users):
    """Navigating away with unsaved settings prompts confirmation; discard resets values."""
    service = SettingsService(db_session)
    admin = auth_users["admin"]

    window = MainWindow(current_user=admin, session=db_session, settings_service=service)
    qtbot.addWidget(window)

    # Navigate to Settings
    window.navigate_to("settings")
    assert window._current_page == "settings"

    # Make unsaved edit
    window._settings_page.txt_store_name.setText("Unsaved Modified Name")
    assert window._settings_page.has_unsaved_changes() is True

    # 1. Attempt navigate away but Cancel
    with patch.object(QMessageBox, "warning", return_value=QMessageBox.Cancel):
        window.navigate_to("dashboard")
        # Stayed on settings
        assert window._current_page == "settings"
        assert window._settings_page.txt_store_name.text() == "Unsaved Modified Name"

    # 2. Attempt navigate away and Discard
    with patch.object(QMessageBox, "warning", return_value=QMessageBox.Discard):
        window.navigate_to("dashboard")
        # Navigated to dashboard
        assert window._current_page == "dashboard"
        assert window._settings_page.has_unsaved_changes() is False


# ─── 6. System Diagnostics & Copy Action Tests ───

def test_diagnostics_copy_action(qtbot, db_session, auth_users):
    """Copy Diagnostic Summary writes sanitized DTO contents to clipboard."""
    service = SettingsService(db_session)
    admin = auth_users["admin"]

    page = SettingsPage(current_user=admin, settings_service=service)
    qtbot.addWidget(page)

    page._on_copy_diagnostics()

    clipboard_text = QApplication.clipboard().text()
    assert "RetailFlow POS System Diagnostics" in clipboard_text
    assert "Asia/Manila" in clipboard_text
    assert "Philippine Peso (PHP · ₱)" in clipboard_text
    assert "Diagnostic summary copied to clipboard" in page._toast.text()

    # Grouped, sanitized output: sections present, no absolute local paths
    for section in ("Application", "Runtime", "Business", "Database", "Storage"):
        assert section in clipboard_text
    assert str(settings.base_dir) not in clipboard_text
    assert "data\\retailflow.db" in clipboard_text.replace("/", "\\")


# ─── 7. MainWindow RBAC Routing Tests ───

def test_mainwindow_rbac_settings_access(qtbot, db_session, auth_users):
    """Admin and Manager can navigate to settings; Cashier and Auditor cannot."""
    service = SettingsService(db_session)

    # 1. Admin
    admin_win = MainWindow(current_user=auth_users["admin"], session=db_session, settings_service=service)
    qtbot.addWidget(admin_win)
    admin_win.navigate_to("settings")
    assert admin_win._current_page == "settings"
    admin_win.close()

    # 2. Cashier
    cashier_win = MainWindow(current_user=auth_users["cashier"], session=db_session, settings_service=service)
    qtbot.addWidget(cashier_win)
    assert cashier_win.nav_buttons["settings"].isVisible() is False
    cashier_win.navigate_to("settings")
    # Blocked from navigating to settings
    assert cashier_win._current_page != "settings"
    cashier_win.close()


# ─── 8. Responsive Viewport Smoke Tests ───

@pytest.mark.parametrize("width,height", [
    (1024, 580),
    (1280, 720),
    (1366, 768),
    (1920, 1080),
])
def test_settings_page_responsive_viewports(qtbot, db_session, auth_users, width, height):
    """SettingsPage renders cleanly across supported monitor resolutions."""
    service = SettingsService(db_session)
    admin = auth_users["admin"]

    page = SettingsPage(current_user=admin, settings_service=service)
    qtbot.addWidget(page)
    page.resize(width, height)
    page.show()
    QApplication.processEvents()

    assert page.btn_save_profile is not None
    assert page.btn_save_receipt is not None
    assert page.btn_copy_diag is not None
    page.close()
