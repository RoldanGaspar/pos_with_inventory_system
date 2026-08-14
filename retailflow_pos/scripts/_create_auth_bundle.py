"""Create all remaining authentication files for Milestone B."""
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

def write(p, content):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    print(f"  OK: {p.relative_to(BASE)}")

# 1. AuthService
write(BASE / "application" / "services" / "auth_service.py", """\"\"\"
RetailFlow POS - Authentication Service
Coordinates login, logout, lockout, and permission checking.
\"\"\"
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from infrastructure.database.repositories.auth import (
    UserRepository, AuditLogRepository, UserSessionRepository
)
from infrastructure.database.models.auth import User
from infrastructure.security.hashing import verify_password, hash_password, validate_password_strength
from app.config import settings
from domain.exceptions import (
    AuthenticationError, AccountLockedError, AccountInactiveError,
    PasswordExpiredError, AuthorizationError, ValidationError
)

logger = logging.getLogger("retailflow.security")


class AuthenticationService:
    \"\"\"Handles all authentication and authorization operations.\"\"\"

    def __init__(self, session: Session):
        self._session = session
        self.user_repo = UserRepository(session)
        self.audit_repo = AuditLogRepository(session)
        self.session_repo = UserSessionRepository(session)

    def login(
        self, username: str, password: str, ip_address: Optional[str] = None
    ) -> Tuple[User, str]:
        user = self.user_repo.get_by_username(username)
        if user is None:
            self.user_repo.record_login_attempt(
                username=username, success=False, ip_address=ip_address,
                failure_reason="User not found")
            raise AuthenticationError("Invalid username or password.")

        if not user.is_active:
            raise AccountInactiveError("This account has been deactivated.")

        if self.user_repo.is_locked_out(user):
            self.user_repo.record_login_attempt(
                username=username, success=False, ip_address=ip_address,
                failure_reason="Account locked", user_id=user.id)
            raise AccountLockedError(
                f"Account is temporarily locked. Try again in {settings.lockout_minutes} minutes.")

        if not verify_password(password, user.password_hash):
            self.user_repo.register_failed_attempt(user)
            self.user_repo.record_login_attempt(
                username=username, success=False, ip_address=ip_address,
                failure_reason="Incorrect password", user_id=user.id)
            logger.warning(f"Failed login for user: {username}")
            raise AuthenticationError("Invalid username or password.")

        if user.password_expires_at and user.password_expires_at < datetime.utcnow():
            raise PasswordExpiredError(
                "Your password has expired. Please change it before logging in.")

        self.user_repo.reset_failed_attempts(user)
        self.user_repo.record_login(user, ip_address)
        self.user_repo.record_login_attempt(
            username=username, success=True, ip_address=ip_address, user_id=user.id)

        token = secrets.token_urlsafe(48)
        self.session_repo.create_session(user.id, token, ip_address)
        logger.info(f"User logged in: {username}")
        return user, token

    def logout(self, token: str) -> None:
        self.session_repo.invalidate_session(token)
        logger.info("User logged out")

    def check_permission(self, user: User, permission_code: str) -> None:
        if not user.has_permission(permission_code):
            raise AuthorizationError(
                f"You do not have permission: {permission_code}")

    def change_password(self, user: User, current_password: str, new_password: str) -> None:
        if not verify_password(current_password, user.password_hash):
            raise AuthenticationError("Current password is incorrect.")
        is_valid, error_msg = validate_password_strength(new_password)
        if not is_valid:
            raise ValidationError(error_msg)
        if self.user_repo.check_password_history(user, new_password):
            raise ValidationError("You cannot reuse a previously used password.")
        new_hash = hash_password(new_password)
        self.user_repo.change_password(user, new_hash)
        self.audit_repo.log_action(
            user_id=user.id, username=user.username,
            action="PASSWORD_CHANGED", module="auth")
        logger.info(f"Password changed for: {user.username}")

    def reset_password(self, user: User, new_password: str) -> None:
        is_valid, error_msg = validate_password_strength(new_password)
        if not is_valid:
            raise ValidationError(error_msg)
        new_hash = hash_password(new_password)
        user.must_change_password = True
        self.user_repo.change_password(user, new_hash)
        self.audit_repo.log_action(
            user_id=user.id, username=user.username,
            action="PASSWORD_RESET", module="auth")
        logger.info(f"Password reset for: {user.username}")

    def lock_user(self, user: User) -> None:
        user.is_locked = True
        user.locked_until = datetime.utcnow() + timedelta(minutes=settings.lockout_minutes)
        self._session.flush()
        self.audit_repo.log_action(
            user_id=user.id, username=user.username,
            action="ACCOUNT_LOCKED", module="auth")

    def unlock_user(self, user: User) -> None:
        self.user_repo.reset_failed_attempts(user)
        self.audit_repo.log_action(
            user_id=user.id, username=user.username,
            action="ACCOUNT_UNLOCKED", module="auth")
""")

# 2. LoginDialog
write(BASE / "presentation" / "dialogs" / "login_dialog.py", """\"\"\"
RetailFlow POS - Login Dialog
Professional login dialog with password toggle, remember username, and lockout feedback.
\"\"\"
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QMessageBox, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont

from sqlalchemy.orm import Session

from application.services.auth_service import AuthenticationService
from domain.exceptions import (
    AuthenticationError, AccountLockedError, AccountInactiveError, PasswordExpiredError
)
from infrastructure.database.models.auth import User


class LoginDialog(QDialog):
    \"\"\"Login dialog shown at application startup.\"\"\"

    login_successful = Signal(User, str)  # user, session_token

    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self._auth_service = AuthenticationService(session)
        self._user: User | None = None
        self._token: str = ""
        self.setWindowTitle("RetailFlow POS - Login")
        self.setFixedSize(420, 360)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet(\"\"\"
            QDialog { background-color: #f5f6fa; }
            QLabel#titleLabel { font-size: 22px; font-weight: 700; color: #1e293b; }
            QLabel#subtitleLabel { font-size: 12px; color: #64748b; }
            QLabel#errorLabel { font-size: 12px; color: #ef4444; background: #fef2f2; border: 1px solid #fecaca; border-radius: 4px; padding: 8px; }
            QLineEdit { padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 6px; background: #ffffff; font-size: 14px; color: #1e293b; }
            QLineEdit:focus { border-color: #3b82f6; }
            QPushButton#loginButton { background-color: #3b82f6; color: #ffffff; border: none; border-radius: 6px; padding: 10px; font-size: 14px; font-weight: 600; }
            QPushButton#loginButton:hover { background-color: #2563eb; }
            QPushButton#loginButton:disabled { background-color: #94a3b8; }
            QCheckBox { font-size: 12px; color: #475569; }
        \"\"\")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(14)

        # Title
        title = QLabel("RetailFlow POS")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Sign in to your account")
        subtitle.setObjectName("subtitleLabel")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(8)

        # Error label (hidden by default)
        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        # Username
        self.txt_username = QLineEdit()
        self.txt_username.setPlaceholderText("Username")
        layout.addWidget(self.txt_username)

        # Password
        self.txt_password = QLineEdit()
        self.txt_password.setPlaceholderText("Password")
        self.txt_password.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.txt_password)

        # Show password checkbox
        self.chk_show_password = QCheckBox("Show password")
        self.chk_show_password.toggled.connect(self._toggle_password_visibility)
        layout.addWidget(self.chk_show_password)

        # Remember me
        self.chk_remember = QCheckBox("Remember username")
        layout.addWidget(self.chk_remember)

        layout.addSpacing(6)

        # Login button
        self.btn_login = QPushButton("Sign In")
        self.btn_login.setObjectName("loginButton")
        self.btn_login.setDefault(True)
        self.btn_login.clicked.connect(self._attempt_login)
        layout.addWidget(self.btn_login)

        # Focus username on show
        self.txt_username.setFocus()

        # Allow Enter key on password field too
        self.txt_password.returnPressed.connect(self._attempt_login)

    def _toggle_password_visibility(self, visible: bool):
        self.txt_password.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)

    def _show_error(self, message: str):
        self.error_label.setText(message)
        self.error_label.setVisible(True)

    def _hide_error(self):
        self.error_label.setVisible(False)

    def _attempt_login(self):
        username = self.txt_username.text().strip()
        password = self.txt_password.text()

        if not username or not password:
            self._show_error("Please enter both username and password.")
            return

        self._hide_error()
        self.btn_login.setEnabled(False)
        self.btn_login.setText("Signing in...")

        # Use QTimer to avoid blocking the GUI
        QTimer.singleShot(100, lambda: self._do_login(username, password))

    def _do_login(self, username: str, password: str):
        try:
            user, token = self._auth_service.login(username, password)
            self._user = user
            self._token = token
            self.accept()
            self.login_successful.emit(user, token)
        except AccountLockedError as e:
            self._show_error(str(e))
        except AccountInactiveError as e:
            self._show_error(str(e))
        except PasswordExpiredError as e:
            self._show_error(str(e))
        except AuthenticationError as e:
            self._show_error(str(e))
        except Exception as e:
            self._show_error(f"An error occurred. Please try again.\\n{str(e)}")
        finally:
            self.btn_login.setEnabled(True)
            self.btn_login.setText("Sign In")
            self.txt_password.clear()

    def get_user(self) -> User | None:
        return self._user

    def get_token(self) -> str:
        return self._token
""")

# 3. Seeder
write(BASE / "infrastructure" / "database" / "seeders" / "auth_seeder.py", """\"\"\"
RetailFlow POS - Authentication Seeder
Creates default roles, permissions, and admin user on first run.
\"\"\"
import logging
from sqlalchemy.orm import Session

from infrastructure.database.models.auth import User, Role, Permission
from infrastructure.security.hashing import hash_password
from app.constants import UserRole as UserRoleEnum

logger = logging.getLogger("retailflow.database")

# Default permissions per module
DEFAULT_PERMISSIONS = {
    "auth": [
        ("view_users", "View Users"),
        ("create_users", "Create Users"),
        ("edit_users", "Edit Users"),
        ("delete_users", "Delete Users"),
        ("manage_roles", "Manage Roles & Permissions"),
    ],
    "dashboard": [
        ("view_dashboard", "View Dashboard"),
    ],
    "products": [
        ("view_products", "View Products"),
        ("create_products", "Create Products"),
        ("edit_products", "Edit Products"),
        ("delete_products", "Delete Products"),
    ],
    "inventory": [
        ("view_inventory", "View Inventory"),
        ("receive_stock", "Receive Stock"),
        ("adjust_stock", "Adjust Stock"),
        ("transfer_stock", "Transfer Stock"),
    ],
    "suppliers": [
        ("view_suppliers", "View Suppliers"),
        ("manage_suppliers", "Manage Suppliers"),
    ],
    "purchasing": [
        ("view_purchase_orders", "View Purchase Orders"),
        ("create_purchase_orders", "Create Purchase Orders"),
        ("approve_purchase_orders", "Approve Purchase Orders"),
    ],
    "pos": [
        ("pos_access", "Access POS"),
        ("pos_discount", "Apply Discounts"),
        ("pos_void", "Void Transactions"),
        ("pos_hold_resume", "Hold & Resume Transactions"),
    ],
    "sales": [
        ("view_sales", "View Sales"),
        ("return_sales", "Process Returns"),
        ("refund_approve", "Approve Refunds"),
    ],
    "reports": [
        ("view_reports", "View Reports"),
        ("export_reports", "Export Reports"),
    ],
    "settings": [
        ("view_settings", "View Settings"),
        ("edit_settings", "Edit Settings"),
        ("manage_backup", "Manage Backups & Restore"),
    ],
    "audit": [
        ("view_audit_logs", "View Audit Logs"),
    ],
    "shifts": [
        ("open_shift", "Open Cashier Shift"),
        ("close_shift", "Close Shift"),
        ("approve_shift_close", "Approve Shift Closure"),
    ],
}

# Role-to-permission mapping
ROLE_PERMISSIONS = {
    UserRoleEnum.ADMINISTRATOR: ["*"],  # Admin gets all permissions
    UserRoleEnum.MANAGER: [
        "view_dashboard", "view_products", "create_products", "edit_products",
        "delete_products", "view_inventory", "receive_stock", "adjust_stock",
        "transfer_stock", "view_suppliers", "manage_suppliers",
        "view_purchase_orders", "create_purchase_orders", "approve_purchase_orders",
        "view_sales", "return_sales", "refund_approve",
        "view_reports", "export_reports",
        "view_settings", "edit_settings", "manage_backup",
        "view_audit_logs", "view_users", "create_users", "edit_users",
        "approve_shift_close",
    ],
    UserRoleEnum.CASHIER: [
        "pos_access", "pos_discount", "pos_hold_resume",
        "open_shift", "close_shift", "view_sales", "return_sales",
        "view_dashboard", "view_products", "view_inventory",
    ],
    UserRoleEnum.INVENTORY_STAFF: [
        "view_dashboard", "view_products", "view_inventory",
        "receive_stock", "adjust_stock", "transfer_stock",
        "view_suppliers", "view_purchase_orders",
    ],
    UserRoleEnum.AUDITOR: [
        "view_dashboard", "view_products", "view_inventory",
        "view_sales", "view_reports", "export_reports",
        "view_audit_logs", "view_suppliers", "view_purchase_orders",
        "view_users",
    ],
}


def seed_auth(session: Session) -> None:
    \"\"\"Seed roles, permissions, and admin user if they do not exist.\"\"\"
    # Check if already seeded
    existing_admin = session.query(User).filter(User.username == "admin").first()
    if existing_admin:
        logger.info("Auth data already seeded, skipping.")
        return

    logger.info("Seeding authentication data...")

    # Create permissions
    perm_map = {}
    for module, perms in DEFAULT_PERMISSIONS.items():
        for code, name in perms:
            perm = Permission(
                code=code, name=name, module=module,
                description=f"Allows {name.lower()}"
            )
            session.add(perm)
            perm_map[code] = perm
    session.flush()

    all_permission_codes = list(perm_map.keys())

    # Create roles
    for role_code in UserRoleEnum:
        role_perms = ROLE_PERMISSIONS.get(role_code, [])
        if role_perms == ["*"]:
            role_perms = all_permission_codes

        role = Role(
            name=role_code.value.replace("_", " ").title(),
            code=role_code.value,
            description=f"{role_code.value.replace('_', ' ').title()} role",
            is_system=True,
        )
        # Assign permissions
        role.permissions = [perm_map[code] for code in role_perms if code in perm_map]
        session.add(role)
    session.flush()

    # Create admin user
    admin_role = session.query(Role).filter(Role.code == UserRoleEnum.ADMINISTRATOR).first()
    admin = User(
        username="admin",
        password_hash=hash_password("admin123"),
        full_name="System Administrator",
        email="admin@retailflow.local",
        is_active=True,
        must_change_password=True,
    )
    admin.roles.append(admin_role)
    session.add(admin)

    # Create demo cashier
    cashier_role = session.query(Role).filter(Role.code == UserRoleEnum.CASHIER).first()
    cashier = User(
        username="cashier",
        password_hash=hash_password("cashier123"),
        full_name="Demo Cashier",
        is_active=True,
    )
    cashier.roles.append(cashier_role)
    session.add(cashier)

    # Create demo manager
    manager_role = session.query(Role).filter(Role.code == UserRoleEnum.MANAGER).first()
    manager = User(
        username="manager",
        password_hash=hash_password("manager123"),
        full_name="Demo Manager",
        is_active=True,
    )
    manager.roles.append(manager_role)
    session.add(manager)

    session.flush()
    logger.info(f"Seeded {len(perm_map)} permissions, {len(UserRoleEnum)} roles, 3 users.")

if __name__ == "__main__":
    from app.bootstrap import bootstrap, shutdown
    from infrastructure.database.session import create_session
    bootstrap()
    session = create_session()
    try:
        seed_auth(session)
        session.commit()
        print("Seeding complete!")
    except Exception as e:
        session.rollback()
        print(f"Seeding failed: {e}")
        raise
    finally:
        session.close()
        shutdown()
""")

# 4. Update bootstrap to auto-seed
bootstrap_path = BASE / "app" / "bootstrap.py"
current = bootstrap_path.read_text()
if "seed_auth" not in current:
    updated = current.replace(
        "init_database()",
        'init_database()\n\n    # Auto-seed auth data if first run\n    _seed_if_needed()'
    )
    updated += """
from infrastructure.database.seeders.auth_seeder import seed_auth

def _seed_if_needed() -> None:
    \"\"\"Seed default roles, permissions, and users on first run.\"\"\"
    from infrastructure.database.session import create_session
    session = create_session()
    try:
        seed_auth(session)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Seeding failed: {e}")
    finally:
        session.close()
"""
    bootstrap_path.write_text(updated)
    print("  Updated: app/bootstrap.py with auto-seeder")

print("\\nAll auth files created successfully!")