"""
RetailFlow POS - Sales History & Transactions Page
Provides sales history searching, payment method filtering, live sales metrics,
derived return badges, and thermal receipt inspection & reprint workflows.
"""

from decimal import Decimal
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

from application.dto.sales_dto import SaleResponseDTO
from application.services.auth_service import AuthenticationService
from application.services.returns_service import ReturnsService
from application.services.sales_service import SalesService
from infrastructure.database.models.auth import User
from presentation.dialogs.sale_details_dialog import SaleDetailsDialog
from presentation.dialogs.sale_success_dialog import SaleSuccessDialog
from presentation.styles.icons import IconManager
from presentation.widgets.metric_card import MetricCardWidget


class SalesPage(QWidget):
    """Sales History & Receipt Search Page with Integrated Return Status Badges."""

    def __init__(
        self,
        current_user: User,
        sales_service: SalesService,
        returns_service: Optional[ReturnsService] = None,
        auth_service: Optional[AuthenticationService] = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._user = current_user
        self._sales_service = sales_service
        self._returns_service = returns_service
        self._auth_service = auth_service
        self._sales_list: list[SaleResponseDTO] = []
        self._active_filter_chip = "all"

        self._init_ui()
        self.load_sales()

    @staticmethod
    def _format_datetime(dt_str: str) -> str:
        try:
            from datetime import datetime
            cleaned = dt_str.replace("Z", "")
            if "T" in cleaned:
                dt = datetime.fromisoformat(cleaned)
            else:
                dt = datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%b %d, %I:%M %p")
        except Exception:
            return dt_str

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # 1. Header Title & Refresh Action
        hdr_row = QHBoxLayout()
        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)
        title_lbl = QLabel("Sales History & Transactions")
        title_lbl.setStyleSheet("font-size: 22px; font-weight: 800; color: #0f172a; letter-spacing: -0.4px;")
        header_layout.addWidget(title_lbl)

        subtitle_lbl = QLabel("Track completed sales orders, inspect payment breakdowns, and re-print receipts.")
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
        btn_refresh.clicked.connect(self.load_sales)
        hdr_row.addWidget(btn_refresh)
        main_layout.addLayout(hdr_row)

        # 2. Summary Metric Cards Grid
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(12)

        self.card_revenue = MetricCardWidget(
            title="TODAY'S REVENUE",
            icon_name="sales",
            accent_color="#059669",
            badge_bg="#ecfdf5",
        )
        self.card_orders = MetricCardWidget(
            title="TODAY'S ORDERS",
            icon_name="check",
            accent_color="#2563eb",
            badge_bg="#eff6ff",
        )
        self.card_aov = MetricCardWidget(
            title="AVG. ORDER VALUE",
            icon_name="wallet",
            accent_color="#7c3aed",
            badge_bg="#f5f3ff",
        )
        self.card_rate = MetricCardWidget(
            title="FULFILLMENT RATE",
            icon_name="check",
            accent_color="#0284c7",
            badge_bg="#e0f2fe",
        )

        metrics_layout.addWidget(self.card_revenue)
        metrics_layout.addWidget(self.card_orders)
        metrics_layout.addWidget(self.card_aov)
        metrics_layout.addWidget(self.card_rate)
        main_layout.addLayout(metrics_layout)

        # 3. Search & Filter Bar
        toolbar_card = QFrame()
        toolbar_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 10px 14px;
            }
        """)
        v_toolbar = QVBoxLayout(toolbar_card)
        v_toolbar.setContentsMargins(0, 0, 0, 0)
        v_toolbar.setSpacing(10)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(10)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search by transaction #, cashier, or customer...")
        self.txt_search.setFixedHeight(36)
        self.txt_search.setStyleSheet("""
            QLineEdit {
                background-color: #f8fafc;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 0 12px;
                font-size: 13px;
                color: #0f172a;
            }
            QLineEdit:focus {
                background-color: #ffffff;
                border-color: #2563eb;
            }
        """)
        self.txt_search.textChanged.connect(self.load_sales)
        toolbar_layout.addWidget(self.txt_search, stretch=3)

        self.cmb_payment = QComboBox()
        self.cmb_payment.setFixedHeight(36)
        self.cmb_payment.addItems([
            "All Payment Methods",
            "Cash",
            "Card",
            "GCash",
            "Maya",
        ])
        self.cmb_payment.setStyleSheet("""
            QComboBox {
                background-color: #f8fafc;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 0 12px;
                font-size: 13px;
                color: #0f172a;
            }
            QComboBox:focus { border-color: #2563eb; }
        """)
        self.cmb_payment.currentIndexChanged.connect(self._on_payment_combo_changed)
        toolbar_layout.addWidget(self.cmb_payment, stretch=1)

        v_toolbar.addLayout(toolbar_layout)

        # Quick Payment Filter Chips
        chips_layout = QHBoxLayout()
        chips_layout.setSpacing(6)

        self.chip_all = QPushButton("All Sales")
        self.chip_cash = QPushButton("Cash")
        self.chip_card = QPushButton("Card")
        self.chip_gcash = QPushButton("GCash / Maya")

        self.payment_chips = [
            (self.chip_all, "all", "All Payment Methods"),
            (self.chip_cash, "cash", "Cash"),
            (self.chip_card, "card", "Card"),
            (self.chip_gcash, "gcash", "GCash"),
        ]

        for chip_btn, mode, combo_text in self.payment_chips:
            chip_btn.setFixedHeight(26)
            chip_btn.setCursor(Qt.PointingHandCursor)
            chip_btn.clicked.connect(lambda chk, m=mode, t=combo_text: self._on_chip_clicked(m, t))
            chips_layout.addWidget(chip_btn)

        chips_layout.addStretch()
        v_toolbar.addLayout(chips_layout)
        self._update_chip_styles()

        main_layout.addWidget(toolbar_card)

        # 4. Sales Table Grid
        self.tbl_sales = QTableWidget()
        self.tbl_sales.setColumnCount(7)
        self.tbl_sales.setHorizontalHeaderLabels([
            "TRANSACTION #",
            "DATE & TIME",
            "PAYMENT METHOD",
            "ITEMS",
            "TOTAL DUE",
            "STATUS / RETURNS",
            "ACTIONS",
        ])

        self.tbl_sales.verticalHeader().setVisible(False)
        self.tbl_sales.setAlternatingRowColors(True)
        self.tbl_sales.setShowGrid(False)
        self.tbl_sales.setStyleSheet("""
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
                padding: 6px 10px;
                border-bottom: 1px solid #f1f5f9;
            }
        """)

        header = self.tbl_sales.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)

        self.tbl_sales.doubleClicked.connect(self._on_row_double_clicked)
        main_layout.addWidget(self.tbl_sales, stretch=1)

    def _on_chip_clicked(self, mode: str, combo_text: str):
        self._active_filter_chip = mode
        self._update_chip_styles()
        idx = self.cmb_payment.findText(combo_text)
        if idx >= 0:
            self.cmb_payment.setCurrentIndex(idx)
        else:
            self.load_sales()

    def _on_payment_combo_changed(self):
        txt = self.cmb_payment.currentText()
        if txt.lower() == "cash":
            self._active_filter_chip = "cash"
        elif txt.lower() == "card":
            self._active_filter_chip = "card"
        elif txt.lower() in ("gcash", "maya"):
            self._active_filter_chip = "gcash"
        else:
            self._active_filter_chip = "all"
        self._update_chip_styles()
        self.load_sales()

    def _update_chip_styles(self):
        for chip_btn, mode, _ in self.payment_chips:
            is_active = self._active_filter_chip == mode
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

    def load_sales(self):
        """Fetch sales transactions matching filters."""
        try:
            keyword = self.txt_search.text().strip() or None
            payment_filter = self.cmb_payment.currentText()

            result = self._sales_service.search_sales(keyword=keyword, page=1, page_size=100)
            items = result.items

            if payment_filter != "All Payment Methods":
                items = [s for s in items if s.payment_method.lower() == payment_filter.lower()]

            self._sales_list = items

            # Update Metrics
            today_rev, today_count = self._sales_service.get_today_summary()
            self.card_revenue.update_value(f"₱{today_rev:,.2f}")
            self.card_orders.update_value(f"{today_count} Orders")
            aov = (today_rev / Decimal(today_count)) if today_count > 0 else Decimal("0.00")
            self.card_aov.update_value(f"₱{aov:,.2f}")
            self.card_rate.update_value("100%" if today_count > 0 else "0%")

            # Populate Table
            self.tbl_sales.setRowCount(len(items))
            dark_color = QColor("#0f172a")

            for row, s in enumerate(items):
                self.tbl_sales.setRowHeight(row, 44)

                # Transaction #
                txn_item = QTableWidgetItem(s.transaction_number)
                txn_item.setFont(QFont("Consolas", 10, QFont.Bold))
                txn_item.setForeground(dark_color)
                txn_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                txn_item.setData(Qt.UserRole, s)
                self.tbl_sales.setItem(row, 0, txn_item)

                # Date & Time
                formatted_time = self._format_datetime(s.created_at)
                date_item = QTableWidgetItem(formatted_time)
                date_item.setForeground(QColor("#64748b"))
                date_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.tbl_sales.setItem(row, 1, date_item)

                # Payment Method
                pm_lbl = QLabel(s.payment_method.upper())
                pm_lbl.setAlignment(Qt.AlignCenter)
                pm_lower = s.payment_method.lower()
                if "cash" in pm_lower:
                    pm_style = "color: #0284c7; background-color: #e0f2fe; border: 1px solid #bae6fd;"
                elif "card" in pm_lower:
                    pm_style = "color: #7c3aed; background-color: #f3e8ff; border: 1px solid #e9d5ff;"
                else:
                    pm_style = "color: #0d9488; background-color: #ccfbf1; border: 1px solid #99f6e4;"
                pm_lbl.setStyleSheet(f"{pm_style} font-size: 9px; font-weight: 800; border-radius: 6px; padding: 2px 8px;")
                self.tbl_sales.setCellWidget(row, 2, pm_lbl)

                # Items Count
                total_qty = sum(item.quantity for item in s.items)
                items_item = QTableWidgetItem(f"{total_qty} items ({len(s.items)} SKUs)")
                items_item.setForeground(QColor("#475569"))
                items_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                self.tbl_sales.setItem(row, 3, items_item)

                # Total Due
                total_item = QTableWidgetItem(f"₱{s.total_amount:,.2f}")
                total_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                total_item.setForeground(dark_color)
                total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tbl_sales.setItem(row, 4, total_item)

                # Status & Derived Return Badge Container
                status_cell = QWidget()
                status_layout = QHBoxLayout(status_cell)
                status_layout.setContentsMargins(4, 0, 4, 0)
                status_layout.setSpacing(6)

                status_lbl = QLabel("COMPLETED")
                status_lbl.setAlignment(Qt.AlignCenter)
                status_lbl.setStyleSheet("""
                    color: #047857;
                    font-size: 10px;
                    font-weight: 800;
                    background-color: #ecfdf5;
                    border: 1px solid #a7f3d0;
                    border-radius: 6px;
                    padding: 2px 8px;
                """)
                status_layout.addWidget(status_lbl)

                # Query Return State if ReturnsService is available
                if self._returns_service:
                    try:
                        sum_dto = self._returns_service.get_sale_return_summary(s.id, actor=self._user)
                        if sum_dto.derived_state == "partial":
                            ret_lbl = QLabel("PARTIAL RETURN")
                            ret_lbl.setStyleSheet("""
                                color: #b45309;
                                font-size: 9px;
                                font-weight: 800;
                                background-color: #fffbeb;
                                border: 1px solid #fde68a;
                                border-radius: 6px;
                                padding: 2px 6px;
                            """)
                            status_layout.addWidget(ret_lbl)
                        elif sum_dto.derived_state == "full":
                            ret_lbl = QLabel("FULLY RETURNED")
                            ret_lbl.setStyleSheet("""
                                color: #b91c1c;
                                font-size: 9px;
                                font-weight: 800;
                                background-color: #fef2f2;
                                border: 1px solid #fecaca;
                                border-radius: 6px;
                                padding: 2px 6px;
                            """)
                            status_layout.addWidget(ret_lbl)
                    except Exception:
                        pass

                status_layout.addStretch()
                self.tbl_sales.setCellWidget(row, 5, status_cell)

                # Action Buttons (View Details + Print Receipt)
                act_widget = QWidget()
                act_layout = QHBoxLayout(act_widget)
                act_layout.setContentsMargins(4, 0, 4, 0)
                act_layout.setSpacing(6)

                btn_view = QPushButton("View")
                btn_view.setIcon(IconManager.get_pixmap("eye", color="#2563eb", size=13))
                btn_view.setCursor(Qt.PointingHandCursor)
                btn_view.setFixedHeight(28)
                btn_view.setStyleSheet("""
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
                btn_view.clicked.connect(lambda checked, sale=s: self._show_details(sale))
                act_layout.addWidget(btn_view)

                btn_print = QPushButton()
                btn_print.setIcon(IconManager.get_pixmap("print", color="#475569", size=13))
                btn_print.setFixedSize(28, 28)
                btn_print.setCursor(Qt.PointingHandCursor)
                btn_print.setStyleSheet("""
                    QPushButton {
                        background-color: #ffffff;
                        border: 1px solid #cbd5e1;
                        border-radius: 6px;
                    }
                    QPushButton:hover {
                        background-color: #f1f5f9;
                    }
                """)
                btn_print.clicked.connect(lambda checked, sale=s: self._reprint_sale(sale))
                act_layout.addWidget(btn_print)

                self.tbl_sales.setCellWidget(row, 6, act_widget)

        except Exception as e:
            import logging
            logging.getLogger("retailflow.sales").exception("Failed to load sales", exc_info=e)

    def _on_row_double_clicked(self, index):
        row = index.row()
        item = self.tbl_sales.item(row, 0)
        if item:
            sale = item.data(Qt.UserRole)
            if sale:
                self._show_details(sale)

    def _show_details(self, sale: SaleResponseDTO):
        dlg = SaleDetailsDialog(
            sale=sale,
            returns_service=self._returns_service,
            auth_service=self._auth_service,
            current_user=self._user,
            parent=self,
        )
        dlg.exec()

    def _reprint_sale(self, sale: SaleResponseDTO):
        dlg = SaleSuccessDialog(sale, self)
        dlg.exec()
