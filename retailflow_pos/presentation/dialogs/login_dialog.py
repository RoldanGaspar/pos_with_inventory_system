"""
RetailFlow POS - Login Dialog
Professional login dialog with password toggle, remember username, and lockout feedback.
"""
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
    """Login dialog shown at application startup."""

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
        self.setStyleSheet("""
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
        """)

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
        self.txt_username.setText("admin")
        layout.addWidget(self.txt_username)

        # Password
        self.txt_password = QLineEdit()
        self.txt_password.setPlaceholderText("Password")
        self.txt_password.setText("admin123")
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
            self._show_error(f"An error occurred. Please try again.\n{str(e)}")
        finally:
            self.btn_login.setEnabled(True)
            self.btn_login.setText("Sign In")
            self.txt_password.clear()

    def get_user(self) -> User | None:
        return self._user

    def get_token(self) -> str:
        return self._token
