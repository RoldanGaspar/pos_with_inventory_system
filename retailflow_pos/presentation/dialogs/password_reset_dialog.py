"""
RetailFlow POS - Password Reset Dialog
Frameless modal for administrators to rapidly reset staff credentials with password strength
verification and auto-generation.
"""

import secrets
import string
from typing import Optional

from PySide6.QtCore import QPoint, Qt
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

from application.dto.user_dto import UserResponseDTO
from application.services.user_service import UserService
from domain.exceptions import RetailFlowError
from infrastructure.database.models.auth import User
from presentation.styles.icons import IconManager


class PasswordResetDialog(QDialog):
    """Modal for resetting a staff user's password."""

    def __init__(
        self,
        user_service: UserService,
        target_user: UserResponseDTO,
        current_actor: User,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._user_service = user_service
        self._user = target_user
        self._actor = current_actor
        self._drag_pos = QPoint()

        self.setWindowTitle(f"Reset Password — @{target_user.username}")
        self.setFixedSize(480, 420)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self._init_ui()

    def _init_ui(self):
        main_container = QFrame(self)
        main_container.setObjectName("dialogContainerCard")
        main_container.setStyleSheet("""
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
        dialog_layout.addWidget(main_container)

        container_layout = QVBoxLayout(main_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # ── 1. Draggable Header ──
        header_card = QFrame()
        header_card.setObjectName("dialogHeaderCard")
        header_card.setStyleSheet("""
            QFrame#dialogHeaderCard {
                background-color: #f8fafc;
                border-bottom: 1px solid #e2e8f0;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                padding: 12px 18px;
            }
        """)
        header_card.mousePressEvent = self._on_header_mouse_press
        header_card.mouseMoveEvent = self._on_header_mouse_move

        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(0, 0, 0, 0)

        hdr_text_layout = QVBoxLayout()
        hdr_text_layout.setSpacing(1)

        hdr_title = QLabel(f"Reset Password: {self._user.full_name}")
        hdr_title.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: 800;")
        hdr_text_layout.addWidget(hdr_title)

        hdr_sub = QLabel(f"Set a new password for @{self._user.username}")
        hdr_sub.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 500;")
        hdr_text_layout.addWidget(hdr_sub)

        header_layout.addLayout(hdr_text_layout)
        header_layout.addStretch()

        btn_close = QPushButton()
        btn_close.setIcon(IconManager.get_pixmap("close", color="#64748b", size=14))
        btn_close.setFixedSize(28, 28)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #f1f5f9; }
        """)
        btn_close.clicked.connect(self.reject)
        header_layout.addWidget(btn_close)

        container_layout.addWidget(header_card)

        # ── 2. Modal Body ──
        body_widget = QWidget()
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(12)

        # Error Banner
        self.error_banner = QLabel("")
        self.error_banner.setWordWrap(True)
        self.error_banner.setStyleSheet("""
            background-color: #fef2f2;
            color: #dc2626;
            border: 1px solid #fca5a5;
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 11px;
            font-weight: 600;
        """)
        self.error_banner.hide()
        body_layout.addWidget(self.error_banner)

        # Password Field
        pwd_box = QFrame()
        pwd_box.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 12px 14px;
            }
        """)
        pwd_layout = QVBoxLayout(pwd_box)
        pwd_layout.setContentsMargins(0, 0, 0, 0)
        pwd_layout.setSpacing(8)

        pwd_hdr_row = QHBoxLayout()
        lbl_pwd = QLabel("NEW PASSWORD *")
        lbl_pwd.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        pwd_hdr_row.addWidget(lbl_pwd)
        pwd_hdr_row.addStretch()

        btn_gen = QPushButton("⚡ Auto Generate")
        btn_gen.setCursor(Qt.PointingHandCursor)
        btn_gen.setFixedHeight(24)
        btn_gen.setStyleSheet("""
            QPushButton {
                background-color: #eff6ff;
                color: #2563eb;
                border: 1px solid #bfdbfe;
                border-radius: 12px;
                font-size: 10px;
                font-weight: 700;
                padding: 0 10px;
            }
            QPushButton:hover { background-color: #2563eb; color: #ffffff; }
        """)
        btn_gen.clicked.connect(self._auto_generate_password)
        pwd_hdr_row.addWidget(btn_gen)
        pwd_layout.addLayout(pwd_hdr_row)

        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.Password)
        self.txt_password.setPlaceholderText("Minimum 8 characters with upper, lower, and digit")
        self.txt_password.setFixedHeight(36)
        self.txt_password.setStyleSheet("""
            QLineEdit {
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background-color: #ffffff;
                font-size: 13px;
                color: #0f172a;
            }
            QLineEdit:focus { border-color: #2563eb; }
        """)
        self.txt_password.textChanged.connect(self._check_password_strength)
        pwd_layout.addWidget(self.txt_password)

        self.lbl_strength = QLabel("Password strength: Enter password")
        self.lbl_strength.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 500;")
        pwd_layout.addWidget(self.lbl_strength)

        body_layout.addWidget(pwd_box)

        note_lbl = QLabel("Note: Changing password will unlock the account and require the user to change password on next login.")
        note_lbl.setWordWrap(True)
        note_lbl.setStyleSheet("font-size: 11px; color: #64748b; font-style: italic;")
        body_layout.addWidget(note_lbl)

        body_layout.addStretch()
        container_layout.addWidget(body_widget, stretch=1)

        # ── 3. Sticky Footer ──
        footer_card = QFrame()
        footer_card.setObjectName("dialogFooterCard")
        footer_card.setStyleSheet("""
            QFrame#dialogFooterCard {
                background-color: #f8fafc;
                border-top: 1px solid #e2e8f0;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
                padding: 10px 18px;
            }
        """)
        footer_layout = QHBoxLayout(footer_card)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(10)
        footer_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(34)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                padding: 0 14px;
            }
            QPushButton:hover { background-color: #f1f5f9; color: #0f172a; }
        """)
        btn_cancel.clicked.connect(self.reject)
        footer_layout.addWidget(btn_cancel)

        btn_save = QPushButton("Save New Password")
        btn_save.setIcon(IconManager.get_pixmap("check", color="#ffffff", size=14))
        btn_save.setFixedHeight(34)
        btn_save.setDefault(True)
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 800;
                padding: 0 16px;
            }
            QPushButton:hover { background-color: #1d4ed8; }
        """)
        btn_save.clicked.connect(self._on_save)
        footer_layout.addWidget(btn_save)

        container_layout.addWidget(footer_card)

    def _auto_generate_password(self):
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        pwd = "".join(secrets.choice(alphabet) for _ in range(12))
        self.txt_password.setEchoMode(QLineEdit.Normal)
        self.txt_password.setText(pwd)

    def _check_password_strength(self, pwd: str):
        if not pwd:
            self.lbl_strength.setText("Password strength: Enter password")
            self.lbl_strength.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 500;")
            return
        length = len(pwd) >= 8
        has_upper = any(c.isupper() for c in pwd)
        has_lower = any(c.islower() for c in pwd)
        has_digit = any(c.isdigit() for c in pwd)
        score = sum([length, has_upper, has_lower, has_digit])

        if score == 4:
            self.lbl_strength.setText("● Strong password (Meets all security policies)")
            self.lbl_strength.setStyleSheet("font-size: 11px; color: #059669; font-weight: 700;")
        elif score >= 2:
            self.lbl_strength.setText("● Fair password (Add uppercase or digits)")
            self.lbl_strength.setStyleSheet("font-size: 11px; color: #d97706; font-weight: 700;")
        else:
            self.lbl_strength.setText("● Weak password (Too short or simple)")
            self.lbl_strength.setStyleSheet("font-size: 11px; color: #dc2626; font-weight: 700;")

    def _on_header_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _on_header_mouse_move(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def _on_save(self):
        pwd = self.txt_password.text().strip()
        if not pwd:
            self.error_banner.setText("Password cannot be empty.")
            self.error_banner.show()
            return
        try:
            self._user_service.reset_password(self._user.id, pwd, actor=self._actor)
            self.accept()
        except RetailFlowError as e:
            self.error_banner.setText(str(e))
            self.error_banner.show()
        except Exception as e:
            self.error_banner.setText(str(e))
            self.error_banner.show()
