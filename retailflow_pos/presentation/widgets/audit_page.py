"""
RetailFlow POS - Audit Logs & Activity Trail Page
Workstation for monitoring immutable system activity, inspecting security events,
filtering changes across modules, and comparing before/after state diffs.
"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from application.dto.audit_dto import AuditFilterDTO, AuditLogResponseDTO
from application.services.audit_service import AuditService
from infrastructure.database.models.auth import User
from presentation.dialogs.audit_details_dialog import AuditDetailsDialog
from presentation.styles.icons import IconManager
from presentation.widgets.metric_card import MetricCardWidget


class AuditPage(QWidget):
    """Audit logs and activity trail workstation."""

    def __init__(
        self,
        current_user: User,
        audit_service: AuditService,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._user = current_user
        self._audit_service = audit_service
        self._logs_list: list[AuditLogResponseDTO] = []
        self._page = 1
        self._page_size = 20
        self._total = 0
        self._active_chip = "all"

        self._init_ui()
        self.load_audit_logs()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # ── 1. Header Title & Actions ──
        hdr_row = QHBoxLayout()
        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)

        title_lbl = QLabel("Audit Logs & Security Activity Trail")
        title_lbl.setStyleSheet("font-size: 22px; font-weight: 800; color: #0f172a; letter-spacing: -0.4px;")
        header_layout.addWidget(title_lbl)

        subtitle_lbl = QLabel("Inspect immutable system audit logs, track staff actions, and audit data modifications.")
        subtitle_lbl.setStyleSheet("font-size: 13px; color: #64748b; font-weight: 500;")
        header_layout.addWidget(subtitle_lbl)

        hdr_row.addLayout(header_layout)
        hdr_row.addStretch()

        btn_refresh = QPushButton(" Refresh Data")
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
        btn_refresh.clicked.connect(self.load_audit_logs)
        hdr_row.addWidget(btn_refresh)

        main_layout.addLayout(hdr_row)

        # ── 2. Summary Metric Cards Grid ──
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(12)

        self.card_total = MetricCardWidget(
            title="TOTAL LOGS",
            icon_name="audit",
            accent_color="#2563eb",
            badge_bg="#eff6ff",
        )
        self.card_auth = MetricCardWidget(
            title="AUTH & SECURITY",
            icon_name="lock",
            accent_color="#7c3aed",
            badge_bg="#f3e8ff",
        )
        self.card_inv = MetricCardWidget(
            title="INVENTORY & CATALOG",
            icon_name="products",
            accent_color="#d97706",
            badge_bg="#fffbeb",
        )
        self.card_users = MetricCardWidget(
            title="USER MANAGEMENT",
            icon_name="users",
            accent_color="#0d9488",
            badge_bg="#ccfbf1",
        )

        for card in [self.card_total, self.card_auth, self.card_inv, self.card_users]:
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
        self.txt_search.setPlaceholderText("Search by user, action, change description, or IP address...")
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
        self.txt_search.textChanged.connect(self._on_search_changed)
        toolbar_layout.addWidget(self.txt_search, stretch=3)

        self.cmb_module = QComboBox()
        self.cmb_module.addItem("All Modules", None)
        self.cmb_module.setFixedHeight(36)
        self.cmb_module.setStyleSheet("""
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
        self.cmb_module.currentIndexChanged.connect(self._on_filter_changed)
        toolbar_layout.addWidget(self.cmb_module, stretch=1)

        self.cmb_action = QComboBox()
        self.cmb_action.addItem("All Actions", None)
        self.cmb_action.setFixedHeight(36)
        self.cmb_action.setStyleSheet("""
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
        self.cmb_action.currentIndexChanged.connect(self._on_filter_changed)
        toolbar_layout.addWidget(self.cmb_action, stretch=1)

        v_toolbar.addLayout(toolbar_layout)

        # Fast Filter Chips Row
        chips_layout = QHBoxLayout()
        chips_layout.setSpacing(6)

        self.chip_all = QPushButton("All Logs")
        self.chip_auth = QPushButton("Auth & Security")
        self.chip_inv = QPushButton("Inventory & Catalog")
        self.chip_users = QPushButton("User Management")
        self.chip_sales = QPushButton("Sales Activity")

        self.audit_chips = [
            (self.chip_all, "all", None),
            (self.chip_auth, "auth", "auth"),
            (self.chip_inv, "inventory", "inventory"),
            (self.chip_users, "users", "users"),
            (self.chip_sales, "sales", "sales"),
        ]

        for chip_btn, mode, mod_name in self.audit_chips:
            chip_btn.setFixedHeight(26)
            chip_btn.setCursor(Qt.PointingHandCursor)
            chip_btn.clicked.connect(lambda chk, m=mode, mn=mod_name: self._on_chip_clicked(m, mn))
            chips_layout.addWidget(chip_btn)

        chips_layout.addStretch()
        v_toolbar.addLayout(chips_layout)
        self._update_chip_styles()

        main_layout.addWidget(toolbar_card)

        # ── 4. Audit Table Feed ──
        self.tbl_audit = QTableWidget()
        self.tbl_audit.setColumnCount(7)
        self.tbl_audit.setHorizontalHeaderLabels([
            "TIMESTAMP",
            "ACTOR USER",
            "MODULE",
            "ACTION",
            "DETAILS / CHANGE SUMMARY",
            "IP ADDRESS",
            "INSPECT",
        ])

        self.tbl_audit.verticalHeader().setVisible(False)
        self.tbl_audit.setAlternatingRowColors(True)
        self.tbl_audit.setShowGrid(False)
        self.tbl_audit.setStyleSheet("""
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

        header = self.tbl_audit.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Fixed)

        self.tbl_audit.setColumnWidth(6, 110)

        self.tbl_audit.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_audit.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_audit.doubleClicked.connect(self._on_row_double_clicked)
        main_layout.addWidget(self.tbl_audit, stretch=1)

        # ── 5. Pagination Footer ──
        footer_layout = QHBoxLayout()
        self.lbl_page_info = QLabel("Showing 0–0 of 0 logs")
        self.lbl_page_info.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 600;")
        footer_layout.addWidget(self.lbl_page_info)
        footer_layout.addStretch()

        self.btn_prev = QPushButton("‹ Previous")
        self.btn_prev.setFixedHeight(30)
        self.btn_prev.setCursor(Qt.PointingHandCursor)
        self.btn_prev.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                padding: 0 12px;
            }
            QPushButton:hover { background-color: #f1f5f9; color: #0f172a; }
            QPushButton:disabled { color: #cbd5e1; border-color: #e2e8f0; }
        """)
        self.btn_prev.clicked.connect(self._prev_page)
        footer_layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton("Next ›")
        self.btn_next.setFixedHeight(30)
        self.btn_next.setCursor(Qt.PointingHandCursor)
        self.btn_next.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                padding: 0 12px;
            }
            QPushButton:hover { background-color: #f1f5f9; color: #0f172a; }
            QPushButton:disabled { color: #cbd5e1; border-color: #e2e8f0; }
        """)
        self.btn_next.clicked.connect(self._next_page)
        footer_layout.addWidget(self.btn_next)

        main_layout.addLayout(footer_layout)

        self._populate_filter_dropdowns()

    def _populate_filter_dropdowns(self):
        try:
            modules = self._audit_service.get_modules(self._user)
            self.cmb_module.blockSignals(True)
            self.cmb_module.clear()
            self.cmb_module.addItem("All Modules", None)
            for m in modules:
                self.cmb_module.addItem(m.capitalize(), m)
            self.cmb_module.blockSignals(False)

            actions = self._audit_service.get_actions(self._user)
            self.cmb_action.blockSignals(True)
            self.cmb_action.clear()
            self.cmb_action.addItem("All Actions", None)
            for a in actions:
                self.cmb_action.addItem(a, a)
            self.cmb_action.blockSignals(False)
        except Exception:
            pass

    def _on_search_changed(self):
        self._page = 1
        self.load_audit_logs()

    def _on_filter_changed(self):
        self._page = 1
        self.load_audit_logs()

    def _on_chip_clicked(self, mode: str, module_name: Optional[str]):
        self._active_chip = mode
        self._update_chip_styles()

        self.cmb_module.blockSignals(True)
        if module_name:
            idx = self.cmb_module.findData(module_name)
            if idx >= 0:
                self.cmb_module.setCurrentIndex(idx)
        else:
            self.cmb_module.setCurrentIndex(0)
        self.cmb_module.blockSignals(False)

        self._page = 1
        self.load_audit_logs()

    def _update_chip_styles(self):
        for chip_btn, mode, _ in self.audit_chips:
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

    def _prev_page(self):
        if self._page > 1:
            self._page -= 1
            self.load_audit_logs()

    def _next_page(self):
        if self._page * self._page_size < self._total:
            self._page += 1
            self.load_audit_logs()

    def load_audit_logs(self):
        """Fetch audit logs matching filters and render feed."""
        try:
            keyword = self.txt_search.text().strip() or None
            module = self.cmb_module.currentData()
            action = self.cmb_action.currentData()

            filters = AuditFilterDTO(
                keyword=keyword,
                module=module,
                action=action,
                page=self._page,
                page_size=self._page_size,
            )

            result = self._audit_service.search(filters, self._user)
            self._logs_list = result.items
            self._total = result.total

            # Update Metrics
            metrics = self._audit_service.get_metrics(self._user)
            self.card_total.update_value(str(metrics.total_logs))
            self.card_total.set_caption("● Immutable audit events")

            self.card_auth.update_value(str(metrics.auth_logs))
            self.card_auth.set_caption("● Logins & sessions")

            self.card_inv.update_value(str(metrics.inventory_logs))
            self.card_inv.set_caption("● Catalog & stock diffs")

            self.card_users.update_value(str(metrics.user_logs))
            self.card_users.set_caption("● Role & credential changes")

            # Render Table
            self.tbl_audit.setRowCount(len(result.items))
            dark_color = QColor("#0f172a")

            for row, log in enumerate(result.items):
                self.tbl_audit.setRowHeight(row, 44)

                # Col 0: Timestamp
                time_item = QTableWidgetItem(log.formatted_time)
                time_item.setFont(QFont("Consolas", 10))
                time_item.setForeground(QColor("#64748b"))
                time_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.tbl_audit.setItem(row, 0, time_item)

                # Col 1: Actor User
                user_item = QTableWidgetItem(f"@{log.username}")
                user_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                user_item.setForeground(dark_color)
                user_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.tbl_audit.setItem(row, 1, user_item)

                # Col 2: Module Badge
                mod_lbl = QLabel(log.module.upper())
                mod_lbl.setAlignment(Qt.AlignCenter)
                m_lower = log.module.lower()
                if "auth" in m_lower:
                    m_style = "color: #7c3aed; background-color: #f3e8ff; border: 1px solid #e9d5ff;"
                elif "inv" in m_lower or "prod" in m_lower:
                    m_style = "color: #d97706; background-color: #fffbeb; border: 1px solid #fde68a;"
                elif "user" in m_lower:
                    m_style = "color: #0d9488; background-color: #ccfbf1; border: 1px solid #99f6e4;"
                elif "sale" in m_lower:
                    m_style = "color: #059669; background-color: #ecfdf5; border: 1px solid #a7f3d0;"
                else:
                    m_style = "color: #2563eb; background-color: #eff6ff; border: 1px solid #bfdbfe;"
                mod_lbl.setStyleSheet(f"{m_style} font-size: 9px; font-weight: 800; border-radius: 6px; padding: 2px 8px;")
                self.tbl_audit.setCellWidget(row, 2, mod_lbl)

                # Col 3: Action Pill
                action_item = QTableWidgetItem(log.action)
                action_item.setFont(QFont("Consolas", 9, QFont.Bold))
                action_item.setForeground(dark_color)
                action_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.tbl_audit.setItem(row, 3, action_item)

                # Col 4: Details / Change Summary
                summary = log.new_value or log.reason or "State updated"
                detail_item = QTableWidgetItem(summary)
                detail_item.setForeground(QColor("#475569"))
                detail_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.tbl_audit.setItem(row, 4, detail_item)

                # Col 5: IP Address
                ip_item = QTableWidgetItem(log.ip_address or "127.0.0.1")
                ip_item.setFont(QFont("Consolas", 9))
                ip_item.setForeground(QColor("#64748b"))
                ip_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                self.tbl_audit.setItem(row, 5, ip_item)

                # Col 6: Action Button (Inspect)
                btn_inspect = QPushButton(" Inspect")
                btn_inspect.setIcon(IconManager.get_pixmap("search", color="#2563eb", size=12))
                btn_inspect.setCursor(Qt.PointingHandCursor)
                btn_inspect.setFixedHeight(28)
                btn_inspect.setStyleSheet("""
                    QPushButton {
                        background-color: #eff6ff;
                        color: #2563eb;
                        border: 1px solid #bfdbfe;
                        border-radius: 6px;
                        font-size: 11px;
                        font-weight: 700;
                        padding: 0 10px;
                    }
                    QPushButton:hover {
                        background-color: #2563eb;
                        color: #ffffff;
                    }
                """)
                btn_inspect.clicked.connect(lambda chk, lg=log: self._open_details_dialog(lg))
                self.tbl_audit.setCellWidget(row, 6, btn_inspect)

            # Update Pagination Footer
            start_num = (result.page - 1) * result.page_size + 1 if result.total > 0 else 0
            end_num = min(result.page * result.page_size, result.total)
            self.lbl_page_info.setText(f"Showing {start_num}–{end_num} of {result.total} audit logs")
            self.btn_prev.setEnabled(result.has_previous)
            self.btn_next.setEnabled(result.has_next)

        except Exception as e:
            import logging
            logging.getLogger("retailflow.audit").exception("Failed to load audit logs", exc_info=e)

    def _on_row_double_clicked(self, index):
        row = index.row()
        if 0 <= row < len(self._logs_list):
            self._open_details_dialog(self._logs_list[row])

    def _open_details_dialog(self, log_dto: AuditLogResponseDTO):
        dlg = AuditDetailsDialog(log_dto, self)
        dlg.exec()
