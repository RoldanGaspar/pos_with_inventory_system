"""
RetailFlow POS - Users Page UI Tests
Tests PySide6 UsersPage rendering, role filtering, search, lock toggling, and dialogs.
"""

import pytest
from PySide6.QtCore import Qt

from application.dto.user_dto import CreateUserDTO
from application.services.user_service import UserService
from infrastructure.database.models.auth import Role, User
from presentation.widgets.users_page import UsersPage


@pytest.fixture
def users_sample(db_session, user_with_permissions):
    admin = user_with_permissions("view_users", "create_users", "edit_users", "delete_users")
    admin.username = "admin_test"
    admin.full_name = "Admin Test User"

    # Add a cashier role if not exists
    cashier_role = db_session.query(Role).filter(Role.code == "cashier").first()
    if not cashier_role:
        cashier_role = Role(name="Cashier", code="cashier", description="Cashier staff")
        db_session.add(cashier_role)
        db_session.flush()

    user_service = UserService(db_session)
    u1 = user_service.create_user(
        CreateUserDTO(
            username="cashier_jane",
            full_name="Jane Cashier",
            password="Password123!",
            email="jane@store.com",
            phone="09123456789",
            role_code="cashier",
        ),
        actor=admin,
    )
    u2 = user_service.create_user(
        CreateUserDTO(
            username="cashier_john",
            full_name="John Cashier",
            password="Password123!",
            email="john@store.com",
            phone="09987654321",
            role_code="cashier",
        ),
        actor=admin,
    )
    user_service.toggle_lock(u2.id, True, actor=admin)
    db_session.commit()

    return admin, user_service


def test_users_page_renders_table(qtbot, users_sample):
    admin, user_service = users_sample
    page = UsersPage(admin, user_service)
    qtbot.addWidget(page)

    assert page.tbl_users.rowCount() >= 3
    assert int(page.card_total._value_label.text()) >= 3


def test_users_page_search_filtering(qtbot, users_sample):
    admin, user_service = users_sample
    page = UsersPage(admin, user_service)
    qtbot.addWidget(page)

    page.txt_search.setText("Jane")
    assert page.tbl_users.rowCount() == 1

    page.txt_search.setText("NON_EXISTENT_USER_XYZ")
    assert page.tbl_users.rowCount() == 0


def test_users_page_role_filtering(qtbot, users_sample):
    admin, user_service = users_sample
    page = UsersPage(admin, user_service)
    qtbot.addWidget(page)

    idx = page.cmb_role.findData("cashier")
    if idx >= 0:
        page.cmb_role.setCurrentIndex(idx)
        assert page.tbl_users.rowCount() >= 2


def test_users_page_status_filtering(qtbot, users_sample):
    admin, user_service = users_sample
    page = UsersPage(admin, user_service)
    qtbot.addWidget(page)

    idx = page.cmb_status.findData("locked")
    page.cmb_status.setCurrentIndex(idx)
    assert page.tbl_users.rowCount() >= 1
