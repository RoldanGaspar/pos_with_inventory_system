"""
RetailFlow POS - Customers Directory & Loyalty CRM Page
Workstation for managing customer profiles, reward points, loyalty tiers, and purchase history.
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
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from application.dto.customer_dto import CustomerFilterDTO, CustomerResponseDTO
from application.services.customer_service import CustomerService
from infrastructure.database.models.auth import User
from presentation.dialogs.customer_dialog import CustomerDialog
from presentation.dialogs.points_adjustment_dialog import PointsAdjustmentDialog
from presentation.styles.icons import IconManager
from presentation.widgets.metric_card import MetricCardWidget
from presentation.widgets.toast_notification import ToastNotification


class CustomersPage(QWidget):
    """Customer Relationship Management (CRM) & Loyalty Program workstation."""

    def __init__(
        self,
        current_user: User,
        customer_service: CustomerService,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._user = current_user
        self._customer_service = customer_service
        self._customers_list: list[CustomerResponseDTO] = []
        self._page = 1
        self._page_size = 20
        self._total = 0
        self._active_chip = "all"

        self._init_ui()
        self.load_customers()

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

        title_lbl = QLabel("Customer Directory & Loyalty CRM")
        title_lbl.setStyleSheet("font-size: 22px; font-weight: 800; color: #0f172a; letter-spacing: -0.4px;")
        header_layout.addWidget(title_lbl)

        subtitle_lbl = QLabel("Manage customer records, track purchase history, and reward loyalty points.")
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
        btn_refresh.clicked.connect(self.load_customers)
        hdr_row.addWidget(btn_refresh)

        self.btn_add_customer = QPushButton(" + Add Customer")
        self.btn_add_customer.setIcon(IconManager.get_pixmap("plus", color="#ffffff", size=14))
        self.btn_add_customer.setFixedHeight(36)
        self.btn_add_customer.setCursor(Qt.PointingHandCursor)
        self.btn_add_customer.setStyleSheet("""
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
        self.btn_add_customer.clicked.connect(self._open_add_dialog)
        hdr_row.addWidget(self.btn_add_customer)

        main_layout.addLayout(hdr_row)

        # ── 2. Summary Metric Cards Grid ──
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(12)

        self.card_total = MetricCardWidget(
            title="TOTAL CUSTOMERS",
            icon_name="users",
            accent_color="#2563eb",
            badge_bg="#eff6ff",
        )
        self.card_members = MetricCardWidget(
            title="LOYALTY MEMBERS",
            icon_name="shield",
            accent_color="#7c3aed",
            badge_bg="#f3e8ff",
        )
        self.card_points = MetricCardWidget(
            title="POINTS ISSUED",
            icon_name="tag",
            accent_color="#d97706",
            badge_bg="#fffbeb",
        )
        self.card_spend = MetricCardWidget(
            title="AVG. SPEND / MEMBER",
            icon_name="sales",
            accent_color="#059669",
            badge_bg="#ecfdf5",
        )

        for card in [self.card_total, self.card_members, self.card_points, self.card_spend]:
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
        self.txt_search.setPlaceholderText("Search customer by name, phone #, email, or city...")
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

        self.cmb_tier = QComboBox()
        self.cmb_tier.addItem("All Loyalty Tiers", None)
        self.cmb_tier.addItem("Platinum (1,000+ pts)", "platinum")
        self.cmb_tier.addItem("Gold (500+ pts)", "gold")
        self.cmb_tier.addItem("Silver (100+ pts)", "silver")
        self.cmb_tier.addItem("Bronze (0-99 pts)", "bronze")
        self.cmb_tier.setFixedHeight(36)
        self.cmb_tier.setStyleSheet("""
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
        self.cmb_tier.currentIndexChanged.connect(self._on_filter_changed)
        toolbar_layout.addWidget(self.cmb_tier, stretch=1)

        self.cmb_status = QComboBox()
        self.cmb_status.addItem("All Statuses", None)
        self.cmb_status.addItem("Active", True)
        self.cmb_status.addItem("Inactive", False)
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
        self.cmb_status.currentIndexChanged.connect(self._on_filter_changed)
        toolbar_layout.addWidget(self.cmb_status, stretch=1)

        v_toolbar.addLayout(toolbar_layout)

        # Fast Filter Chips Row
        chips_layout = QHBoxLayout()
        chips_layout.setSpacing(6)

        self.chip_all = QPushButton("All Customers")
        self.chip_plat = QPushButton("VIP Platinum")
        self.chip_gold = QPushButton("Gold")
        self.chip_silver = QPushButton("Silver")
        self.chip_bronze = QPushButton("Bronze")

        self.tier_chips = [
            (self.chip_all, "all", None),
            (self.chip_plat, "platinum", "platinum"),
            (self.chip_gold, "gold", "gold"),
            (self.chip_silver, "silver", "silver"),
            (self.chip_bronze, "bronze", "bronze"),
        ]

        for chip_btn, mode, t_name in self.tier_chips:
            chip_btn.setFixedHeight(26)
            chip_btn.setCursor(Qt.PointingHandCursor)
            chip_btn.clicked.connect(lambda chk, m=mode, tn=t_name: self._on_chip_clicked(m, tn))
            chips_layout.addWidget(chip_btn)

        chips_layout.addStretch()
        v_toolbar.addLayout(chips_layout)
        self._update_chip_styles()

        main_layout.addWidget(toolbar_card)

        # ── 4. Customers Table Feed ──
        self.tbl_customers = QTableWidget()
        self.tbl_customers.setColumnCount(7)
        self.tbl_customers.setHorizontalHeaderLabels([
            "AVATAR",
            "CUSTOMER & PHONE",
            "EMAIL & ADDRESS",
            "LOYALTY TIER",
            "POINTS BALANCE",
            "TOTAL SPENT",
            "ACTIONS",
        ])

        self.tbl_customers.verticalHeader().setVisible(False)
        self.tbl_customers.setAlternatingRowColors(True)
        self.tbl_customers.setShowGrid(False)
        self.tbl_customers.setStyleSheet("""
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

        header = self.tbl_customers.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Fixed)

        self.tbl_customers.setColumnWidth(0, 50)
        self.tbl_customers.setColumnWidth(6, 120)

        self.tbl_customers.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_customers.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_customers.doubleClicked.connect(self._on_row_double_clicked)
        main_layout.addWidget(self.tbl_customers, stretch=1)

        # ── 5. Pagination Footer ──
        footer_layout = QHBoxLayout()
        self.lbl_page_info = QLabel("Showing 0–0 of 0 customers")
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

    def _on_search_changed(self):
        self._page = 1
        self.load_customers()

    def _on_filter_changed(self):
        self._page = 1
        self.load_customers()

    def _on_chip_clicked(self, mode: str, tier_name: Optional[str]):
        self._active_chip = mode
        self._update_chip_styles()

        self.cmb_tier.blockSignals(True)
        if tier_name:
            idx = self.cmb_tier.findData(tier_name)
            if idx >= 0:
                self.cmb_tier.setCurrentIndex(idx)
        else:
            self.cmb_tier.setCurrentIndex(0)
        self.cmb_tier.blockSignals(False)

        self._page = 1
        self.load_customers()

    def _update_chip_styles(self):
        for chip_btn, mode, _ in self.tier_chips:
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
            self.load_customers()

    def _next_page(self):
        if self._page * self._page_size < self._total:
            self._page += 1
            self.load_customers()

    def load_customers(self):
        """Fetch customer profiles matching filters and populate table."""
        try:
            keyword = self.txt_search.text().strip() or None
            tier = self.cmb_tier.currentData()
            is_active = self.cmb_status.currentData()

            filters = CustomerFilterDTO(
                keyword=keyword,
                tier=tier,
                is_active=is_active,
                page=self._page,
                page_size=self._page_size,
            )

            result = self._customer_service.search(filters, self._user)
            self._customers_list = result.items
            self._total = result.total

            # Update Metrics
            metrics = self._customer_service.get_metrics(self._user)
            self.card_total.update_value(str(metrics.total_customers))
            self.card_total.set_caption("● Registered shoppers")

            self.card_members.update_value(str(metrics.loyalty_members))
            self.card_members.set_caption("● In rewards program")

            self.card_points.update_value(f"{metrics.total_points:,} pts")
            self.card_points.set_caption("● Total active points")

            self.card_spend.update_value(f"₱{metrics.avg_spend:,.2f}")
            self.card_spend.set_caption("● Average customer spend")

            # Render Table
            self.tbl_customers.setRowCount(len(result.items))
            dark_color = QColor("#0f172a")

            for row, c in enumerate(result.items):
                self.tbl_customers.setRowHeight(row, 48)

                # Col 0: Avatar
                initial = c.name[:1].upper() if c.name else "C"
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
                self.tbl_customers.setCellWidget(row, 0, av_container)

                # Col 1: Customer Name & Phone
                name_w = QWidget()
                name_l = QVBoxLayout(name_w)
                name_l.setContentsMargins(4, 2, 4, 2)
                name_l.setSpacing(1)
                full_lbl = QLabel(c.name)
                full_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #0f172a;")
                phone_lbl = QLabel(c.phone)
                phone_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #2563eb; font-family: 'Consolas', monospace;")
                name_l.addWidget(full_lbl)
                name_l.addWidget(phone_lbl)
                self.tbl_customers.setCellWidget(row, 1, name_w)

                # Col 2: Email & Address
                addr_w = QWidget()
                addr_l = QVBoxLayout(addr_w)
                addr_l.setContentsMargins(4, 2, 4, 2)
                addr_l.setSpacing(1)
                email_lbl = QLabel(c.email or "No email registered")
                email_lbl.setStyleSheet("font-size: 11px; color: #0f172a; font-weight: 500;")
                city_lbl = QLabel(c.address or "No address")
                city_lbl.setStyleSheet("font-size: 10px; color: #64748b;")
                addr_l.addWidget(email_lbl)
                addr_l.addWidget(city_lbl)
                self.tbl_customers.setCellWidget(row, 2, addr_w)

                # Col 3: Loyalty Tier Pill
                tier_lbl = QLabel(c.tier.upper())
                tier_lbl.setAlignment(Qt.AlignCenter)
                t_lower = c.tier.lower()
                if t_lower == "platinum":
                    t_style = "color: #7c3aed; background-color: #f3e8ff; border: 1px solid #e9d5ff;"
                elif t_lower == "gold":
                    t_style = "color: #d97706; background-color: #fffbeb; border: 1px solid #fde68a;"
                elif t_lower == "silver":
                    t_style = "color: #475569; background-color: #f1f5f9; border: 1px solid #cbd5e1;"
                else:
                    t_style = "color: #b45309; background-color: #ffedd5; border: 1px solid #fed7aa;"
                tier_lbl.setStyleSheet(f"{t_style} font-size: 9px; font-weight: 800; border-radius: 6px; padding: 2px 8px;")
                self.tbl_customers.setCellWidget(row, 3, tier_lbl)

                # Col 4: Points Balance
                pts_item = QTableWidgetItem(f"★ {c.loyalty_points:,} pts")
                pts_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                pts_item.setForeground(QColor("#d97706") if c.loyalty_points > 0 else QColor("#94a3b8"))
                pts_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                self.tbl_customers.setItem(row, 4, pts_item)

                # Col 5: Total Spent & Visits
                spend_item = QTableWidgetItem(f"₱{c.total_spent:,.2f} ({c.total_visits} v)")
                spend_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                spend_item.setForeground(dark_color)
                spend_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tbl_customers.setItem(row, 5, spend_item)

                # Col 6: Action Buttons (Edit + Adjust Points)
                act_w = QWidget()
                act_l = QHBoxLayout(act_w)
                act_l.setContentsMargins(4, 0, 4, 0)
                act_l.setSpacing(4)

                btn_edit = QPushButton()
                btn_edit.setIcon(IconManager.get_pixmap("edit", color="#2563eb", size=13))
                btn_edit.setFixedSize(28, 28)
                btn_edit.setToolTip("Edit Customer Profile")
                btn_edit.setCursor(Qt.PointingHandCursor)
                btn_edit.setStyleSheet("""
                    QPushButton {
                        background-color: #eff6ff;
                        border: 1px solid #bfdbfe;
                        border-radius: 6px;
                    }
                    QPushButton:hover { border-color: #2563eb; }
                """)
                btn_edit.clicked.connect(lambda chk, cust=c: self._open_edit_dialog(cust))
                act_l.addWidget(btn_edit)

                btn_pts = QPushButton()
                btn_pts.setIcon(IconManager.get_pixmap("tag", color="#d97706", size=13))
                btn_pts.setFixedSize(28, 28)
                btn_pts.setToolTip("Adjust Loyalty Points")
                btn_pts.setCursor(Qt.PointingHandCursor)
                btn_pts.setStyleSheet("""
                    QPushButton {
                        background-color: #fffbeb;
                        border: 1px solid #fde68a;
                        border-radius: 6px;
                    }
                    QPushButton:hover { border-color: #d97706; }
                """)
                btn_pts.clicked.connect(lambda chk, cust=c: self._open_points_dialog(cust))
                act_l.addWidget(btn_pts)

                self.tbl_customers.setCellWidget(row, 6, act_w)

            # Update Pagination Footer
            start_num = (result.page - 1) * result.page_size + 1 if result.total > 0 else 0
            end_num = min(result.page * result.page_size, result.total)
            self.lbl_page_info.setText(f"Showing {start_num}–{end_num} of {result.total} customers")
            self.btn_prev.setEnabled(result.has_previous)
            self.btn_next.setEnabled(result.has_next)

        except Exception as e:
            import logging
            logging.getLogger("retailflow.customers").exception("Failed to load customers", exc_info=e)

    def _on_row_double_clicked(self, index):
        row = index.row()
        if 0 <= row < len(self._customers_list):
            self._open_edit_dialog(self._customers_list[row])

    def _open_add_dialog(self):
        dlg = CustomerDialog(self._customer_service, self._user, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._toast.show_toast("Customer registered successfully!")
            self.load_customers()

    def _open_edit_dialog(self, customer: CustomerResponseDTO):
        dlg = CustomerDialog(self._customer_service, self._user, customer_data=customer, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._toast.show_toast(f"Updated profile for '{customer.name}'")
            self.load_customers()

    def _open_points_dialog(self, customer: CustomerResponseDTO):
        dlg = PointsAdjustmentDialog(self._customer_service, customer, self._user, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._toast.show_toast(f"Points updated for {customer.name}")
            self.load_customers()
