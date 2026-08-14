"""
RetailFlow POS - User & Staff Management Page
Workstation for managing staff accounts, security roles, access credentials,
account lockouts, and password resets.
"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from application.dto.user_dto import UserResponseDTO
from application.services.user_service import UserService
from infrastructure.database.models.auth import User
from presentation.dialogs.password_reset_dialog import PasswordResetDialog
from presentation.dialogs.user_form_dialog import UserFormDialog
from presentation.styles.icons import IconManager
from presentation.widgets.metric_card import MetricCardWidget
from presentation.widgets.toast_notification import ToastNotification


class UsersPage(QWidget):
    """Staff accounts and role permissions management workstation."""

    def __init__(
        self,
        current_user: User,
        user_service: UserService,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._user = current_user
        self._user_service = user_service
        self._users_list: list[UserResponseDTO] = []
        self._active_chip = "all"

        self._init_ui()
        self.load_users()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Toast notification overlay
        self._toast = ToastNotification(self)

        # ── 1. Header Title & Top Actions ──
        hdr_row = QHBoxLayout()
        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)

        title_lbl = QLabel("User & Staff Management")
        title_lbl.setStyleSheet("font-size: 22px; font-weight: 800; color: #0f172a; letter-spacing: -0.4px;")
        header_layout.addWidget(title_lbl)

        subtitle_lbl = QLabel("Manage staff access credentials, assign role permissions, and track active accounts.")
        subtitle_lbl.setStyleSheet("font-size: 13px; color: #64748b; font-weight: 500;")
        header_layout.addWidget(subtitle_lbl)

        hdr_row.addLayout(header_layout)
        hdr_row.addStretch()

        btn_refresh = QPushButton(" Refresh")
        btn_refresh.setIcon(IconManager.get_pixmap("clock", color="#475569", size=13))
        btn_refresh.setFixedHeight(36)
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 700;
                padding: 0px 14px;
            }
            QPushButton:hover {
                background-color: #f8fafc;
                border-color: #94a3b8;
                color: #2563eb;
            }
        """)
        btn_refresh.clicked.connect(self.load_users)
        hdr_row.addWidget(btn_refresh)

        self.btn_add_user = QPushButton(" + Add New User")
        self.btn_add_user.setIcon(IconManager.get_pixmap("plus", color="#ffffff", size=14))
        self.btn_add_user.setFixedHeight(36)
        self.btn_add_user.setCursor(Qt.PointingHandCursor)
        self.btn_add_user.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 800;
                padding: 0px 16px;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        self.btn_add_user.clicked.connect(self._open_add_dialog)
        hdr_row.addWidget(self.btn_add_user)

        main_layout.addLayout(hdr_row)

        # ── 2. Summary Metric Cards Grid ──
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(12)

        self.card_total = MetricCardWidget(
            title="TOTAL STAFF",
            icon_name="users",
            accent_color="#2563eb",
            badge_bg="#eff6ff",
        )
        self.card_active = MetricCardWidget(
            title="ACTIVE ACCOUNTS",
            icon_name="check",
            accent_color="#059669",
            badge_bg="#ecfdf5",
        )
        self.card_locked = MetricCardWidget(
            title="LOCKED / INACTIVE",
            icon_name="alert_triangle",
            accent_color="#d97706",
            badge_bg="#fffbeb",
        )
        self.card_roles = MetricCardWidget(
            title="ROLES ASSIGNED",
            icon_name="shield",
            accent_color="#7c3aed",
            badge_bg="#f3e8ff",
        )

        for card in [self.card_total, self.card_active, self.card_locked, self.card_roles]:
            metrics_layout.addWidget(card)

        main_layout.addLayout(metrics_layout)

        # ── 3. Search & Filter Toolbar ──
        toolbar_card = QFrame()
        toolbar_card.setObjectName("filterToolbar")
        toolbar_card.setStyleSheet("""
            QFrame#filterToolbar {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 10px 14px;
            }
        """)
        v_toolbar = QVBoxLayout(toolbar_card)
        v_toolbar.setContentsMargins(0, 0, 0, 0)
        v_toolbar.setSpacing(8)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(10)

        self.txt_search = QLineEdit()
        self.txt_search.addAction(IconManager.get_icon("search", color="#64748b", size=16), QLineEdit.LeadingPosition)
        self.txt_search.setPlaceholderText("Search by staff name, username, or email...")
        self.txt_search.setFixedHeight(36)
        self.txt_search.setStyleSheet("""
            QLineEdit {
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background-color: #ffffff;
                font-size: 13px;
                color: #0f172a;
            }
            QLineEdit:focus { border-color: #2563eb; }
        """)
        self.txt_search.textChanged.connect(self.load_users)
        toolbar_layout.addWidget(self.txt_search, stretch=3)

        self.cmb_role = QComboBox()
        self.cmb_role.addItem("All Roles", None)
        self.cmb_role.setFixedHeight(36)
        self.cmb_role.setStyleSheet("""
            QComboBox {
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background-color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                color: #0f172a;
            }
            QComboBox:focus { border-color: #2563eb; }
        """)
        self.cmb_role.currentIndexChanged.connect(self.load_users)
        toolbar_layout.addWidget(self.cmb_role, stretch=1)

        self.cmb_status = QComboBox()
        self.cmb_status.addItem("All Statuses", None)
        self.cmb_status.addItem("Active", "active")
        self.cmb_status.addItem("Inactive", "inactive")
        self.cmb_status.addItem("Locked", "locked")
        self.cmb_status.setFixedHeight(36)
        self.cmb_status.setStyleSheet("""
            QComboBox {
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background-color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                color: #0f172a;
            }
            QComboBox:focus { border-color: #2563eb; }
        """)
        self.cmb_status.currentIndexChanged.connect(self._on_status_combo_changed)
        toolbar_layout.addWidget(self.cmb_status, stretch=1)

        v_toolbar.addLayout(toolbar_layout)

        # Fast Filter Chips Row
        chips_layout = QHBoxLayout()
        chips_layout.setSpacing(6)

        self.chip_all = QPushButton("All Staff")
        self.chip_admins = QPushButton("Admins")
        self.chip_cashiers = QPushButton("Cashiers")
        self.chip_managers = QPushButton("Managers")
        self.chip_locked = QPushButton("Locked Accounts")

        self.user_chips = [
            (self.chip_all, "all", None, None),
            (self.chip_admins, "administrator", "administrator", None),
            (self.chip_cashiers, "cashier", "cashier", None),
            (self.chip_managers, "manager", "manager", None),
            (self.chip_locked, "locked", None, "locked"),
        ]

        for chip_btn, mode, r_code, s_code in self.user_chips:
            chip_btn.setFixedHeight(26)
            chip_btn.setCursor(Qt.PointingHandCursor)
            chip_btn.clicked.connect(lambda chk, m=mode, r=r_code, s=s_code: self._on_chip_clicked(m, r, s))
            chips_layout.addWidget(chip_btn)

        chips_layout.addStretch()
        v_toolbar.addLayout(chips_layout)
        self._update_chip_styles()

        main_layout.addWidget(toolbar_card)

        # ── 4. Staff Table Grid ──
        self.tbl_users = QTableWidget()
        self.tbl_users.setColumnCount(7)
        self.tbl_users.setHorizontalHeaderLabels([
            "AVATAR",
            "STAFF MEMBER",
            "ROLE",
            "CONTACT INFO",
            "STATUS",
            "LAST LOGIN",
            "ACTIONS",
        ])

        self.tbl_users.verticalHeader().setVisible(False)
        self.tbl_users.setAlternatingRowColors(True)
        self.tbl_users.setShowGrid(False)
        self.tbl_users.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                font-size: 12px;
                color: #0f172a;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #64748b;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.8px;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                padding: 8px 10px;
            }
            QTableWidget::item {
                padding: 4px 8px;
                border-bottom: 1px solid #f1f5f9;
            }
        """)

        header = self.tbl_users.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Fixed)

        self.tbl_users.setColumnWidth(0, 50)
        self.tbl_users.setColumnWidth(4, 110)
        self.tbl_users.setColumnWidth(6, 175)

        self.tbl_users.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_users.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_users.doubleClicked.connect(self._on_row_double_clicked)
        main_layout.addWidget(self.tbl_users, stretch=1)

        self._populate_roles_combo()

    def _populate_roles_combo(self):
        try:
            roles = self._user_service.get_roles(self._user)
            self.cmb_role.blockSignals(True)
            self.cmb_role.clear()
            self.cmb_role.addItem("All Roles", None)
            for r in roles:
                self.cmb_role.addItem(r.name, r.code)
            self.cmb_role.blockSignals(False)
        except Exception:
            pass

    def _on_chip_clicked(self, mode: str, role_code: Optional[str], status_code: Optional[str]):
        self._active_chip = mode
        self._update_chip_styles()

        self.cmb_role.blockSignals(True)
        if role_code:
            idx = self.cmb_role.findData(role_code)
            if idx >= 0:
                self.cmb_role.setCurrentIndex(idx)
        else:
            self.cmb_role.setCurrentIndex(0)
        self.cmb_role.blockSignals(False)

        self.cmb_status.blockSignals(True)
        if status_code:
            idx_s = self.cmb_status.findData(status_code)
            if idx_s >= 0:
                self.cmb_status.setCurrentIndex(idx_s)
        else:
            self.cmb_status.setCurrentIndex(0)
        self.cmb_status.blockSignals(False)

        self.load_users()

    def _on_status_combo_changed(self):
        st = self.cmb_status.currentData()
        if st == "locked":
            self._active_chip = "locked"
        else:
            self._active_chip = "all"
        self._update_chip_styles()
        self.load_users()

    def _update_chip_styles(self):
        for chip_btn, mode, _, _ in self.user_chips:
            is_active = self._active_chip == mode
            if is_active:
                chip_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2563eb;
                        color: #ffffff;
                        border: none;
                        border-radius: 13px;
                        font-size: 11px;
                        font-weight: 700;
                        padding: 0 12px;
                    }
                """)
            else:
                chip_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f1f5f9;
                        color: #475569;
                        border: 1px solid #e2e8f0;
                        border-radius: 13px;
                        font-size: 11px;
                        font-weight: 600;
                        padding: 0 12px;
                    }
                    QPushButton:hover { background-color: #e2e8f0; color: #0f172a; }
                """)

    def load_users(self):
        """Fetch staff users matching search and role filters."""
        try:
            keyword = self.txt_search.text().strip() or None
            role_code = self.cmb_role.currentData()
            status = self.cmb_status.currentData()

            users = self._user_service.get_users(
                keyword=keyword,
                role_code=role_code,
                status=status,
                actor=self._user,
            )
            self._users_list = users

            # Update Metric Cards
            metrics = self._user_service.get_metrics(self._user)
            self.card_total.update_value(str(metrics.total_users))
            self.card_total.set_caption("● System accounts")

            self.card_active.update_value(str(metrics.active_users))
            self.card_active.set_caption("● Full store access")

            self.card_locked.update_value(str(metrics.locked_users))
            self.card_locked.set_caption("● Requires unlock" if metrics.locked_users > 0 else "● No lockouts")

            self.card_roles.update_value(str(metrics.roles_count))
            self.card_roles.set_caption("● Configured roles")

            # Render Table
            self.tbl_users.setRowCount(len(users))
            dark_color = QColor("#0f172a")

            for row, u in enumerate(users):
                self.tbl_users.setRowHeight(row, 48)

                # Col 0: Avatar Circle
                initial = u.full_name[:1].upper() if u.full_name else u.username[:1].upper()
                avatar_lbl = QLabel(initial)
                avatar_lbl.setAlignment(Qt.AlignCenter)
                avatar_lbl.setFixedSize(28, 28)
                avatar_lbl.setStyleSheet("""
                    background-color: #2563eb;
                    color: #ffffff;
                    border-radius: 14px;
                    font-size: 12px;
                    font-weight: 800;
                """)
                av_container = QWidget()
                av_l = QHBoxLayout(av_container)
                av_l.setContentsMargins(0, 0, 0, 0)
                av_l.setAlignment(Qt.AlignCenter)
                av_l.addWidget(avatar_lbl)
                self.tbl_users.setCellWidget(row, 0, av_container)

                # Col 1: Staff Member
                name_w = QWidget()
                name_l = QVBoxLayout(name_w)
                name_l.setContentsMargins(4, 2, 4, 2)
                name_l.setSpacing(1)
                full_lbl = QLabel(u.full_name)
                full_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #0f172a;")
                user_lbl = QLabel(f"@{u.username}")
                user_lbl.setStyleSheet("font-size: 11px; font-weight: 500; color: #64748b;")
                name_l.addWidget(full_lbl)
                name_l.addWidget(user_lbl)
                self.tbl_users.setCellWidget(row, 1, name_w)

                # Col 2: Role Badge
                role_lbl = QLabel(u.primary_role.upper())
                role_lbl.setAlignment(Qt.AlignCenter)
                r_lower = u.primary_role.lower()
                if "admin" in r_lower:
                    r_style = "color: #7c3aed; background-color: #f3e8ff; border: 1px solid #e9d5ff;"
                elif "manager" in r_lower:
                    r_style = "color: #0d9488; background-color: #ccfbf1; border: 1px solid #99f6e4;"
                elif "cashier" in r_lower:
                    r_style = "color: #2563eb; background-color: #eff6ff; border: 1px solid #bfdbfe;"
                else:
                    r_style = "color: #475569; background-color: #f1f5f9; border: 1px solid #e2e8f0;"
                role_lbl.setStyleSheet(f"{r_style} font-size: 10px; font-weight: 800; border-radius: 6px; padding: 2px 8px;")
                self.tbl_users.setCellWidget(row, 2, role_lbl)

                # Col 3: Contact Info
                contact_w = QWidget()
                contact_l = QVBoxLayout(contact_w)
                contact_l.setContentsMargins(4, 2, 4, 2)
                contact_l.setSpacing(1)
                email_lbl = QLabel(u.email or "No email registered")
                email_lbl.setStyleSheet("font-size: 11px; color: #0f172a; font-weight: 500;")
                phone_lbl = QLabel(u.phone or "No phone")
                phone_lbl.setStyleSheet("font-size: 10px; color: #64748b;")
                contact_l.addWidget(email_lbl)
                contact_l.addWidget(phone_lbl)
                self.tbl_users.setCellWidget(row, 3, contact_w)

                # Col 4: Status Badge
                status_lbl = QLabel()
                status_lbl.setAlignment(Qt.AlignCenter)
                if u.is_locked:
                    status_lbl.setText("● Locked")
                    status_lbl.setStyleSheet("color: #d97706; font-size: 10px; font-weight: 800; background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 2px 8px;")
                elif not u.is_active:
                    status_lbl.setText("● Inactive")
                    status_lbl.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 800; background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 8px; padding: 2px 8px;")
                else:
                    status_lbl.setText("● Active")
                    status_lbl.setStyleSheet("color: #047857; font-size: 10px; font-weight: 800; background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px; padding: 2px 8px;")
                self.tbl_users.setCellWidget(row, 4, status_lbl)

                # Col 5: Last Login
                login_item = QTableWidgetItem(u.last_login_at or "Never logged in")
                login_item.setForeground(QColor("#64748b"))
                login_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.tbl_users.setItem(row, 5, login_item)

                # Col 6: Actions
                act_w = QWidget()
                act_l = QHBoxLayout(act_w)
                act_l.setContentsMargins(4, 0, 4, 0)
                act_l.setSpacing(4)

                # Edit
                btn_edit = QPushButton()
                btn_edit.setIcon(IconManager.get_pixmap("edit", color="#2563eb", size=13))
                btn_edit.setFixedSize(28, 28)
                btn_edit.setToolTip("Edit Profile & Roles")
                btn_edit.setCursor(Qt.PointingHandCursor)
                btn_edit.setStyleSheet(self._action_btn_style("#eff6ff", "#bfdbfe"))
                btn_edit.clicked.connect(lambda chk, usr=u: self._open_edit_dialog(usr))
                act_l.addWidget(btn_edit)

                # Reset Password
                btn_pwd = QPushButton()
                btn_pwd.setIcon(IconManager.get_pixmap("lock", color="#7c3aed", size=13))
                btn_pwd.setFixedSize(28, 28)
                btn_pwd.setToolTip("Reset Password")
                btn_pwd.setCursor(Qt.PointingHandCursor)
                btn_pwd.setStyleSheet(self._action_btn_style("#f3e8ff", "#e9d5ff"))
                btn_pwd.clicked.connect(lambda chk, usr=u: self._open_reset_dialog(usr))
                act_l.addWidget(btn_pwd)

                # Lock / Unlock
                btn_lock = QPushButton()
                lock_ico = "unlock" if u.is_locked else "lock"
                lock_color = "#059669" if u.is_locked else "#d97706"
                btn_lock.setIcon(IconManager.get_pixmap(lock_ico, color=lock_color, size=13))
                btn_lock.setFixedSize(28, 28)
                btn_lock.setToolTip("Unlock Account" if u.is_locked else "Lock Account")
                btn_lock.setCursor(Qt.PointingHandCursor)
                btn_lock.setStyleSheet(self._action_btn_style("#fffbeb" if not u.is_locked else "#ecfdf5", "#fde68a" if not u.is_locked else "#a7f3d0"))
                btn_lock.clicked.connect(lambda chk, usr=u: self._toggle_lock(usr))
                act_l.addWidget(btn_lock)

                self.tbl_users.setCellWidget(row, 6, act_w)

        except Exception as e:
            import logging
            logging.getLogger("retailflow.users").exception("Failed to load users", exc_info=e)

    def _action_btn_style(self, bg: str, border: str) -> str:
        return f"""
            QPushButton {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 6px;
            }}
            QPushButton:hover {{
                border-color: #2563eb;
            }}
        """

    def _on_row_double_clicked(self, index):
        row = index.row()
        if 0 <= row < len(self._users_list):
            self._open_edit_dialog(self._users_list[row])

    def _open_add_dialog(self):
        dlg = UserFormDialog(self._user_service, self._user, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._toast.show_toast("Staff user created successfully!")
            self.load_users()

    def _open_edit_dialog(self, target_user: UserResponseDTO):
        dlg = UserFormDialog(self._user_service, self._user, user_data=target_user, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._toast.show_toast(f"Updated profile for '{target_user.full_name}'")
            self.load_users()

    def _open_reset_dialog(self, target_user: UserResponseDTO):
        dlg = PasswordResetDialog(self._user_service, target_user, self._user, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._toast.show_toast(f"Password reset for @{target_user.username}")
            self.load_users()

    def _toggle_lock(self, target_user: UserResponseDTO):
        action_name = "Unlock" if target_user.is_locked else "Lock"
        reply = QMessageBox.question(
            self,
            f"Confirm {action_name}",
            f"Are you sure you want to {action_name.lower()} account @{target_user.username}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                new_state = self._user_service.toggle_lock(target_user.id, not target_user.is_locked, actor=self._user)
                msg = f"Account @{target_user.username} is now {'Locked' if new_state else 'Unlocked'}."
                self._toast.show_toast(msg)
                self.load_users()
            except Exception as e:
                self._toast.show_toast(str(e), is_error=True)
