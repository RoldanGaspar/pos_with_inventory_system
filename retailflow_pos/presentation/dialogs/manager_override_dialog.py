"""
RetailFlow POS - Manager Override Authorization Dialog
Modal for authenticating a Manager/Admin to approve cashier returns without elevating global session.
"""

from typing import Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from application.services.auth_service import AuthenticationService
from domain.exceptions import (
    AccountInactiveError,
    AccountLockedError,
    AuthenticationError,
    AuthorizationError,
)
from infrastructure.database.models.auth import User
from presentation.styles.icons import IconManager


class ManagerOverrideDialog(QDialog):
    """Modal dialog for synchronous Manager / Admin authorization."""

    def __init__(
        self,
        auth_service: AuthenticationService,
        required_permission: str = "refund_approve",
        action_title: str = "Authorize Customer Return",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._auth_service = auth_service
        self._required_permission = required_permission
        self._action_title = action_title
        self.authenticated_approver: Optional[User] = None
        self._drag_pos = QPoint()

        self.setWindowTitle("Manager Authorization Required")
        self.setFixedSize(400, 320)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self._init_ui()

    def _init_ui(self):
        container = QFrame(self)
        container.setObjectName("dialogContainerCard")
        container.setStyleSheet("""
            QFrame#dialogContainerCard {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 12px;
            }
            QLabel {
                color: #0f172a;
                border: none;
                background: transparent;
            }
        """)

        dialog_layout = QVBoxLayout(self)
        dialog_layout.setContentsMargins(0, 0, 0, 0)
        dialog_layout.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 1. Header ──
        header_card = QFrame()
        header_card.setObjectName("dialogHeaderCard")
        header_card.setStyleSheet("""
            QFrame#dialogHeaderCard {
                background-color: #f8fafc;
                border-bottom: 1px solid #e2e8f0;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                padding: 12px 16px;
            }
        """)
        header_card.mousePressEvent = self._on_header_mouse_press
        header_card.mouseMoveEvent = self._on_header_mouse_move

        hdr_layout = QHBoxLayout(header_card)
        hdr_layout.setContentsMargins(0, 0, 0, 0)

        hdr_text_layout = QVBoxLayout()
        hdr_text_layout.setSpacing(2)

        hdr_title = QLabel("Manager Approval Required")
        hdr_title.setStyleSheet("color: #0f172a; font-size: 14px; font-weight: 800;")
        hdr_text_layout.addWidget(hdr_title)

        hdr_sub = QLabel(self._action_title)
        hdr_sub.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 500;")
        hdr_text_layout.addWidget(hdr_sub)
        hdr_layout.addLayout(hdr_text_layout)
        hdr_layout.addStretch()

        btn_close = QPushButton()
        btn_close.setIcon(IconManager.get_pixmap("close", color="#64748b", size=14))
        btn_close.setFixedSize(26, 26)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("background: transparent; border: none; border-radius: 4px;")
        btn_close.clicked.connect(self.reject)
        hdr_layout.addWidget(btn_close)
        layout.addWidget(header_card)

        # ── 2. Body / Inputs ──
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(12)

        # Error Banner (Hidden initially)
        self.lbl_error = QLabel("")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setStyleSheet("""
            background-color: #fef2f2;
            color: #b91c1c;
            border: 1px solid #fecaca;
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 11px;
            font-weight: 600;
        """)
        self.lbl_error.setVisible(False)
        body_layout.addWidget(self.lbl_error)

        # Username Input
        lbl_user = QLabel("Manager Username")
        lbl_user.setStyleSheet("font-size: 11px; font-weight: 700; color: #475569;")
        body_layout.addWidget(lbl_user)

        self.txt_username = QLineEdit()
        self.txt_username.setPlaceholderText("Enter manager username")
        self.txt_username.setFixedHeight(34)
        self.txt_username.setStyleSheet("""
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 0 10px;
                font-size: 12px;
                color: #0f172a;
            }
            QLineEdit:focus {
                border: 1px solid #2563eb;
            }
        """)
        body_layout.addWidget(self.txt_username)

        # Password Input
        lbl_pass = QLabel("Manager Password")
        lbl_pass.setStyleSheet("font-size: 11px; font-weight: 700; color: #475569;")
        body_layout.addWidget(lbl_pass)

        self.txt_password = QLineEdit()
        self.txt_password.setPlaceholderText("Enter manager password")
        self.txt_password.setEchoMode(QLineEdit.Password)
        self.txt_password.setFixedHeight(34)
        self.txt_password.setStyleSheet("""
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 0 10px;
                font-size: 12px;
                color: #0f172a;
            }
            QLineEdit:focus {
                border: 1px solid #2563eb;
            }
        """)
        self.txt_password.returnPressed.connect(self._on_authorize)
        body_layout.addWidget(self.txt_password)

        layout.addWidget(body)
        layout.addStretch()

        # ── 3. Footer Actions ──
        footer = QFrame()
        footer.setStyleSheet("""
            background-color: #f8fafc;
            border-top: 1px solid #e2e8f0;
            border-bottom-left-radius: 12px;
            border-bottom-right-radius: 12px;
            padding: 10px 16px;
        """)
        ft_layout = QHBoxLayout(footer)
        ft_layout.setContentsMargins(0, 0, 0, 0)
        ft_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(32)
        btn_cancel.setFixedWidth(75)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                color: #0f172a;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        ft_layout.addWidget(btn_cancel)

        self.btn_authorize = QPushButton("Authorize")
        self.btn_authorize.setFixedHeight(32)
        self.btn_authorize.setFixedWidth(90)
        self.btn_authorize.setCursor(Qt.PointingHandCursor)
        self.btn_authorize.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        self.btn_authorize.clicked.connect(self._on_authorize)
        ft_layout.addWidget(self.btn_authorize)

        layout.addWidget(footer)

    def _on_header_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _on_header_mouse_move(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def _on_authorize(self):
        username = self.txt_username.text().strip()
        password = self.txt_password.text()

        if not username:
            self._show_error("Please enter manager username.")
            self.txt_username.setFocus()
            return

        if not password:
            self._show_error("Please enter manager password.")
            self.txt_password.setFocus()
            return

        try:
            # Authenticate credentials and permission without creating orphaned sessions or mutating last_login
            user = self._auth_service.verify_credentials(
                username=username,
                password=password,
                required_permission=self._required_permission,
            )
            self.authenticated_approver = user
            self.accept()

        except AuthenticationError:
            self._show_error("Invalid manager username or password.")
            self.txt_password.clear()
            self.txt_password.setFocus()
        except AccountInactiveError:
            self._show_error(f"Approving account '{username}' has been deactivated.")
            self.txt_password.clear()
        except AccountLockedError as e:
            self._show_error(str(e))
            self.txt_password.clear()
        except Exception as e:
            self._show_error(f"Authorization error: {str(e)}")
            self.txt_password.clear()

    def _show_error(self, message: str):
        self.lbl_error.setText(message)
        self.lbl_error.setVisible(True)
