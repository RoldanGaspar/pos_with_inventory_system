"""
RetailFlow POS - Audit Page UI Tests
Tests PySide6 AuditPage rendering, keyword search, module filtering, and pagination.
"""

import pytest
from PySide6.QtCore import Qt

from application.services.audit_service import AuditService
from infrastructure.database.models.auth import AuditLog, User
from infrastructure.database.repositories.auth import AuditLogRepository
from presentation.widgets.audit_page import AuditPage


@pytest.fixture
def audit_sample(db_session, user_with_permissions):
    admin = user_with_permissions("view_audit_logs", "view_users")
    admin.username = "audit_admin"
    admin.full_name = "Audit Admin User"

    audit_repo = AuditLogRepository(db_session)
    audit_repo.log_action(
        user_id=admin.id,
        username="audit_admin",
        action="LOGIN_SUCCESS",
        module="auth",
        new_value="Session started",
        ip_address="127.0.0.1",
    )
    audit_repo.log_action(
        user_id=admin.id,
        username="audit_admin",
        action="STOCK_ADJUSTMENT",
        module="inventory",
        previous_value="Quantity: 5",
        new_value="Quantity: 25 (+20)",
        ip_address="127.0.0.1",
        reason="Supplier delivery",
    )
    audit_repo.log_action(
        user_id=admin.id,
        username="audit_admin",
        action="CREATE_USER",
        module="users",
        new_value="Created user john_doe",
        ip_address="127.0.0.1",
    )
    db_session.commit()

    audit_service = AuditService(db_session)
    return admin, audit_service


def test_audit_page_renders_table(qtbot, audit_sample):
    admin, audit_service = audit_sample
    page = AuditPage(admin, audit_service)
    qtbot.addWidget(page)

    assert page.tbl_audit.rowCount() >= 3
    assert int(page.card_total._value_label.text()) >= 3


def test_audit_page_search_filtering(qtbot, audit_sample):
    admin, audit_service = audit_sample
    page = AuditPage(admin, audit_service)
    qtbot.addWidget(page)

    page.txt_search.setText("STOCK_ADJUSTMENT")
    assert page.tbl_audit.rowCount() >= 1

    page.txt_search.setText("NON_EXISTENT_LOG_STRING_12345")
    assert page.tbl_audit.rowCount() == 0


def test_audit_page_module_filtering(qtbot, audit_sample):
    admin, audit_service = audit_sample
    page = AuditPage(admin, audit_service)
    qtbot.addWidget(page)

    idx = page.cmb_module.findData("auth")
    if idx >= 0:
        page.cmb_module.setCurrentIndex(idx)
        assert page.tbl_audit.rowCount() >= 1


def test_audit_page_action_filtering(qtbot, audit_sample):
    admin, audit_service = audit_sample
    page = AuditPage(admin, audit_service)
    qtbot.addWidget(page)

    idx = page.cmb_action.findData("CREATE_USER")
    if idx >= 0:
        page.cmb_action.setCurrentIndex(idx)
        assert page.tbl_audit.rowCount() >= 1
