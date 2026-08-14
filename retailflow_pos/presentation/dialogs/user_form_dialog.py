"""
RetailFlow POS - User Form Dialog
Frameless modal for creating and updating staff user accounts with role selection,
password strength meters, and auto-generated secure passwords.
"""

import secrets
import string
from typing import Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from application.dto.user_dto import CreateUserDTO, UpdateUserDTO, UserResponseDTO
from application.services.user_service import UserService
from domain.exceptions import RetailFlowError
from infrastructure.database.models.auth import User
from presentation.styles.icons import IconManager


class UserFormDialog(QDialog):
    """Modal dialog for creating or editing staff users."""

    def __init__(
        self,
        user_service: UserService,
        current_actor: User,
        user_data: Optional[UserResponseDTO] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._user_service = user_service
        self._actor = current_actor
        self._user_data = user_data
        self._is_edit = user_data is not None
        self._drag_pos = QPoint()

        self.setWindowTitle("Edit Staff Account" if self._is_edit else "Create Staff Account")
        self.setFixedSize(540, 560 if self._is_edit else 640)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self._init_ui()
        self._load_roles()
        if self._is_edit:
            self._prefill_data()

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

        title_text = f"Edit Staff: @{self._user_data.username}" if self._is_edit else "Create New Staff Account"
        hdr_title = QLabel(title_text)
        hdr_title.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: 800;")
        hdr_text_layout.addWidget(hdr_title)

        hdr_sub = QLabel("Assign permissions, configure access roles, and manage credentials.")
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

        # Row 1: Full Name & Username
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        f_name_col = QVBoxLayout()
        f_name_col.setSpacing(4)
        lbl_name = QLabel("FULL NAME *")
        lbl_name.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_name_col.addWidget(lbl_name)
        self.txt_full_name = QLineEdit()
        self.txt_full_name.setPlaceholderText("e.g. Maria Santos")
        self.txt_full_name.setFixedHeight(36)
        self.txt_full_name.setStyleSheet(self._input_style())
        f_name_col.addWidget(self.txt_full_name)
        row1.addLayout(f_name_col, 1)

        f_user_col = QVBoxLayout()
        f_user_col.setSpacing(4)
        lbl_user = QLabel("USERNAME *" if not self._is_edit else "USERNAME (LOCKED)")
        lbl_user.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_user_col.addWidget(lbl_user)
        self.txt_username = QLineEdit()
        self.txt_username.setPlaceholderText("e.g. maria.cashier")
        self.txt_username.setFixedHeight(36)
        self.txt_username.setStyleSheet(self._input_style())
        if self._is_edit:
            self.txt_username.setEnabled(False)
            self.txt_username.setStyleSheet(self._input_style(disabled=True))
        f_user_col.addWidget(self.txt_username)
        row1.addLayout(f_user_col, 1)
        body_layout.addLayout(row1)

        # Row 2: Email & Phone
        row2 = QHBoxLayout()
        row2.setSpacing(12)

        f_email_col = QVBoxLayout()
        f_email_col.setSpacing(4)
        lbl_email = QLabel("EMAIL ADDRESS")
        lbl_email.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_email_col.addWidget(lbl_email)
        self.txt_email = QLineEdit()
        self.txt_email.setPlaceholderText("e.g. maria@retailflow.com")
        self.txt_email.setFixedHeight(36)
        self.txt_email.setStyleSheet(self._input_style())
        f_email_col.addWidget(self.txt_email)
        row2.addLayout(f_email_col, 1)

        f_phone_col = QVBoxLayout()
        f_phone_col.setSpacing(4)
        lbl_phone = QLabel("PHONE NUMBER")
        lbl_phone.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_phone_col.addWidget(lbl_phone)
        self.txt_phone = QLineEdit()
        self.txt_phone.setPlaceholderText("e.g. +63 912 345 6789")
        self.txt_phone.setFixedHeight(36)
        self.txt_phone.setStyleSheet(self._input_style())
        f_phone_col.addWidget(self.txt_phone)
        row2.addLayout(f_phone_col, 1)
        body_layout.addLayout(row2)

        # Row 3: Role & Status
        row3 = QHBoxLayout()
        row3.setSpacing(12)

        f_role_col = QVBoxLayout()
        f_role_col.setSpacing(4)
        lbl_role = QLabel("ROLE ASSIGNMENT *")
        lbl_role.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_role_col.addWidget(lbl_role)
        self.cmb_role = QComboBox()
        self.cmb_role.setFixedHeight(36)
        self.cmb_role.setStyleSheet(self._combo_style())
        f_role_col.addWidget(self.cmb_role)
        row3.addLayout(f_role_col, 1)

        f_status_col = QVBoxLayout()
        f_status_col.setSpacing(4)
        lbl_status = QLabel("ACCOUNT STATUS")
        lbl_status.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_status_col.addWidget(lbl_status)
        self.cmb_status = QComboBox()
        self.cmb_status.addItem("Active", "active")
        self.cmb_status.addItem("Inactive", "inactive")
        self.cmb_status.setFixedHeight(36)
        self.cmb_status.setStyleSheet(self._combo_style())
        f_status_col.addWidget(self.cmb_status)
        row3.addLayout(f_status_col, 1)
        body_layout.addLayout(row3)

        # Password Section (Only for Create User)
        if not self._is_edit:
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
            lbl_pwd = QLabel("INITIAL PASSWORD *")
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
            self.txt_password.setStyleSheet(self._input_style())
            self.txt_password.textChanged.connect(self._check_password_strength)
            pwd_layout.addWidget(self.txt_password)

            # Strength meter
            strength_row = QHBoxLayout()
            self.lbl_strength = QLabel("Password strength: Enter password")
            self.lbl_strength.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 500;")
            strength_row.addWidget(self.lbl_strength)
            pwd_layout.addLayout(strength_row)

            self.chk_must_change = QCheckBox("Require password change upon first login")
            self.chk_must_change.setChecked(True)
            self.chk_must_change.setStyleSheet("font-size: 11px; color: #475569; font-weight: 600;")
            pwd_layout.addWidget(self.chk_must_change)

            body_layout.addWidget(pwd_box)

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

        btn_save = QPushButton("Save Staff Member")
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

    def _load_roles(self):
        self.cmb_role.clear()
        roles = self._user_service.get_roles(self._actor)
        for r in roles:
            self.cmb_role.addItem(r.name, r.code)

    def _prefill_data(self):
        if not self._user_data:
            return
        self.txt_full_name.setText(self._user_data.full_name)
        self.txt_username.setText(self._user_data.username)
        self.txt_email.setText(self._user_data.email or "")
        self.txt_phone.setText(self._user_data.phone or "")

        if self._user_data.role_codes:
            code = self._user_data.role_codes[0]
            idx = self.cmb_role.findData(code)
            if idx >= 0:
                self.cmb_role.setCurrentIndex(idx)

        idx_s = self.cmb_status.findData("active" if self._user_data.is_active else "inactive")
        if idx_s >= 0:
            self.cmb_status.setCurrentIndex(idx_s)

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
        name = self.txt_full_name.text().strip()
        user_name = self.txt_username.text().strip()
        email = self.txt_email.text().strip() or None
        phone = self.txt_phone.text().strip() or None
        role_code = self.cmb_role.currentData()
        status = self.cmb_status.currentData()

        if not name:
            self._show_error("Full name is required.")
            return

        if not self._is_edit and not user_name:
            self._show_error("Username is required.")
            return

        try:
            if self._is_edit:
                dto = UpdateUserDTO(
                    full_name=name,
                    email=email,
                    phone=phone,
                    role_code=role_code,
                    status=status,
                )
                self._user_service.update_user(self._user_data.id, dto, actor=self._actor)
            else:
                pwd = self.txt_password.text()
                if not pwd:
                    self._show_error("Initial password is required.")
                    return
                dto_c = CreateUserDTO(
                    username=user_name,
                    full_name=name,
                    password=pwd,
                    email=email,
                    phone=phone,
                    role_code=role_code,
                    must_change_password=self.chk_must_change.isChecked(),
                    status=status,
                )
                self._user_service.create_user(dto_c, actor=self._actor)

            self.accept()
        except RetailFlowError as e:
            self._show_error(str(e))
        except Exception as e:
            self._show_error(str(e))

    def _show_error(self, msg: str):
        self.error_banner.setText(msg)
        self.error_banner.show()

    def _input_style(self, disabled: bool = False) -> str:
        bg = "#f1f5f9" if disabled else "#ffffff"
        color = "#94a3b8" if disabled else "#0f172a"
        return f"""
            QLineEdit {{
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background-color: {bg};
                font-size: 13px;
                color: {color};
            }}
            QLineEdit:focus {{ border-color: #2563eb; }}
        """

    def _combo_style(self) -> str:
        return """
            QComboBox {
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background-color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                color: #0f172a;
            }
            QComboBox:focus { border-color: #2563eb; }
        """
