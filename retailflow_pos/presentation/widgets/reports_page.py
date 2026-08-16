"""
RetailFlow POS - Reports & Financial Analytics Workstation Page (Phase 5B Production)
Executive-grade reporting workstation featuring global date range controls, executive KPI cards,
financial trend timeline chart, waterfall Profit & Loss statement, store OPEX category allocations,
tax & tender reconciliation, payment & refund breakdowns, product contribution leaderboard,
cashier operational performance, current inventory snapshot, received purchasing intake,
and permission-aware CSV export actions.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QFont, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QDateEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from application.dto.report_dto import (
    CashierPerformanceDTO,
    DailyFinancialPointDTO,
    ExpenseCategoryBreakdownDTO,
    FinancialSummaryDTO,
    InventoryValueDTO,
    PaymentMethodSummaryDTO,
    ProductPerformanceDTO,
    PurchaseIntakeSummaryDTO,
    RefundMethodSummaryDTO,
)
from application.services.report_export_service import ReportExportService
from application.services.report_service import ReportService
from domain.exceptions import AuthorizationError, ValidationError
from infrastructure.database.models.auth import User
from presentation.styles.icons import IconManager
from presentation.widgets.charts.financial_trend_chart import FinancialTrendChartWidget
from presentation.widgets.metric_card import MetricCardWidget
from presentation.widgets.toast_notification import ToastNotification


class ReportsPage(QWidget):
    """Executive Reports and Financial Analytics Workstation Page."""

    BREAKPOINT_WIDTH = 1180

    def __init__(
        self,
        current_user: User,
        report_service: ReportService,
        report_export_service: Optional[ReportExportService] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._user = current_user
        self._report_service = report_service
        self._report_export_service = report_export_service or ReportExportService(report_service)

        self._active_preset = "this_month"
        self._is_compact_layout = False

        # Cached DTO data
        self._current_summary: Optional[FinancialSummaryDTO] = None
        self._current_trend_points: List[DailyFinancialPointDTO] = []
        self._current_opex_breakdown: List[ExpenseCategoryBreakdownDTO] = []
        self._current_payment_methods: List[PaymentMethodSummaryDTO] = []
        self._current_refund_methods: List[RefundMethodSummaryDTO] = []
        self._current_products: List[ProductPerformanceDTO] = []
        self._current_cashiers: List[CashierPerformanceDTO] = []
        self._current_purchasing: Optional[PurchaseIntakeSummaryDTO] = None
        self._current_inventory: Optional[InventoryValueDTO] = None

        self._preset_buttons: dict[str, QPushButton] = {}

        self._init_ui()
        self._reload_report_data()

    def _has_permission(self, code: str) -> bool:
        if not self._user:
            return False
        if hasattr(self._user, "is_admin") and self._user.is_admin():
            return True
        return self._user.has_permission(code)

    # ── UI Construction ─────────────────────────────────────────────

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Toast notification overlay
        self._toast = ToastNotification(self)

        # ── Scroll Area for Vertical Narrative ──
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setStyleSheet("QScrollArea { background-color: #f8fafc; border: none; }")

        self._content_widget = QWidget()
        self._content_widget.setStyleSheet("background-color: #f8fafc;")
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(20, 20, 20, 24)
        self._content_layout.setSpacing(16)

        # ── 1. Page Header & Export Action ──
        self._build_header_section()

        # ── 2. Global Date Filter Toolbar ──
        self._build_date_toolbar()

        # ── 3. Executive KPI Cards Row ──
        self._build_kpi_section()

        # ── 4. Financial Trend Timeline Chart ──
        self.chart_widget = FinancialTrendChartWidget(self._content_widget)
        self._content_layout.addWidget(self.chart_widget)

        # ── 5. Paired Row 1: Waterfall P&L (Left) ↔ OPEX Category Breakdown (Right) ──
        self._build_pnl_and_opex_section()

        # ── 6. Paired Row 2: Tax & Tender Reconciliation (Left) ↔ Payment & Refund Breakdown (Right) ──
        self._build_tax_and_payment_section()

        # ── 7. Full-Width Table: Product Performance Leaderboard ──
        self._build_product_performance_section()

        # ── 8. Full-Width Table: Cashier Operational Performance ──
        self._build_cashier_performance_section()

        # ── 9. Paired Row 3: Current Inventory Snapshot (Left) ↔ Received Purchasing Summary (Right) ──
        self._build_inventory_and_purchasing_section()

        self._scroll.setWidget(self._content_widget)
        root.addWidget(self._scroll)

    # ── 1. Header & Export Action ────────────────────────────────────

    def _build_header_section(self):
        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(0, 0, 0, 4)
        hdr_row.setSpacing(12)

        # Title + Subtitle container
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        lbl_title = QLabel("Executive Reports & Financial Analytics")
        lbl_title.setStyleSheet("font-size: 22px; font-weight: 800; color: #0f172a; border: none; letter-spacing: -0.5px;")
        lbl_sub = QLabel("Operational P&L performance, customer returns, revenue trends, cashier audit, and working capital insights.")
        lbl_sub.setStyleSheet("font-size: 12px; font-weight: 500; color: #64748b; border: none;")

        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        hdr_row.addLayout(title_box)

        hdr_row.addStretch(1)

        # Export CSV Button (Permission-Guarded)
        can_export = self._has_permission("export_reports")
        self.btn_export = QPushButton(" Export Reports ▾")
        self.btn_export.setIcon(IconManager.get_icon("download", color="#ffffff"))
        self.btn_export.setFixedHeight(34)
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 0 14px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton::menu-indicator {
                image: none;
                width: 0px;
            }
        """)

        # Build Export Dropdown Menu
        self._export_menu = QMenu(self)
        self._export_menu.setStyleSheet("""
            QMenu {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 4px 0px;
            }
            QMenu::item {
                padding: 8px 18px;
                font-size: 12px;
                font-weight: 600;
                color: #0f172a;
            }
            QMenu::item:selected {
                background-color: #eff6ff;
                color: #2563eb;
            }
        """)

        act_summary = self._export_menu.addAction("📊 Executive Financial Summary")
        act_summary.triggered.connect(lambda: self._on_export_action("Financial Summary"))

        act_products = self._export_menu.addAction("🏆 Product Contribution Leaderboard")
        act_products.triggered.connect(lambda: self._on_export_action("Product Performance"))

        act_cashiers = self._export_menu.addAction("👤 Cashier Operational Performance")
        act_cashiers.triggered.connect(lambda: self._on_export_action("Cashier Performance"))

        act_opex = self._export_menu.addAction("💼 Store OPEX Breakdown")
        act_opex.triggered.connect(lambda: self._on_export_action("OPEX Breakdown"))

        act_payments = self._export_menu.addAction("💳 Collections & Refunds by Channel")
        act_payments.triggered.connect(lambda: self._on_export_action("Payment Methods"))

        # Refresh button
        self.btn_refresh = QPushButton(" Refresh")
        self.btn_refresh.setIcon(IconManager.get_icon("rotate-cw", color="#334155"))
        self.btn_refresh.setFixedHeight(34)
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #f8fafc;
                color: #334155;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 0 12px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                border-color: #94a3b8;
            }
        """)
        self.btn_refresh.clicked.connect(self._reload_report_data)
        hdr_row.addWidget(self.btn_refresh)

        self.btn_export.setMenu(self._export_menu)
        self.btn_export.setVisible(can_export)
        hdr_row.addWidget(self.btn_export)

        self._content_layout.addLayout(hdr_row)

    def _on_export_action(self, export_type: str):
        """Handle user selection from Export CSV dropdown menu."""
        start_date, end_date = self._get_active_date_range()
        default_name = self._report_export_service.get_default_filename(
            export_type=export_type,
            start_date=start_date,
            end_date=end_date,
        )

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {export_type} (CSV)",
            default_name,
            "CSV Files (*.csv)",
        )

        if not file_path:
            return  # User cancelled dialog

        try:
            if export_type == "Financial Summary":
                self._report_export_service.export_financial_summary_csv(
                    start_date=start_date,
                    end_date=end_date,
                    actor=self._user,
                    target_path=file_path,
                )
            elif export_type == "Product Performance":
                self._report_export_service.export_product_performance_csv(
                    start_date=start_date,
                    end_date=end_date,
                    actor=self._user,
                    target_path=file_path,
                )
            elif export_type == "Cashier Performance":
                self._report_export_service.export_cashier_performance_csv(
                    start_date=start_date,
                    end_date=end_date,
                    actor=self._user,
                    target_path=file_path,
                )
            elif export_type == "OPEX Breakdown":
                self._report_export_service.export_opex_breakdown_csv(
                    start_date=start_date,
                    end_date=end_date,
                    actor=self._user,
                    target_path=file_path,
                )
            elif export_type == "Payment Methods":
                self._report_export_service.export_payment_methods_csv(
                    start_date=start_date,
                    end_date=end_date,
                    actor=self._user,
                    target_path=file_path,
                )

            self._toast.show_toast(f"{export_type} exported successfully.", "success")

        except (AuthorizationError, ValidationError) as e:
            self._toast.show_toast(f"Export failed: {str(e)}", "error")
        except Exception:
            self._toast.show_toast(f"Failed to export {export_type}.", "error")

    # ── 2. Global Date Toolbar ───────────────────────────────────────

    def _build_date_toolbar(self):
        toolbar_frame = QFrame()
        toolbar_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(toolbar_frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # Row 1: Presets + Custom Date Pickers
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        lbl_range = QLabel("PERIOD:")
        lbl_range.setStyleSheet("font-size: 11px; font-weight: 800; color: #64748b; letter-spacing: 0.5px; border: none;")
        top_row.addWidget(lbl_range)

        # Segmented Preset Buttons
        self._preset_group = QButtonGroup(self)
        presets = [
            ("today", "Today"),
            ("yesterday", "Yesterday"),
            ("last_7_days", "Last 7 Days"),
            ("this_month", "This Month"),
            ("last_month", "Last Month"),
            ("this_year", "This Year"),
            ("custom", "Custom Range"),
        ]

        for p_key, p_label in presets:
            btn = QPushButton(p_label)
            btn.setCheckable(True)
            btn.setFixedHeight(30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, k=p_key: self._on_preset_clicked(k))
            self._preset_buttons[p_key] = btn
            self._preset_group.addButton(btn)
            top_row.addWidget(btn)

        # Set default active preset
        self._preset_buttons["this_month"].setChecked(True)
        self._update_preset_styles()

        top_row.addStretch(1)

        # Custom Pickers (Hidden unless "custom" is selected)
        self._custom_pickers_widget = QWidget()
        custom_layout = QHBoxLayout(self._custom_pickers_widget)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(8)

        lbl_from = QLabel("From:")
        lbl_from.setStyleSheet("font-size: 11px; font-weight: 700; color: #475569; border: none;")
        self.dt_start = QDateEdit()
        self.dt_start.setCalendarPopup(True)
        self.dt_start.setDisplayFormat("yyyy-MM-dd")
        self.dt_start.setDate(QDate.currentDate().addDays(-30))
        self.dt_start.setFixedHeight(30)
        self.dt_start.setStyleSheet("""
            QDateEdit {
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 2px 8px;
                font-size: 12px;
                font-weight: 600;
                color: #0f172a;
                background-color: #ffffff;
            }
            QDateEdit:focus { border-color: #2563eb; }
        """)
        self.dt_start.dateChanged.connect(self._on_custom_date_changed)

        lbl_to = QLabel("To:")
        lbl_to.setStyleSheet("font-size: 11px; font-weight: 700; color: #475569; border: none;")
        self.dt_end = QDateEdit()
        self.dt_end.setCalendarPopup(True)
        self.dt_end.setDisplayFormat("yyyy-MM-dd")
        self.dt_end.setDate(QDate.currentDate())
        self.dt_end.setFixedHeight(30)
        self.dt_end.setStyleSheet("""
            QDateEdit {
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 2px 8px;
                font-size: 12px;
                font-weight: 600;
                color: #0f172a;
                background-color: #ffffff;
            }
            QDateEdit:focus { border-color: #2563eb; }
        """)
        self.dt_end.dateChanged.connect(self._on_custom_date_changed)

        custom_layout.addWidget(lbl_from)
        custom_layout.addWidget(self.dt_start)
        custom_layout.addWidget(lbl_to)
        custom_layout.addWidget(self.dt_end)
        self._custom_pickers_widget.setVisible(False)
        top_row.addWidget(self._custom_pickers_widget)

        layout.addLayout(top_row)

        # Row 2: Active Period Banner
        self.lbl_active_period = QLabel("📅 Active Period: Loading...")
        self.lbl_active_period.setStyleSheet("font-size: 12px; font-weight: 700; color: #2563eb; border: none;")
        layout.addWidget(self.lbl_active_period)

        self._content_layout.addWidget(toolbar_frame)

    def _update_preset_styles(self):
        for key, btn in self._preset_buttons.items():
            if key == self._active_preset:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2563eb;
                        color: #ffffff;
                        border: 1px solid #2563eb;
                        border-radius: 6px;
                        font-size: 11px;
                        font-weight: 700;
                        padding: 0 10px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f8fafc;
                        color: #475569;
                        border: 1px solid #cbd5e1;
                        border-radius: 6px;
                        font-size: 11px;
                        font-weight: 600;
                        padding: 0 10px;
                    }
                    QPushButton:hover {
                        background-color: #f1f5f9;
                        border-color: #94a3b8;
                    }
                """)

    def _on_preset_clicked(self, preset_key: str):
        self._active_preset = preset_key
        self._update_preset_styles()
        self._custom_pickers_widget.setVisible(preset_key == "custom")
        self._reload_report_data()

    def _on_custom_date_changed(self):
        if self._active_preset == "custom":
            self._reload_report_data()

    # ── 3. Executive KPI Cards Row ───────────────────────────────────

    def _build_kpi_section(self):
        self.card_net_sales = MetricCardWidget(
            title="NET SALES",
            icon_name="shopping-bag",
            accent_color="#2563eb",
            badge_bg="#eff6ff",
        )
        self.card_gross_profit = MetricCardWidget(
            title="GROSS PROFIT",
            icon_name="dollar-sign",
            accent_color="#059669",
            badge_bg="#ecfdf5",
        )
        self.card_opex = MetricCardWidget(
            title="STORE OPERATING EXPENSES",
            icon_name="pie-chart",
            accent_color="#d97706",
            badge_bg="#fffbeb",
        )
        self.card_net_operating_profit = MetricCardWidget(
            title="NET OPERATING PROFIT",
            icon_name="award",
            accent_color="#7c3aed",
            badge_bg="#f5f3ff",
        )

        self._kpi_cards = [
            self.card_net_sales,
            self.card_gross_profit,
            self.card_opex,
            self.card_net_operating_profit,
        ]

        self._kpi_container = QWidget()
        self._kpi_layout_h = QHBoxLayout()
        self._kpi_layout_h.setContentsMargins(0, 0, 0, 0)
        self._kpi_layout_h.setSpacing(12)

        for c in self._kpi_cards:
            self._kpi_layout_h.addWidget(c)
        self._kpi_container.setLayout(self._kpi_layout_h)

        self._content_layout.addWidget(self._kpi_container)

    # ── 4. Paired Analytical Row 1 (P&L ↔ OPEX) ──────────────────────

    def _build_pnl_and_opex_section(self):
        self._pnl_card = self._build_pnl_card()
        self._opex_card = self._build_opex_card()

        self._analytical_container = QWidget()
        self._analytical_layout = QHBoxLayout(self._analytical_container)
        self._analytical_layout.setContentsMargins(0, 0, 0, 0)
        self._analytical_layout.setSpacing(14)

        self._analytical_layout.addWidget(self._pnl_card, 1)
        self._analytical_layout.addWidget(self._opex_card, 1)

        self._content_layout.addWidget(self._analytical_container)

    def _build_pnl_card(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        # Card Title
        hdr = QLabel("Profit & Loss Statement (P&L)")
        hdr.setStyleSheet("font-size: 15px; font-weight: 800; color: #0f172a; border: none;")
        layout.addWidget(hdr)

        # Waterfall rows
        self._pnl_rows = {}
        row_defs = [
            ("gross_sales", "Gross Sales", "#0f172a", False),
            ("discounts", "Less: Discounts Granted", "#dc2626", False),
            ("sales_returns", "Less: Customer Returns", "#dc2626", False),
            ("net_sales", "= Net Sales", "#2563eb", True),
            ("cogs", "Less: Cost of Goods Sold (COGS)", "#dc2626", False),
            ("gross_profit", "= Gross Profit", "#059669", True),
            ("gross_margin", "  Gross Margin %", "#64748b", False),
            ("opex", "Less: Store Operating Expenses (OPEX)", "#dc2626", False),
            ("net_operating_profit", "= Net Operating Profit", "#7c3aed", True),
            ("net_operating_margin", "  Net Operating Margin %", "#64748b", False),
        ]

        for key, label_text, color, is_bold in row_defs:
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            val = QLabel("₱0.00" if "%" not in label_text else "0.0%")

            weight = "800" if is_bold else "500"
            size = "13px" if not is_bold else ("15px" if key == "net_operating_profit" else "14px")
            lbl.setStyleSheet(f"font-size: {size}; font-weight: {weight}; color: #334155; border: none;")
            val.setStyleSheet(f"font-size: {size}; font-weight: {weight}; color: {color}; border: none;")
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            row.addWidget(lbl)
            row.addStretch(1)
            row.addWidget(val)

            self._pnl_rows[key] = (lbl, val)

            # Separator line before key subtotal lines
            if key in ["net_sales", "gross_profit", "net_operating_profit"]:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setStyleSheet("background-color: #f1f5f9; max-height: 1px; border: none;")
                layout.addWidget(sep)

            layout.addLayout(row)

        return frame

    def _build_opex_card(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        # Card Title
        hdr = QLabel("Store Operating Expenses Breakdown")
        hdr.setStyleSheet("font-size: 15px; font-weight: 800; color: #0f172a; border: none;")
        layout.addWidget(hdr)

        # Container for dynamic category progress rows
        self._opex_list_widget = QWidget()
        self._opex_list_layout = QVBoxLayout(self._opex_list_widget)
        self._opex_list_layout.setContentsMargins(0, 0, 0, 0)
        self._opex_list_layout.setSpacing(8)

        self._opex_empty_lbl = QLabel("No paid operating expenses for this period.")
        self._opex_empty_lbl.setStyleSheet("font-size: 12px; color: #94a3b8; font-style: italic; border: none; padding: 20px 0;")
        self._opex_empty_lbl.setAlignment(Qt.AlignCenter)
        self._opex_list_layout.addWidget(self._opex_empty_lbl)

        layout.addWidget(self._opex_list_widget)
        layout.addStretch(1)
        return frame

    # ── 5. Paired Analytical Row 2 (Tax/Tender ↔ Payment Methods) ────

    def _build_tax_and_payment_section(self):
        self._tax_tender_card = self._build_tax_tender_card()
        self._payment_card = self._build_payment_card()

        self._tax_payment_container = QWidget()
        self._tax_payment_layout = QHBoxLayout(self._tax_payment_container)
        self._tax_payment_layout.setContentsMargins(0, 0, 0, 0)
        self._tax_payment_layout.setSpacing(14)

        self._tax_payment_layout.addWidget(self._tax_tender_card, 1)
        self._tax_payment_layout.addWidget(self._payment_card, 1)

        self._content_layout.addWidget(self._tax_payment_container)

    def _build_tax_tender_card(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        hdr = QLabel("Tax & Tender Operational Reconciliation")
        hdr.setStyleSheet("font-size: 15px; font-weight: 800; color: #0f172a; border: none;")
        layout.addWidget(hdr)

        sub_info = QLabel("Output VAT and collections are operational tax and cash drawer reconciliation metrics.")
        sub_info.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 500; border: none;")
        layout.addWidget(sub_info)

        # Structured Grid for Tax and Tender Reconciliation
        grid = QGridLayout()
        grid.setSpacing(8)

        self.lbl_gross_vat_val = QLabel("₱0.00")
        self.lbl_vat_reversals_val = QLabel("₱0.00")
        self.lbl_net_vat_val = QLabel("₱0.00")

        self.lbl_collections_val = QLabel("₱0.00")
        self.lbl_refunds_val = QLabel("₱0.00")
        self.lbl_net_collections_val = QLabel("₱0.00")

        tiles = [
            ("GROSS OUTPUT VAT", self.lbl_gross_vat_val, "#475569", 0, 0),
            ("OUTPUT VAT REVERSALS", self.lbl_vat_reversals_val, "#dc2626", 0, 1),
            ("NET OUTPUT VAT", self.lbl_net_vat_val, "#0f172a", 0, 2),
            ("GROSS COLLECTIONS", self.lbl_collections_val, "#475569", 1, 0),
            ("REFUNDS ISSUED", self.lbl_refunds_val, "#dc2626", 1, 1),
            ("NET COLLECTIONS", self.lbl_net_collections_val, "#2563eb", 1, 2),
        ]

        for title, val_lbl, color, r, c in tiles:
            tile = QFrame()
            tile.setStyleSheet("background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 4px;")
            tl = QVBoxLayout(tile)
            tl.setContentsMargins(8, 6, 8, 6)
            tl.setSpacing(2)

            t_lbl = QLabel(title)
            t_lbl.setStyleSheet("font-size: 9px; font-weight: 700; color: #64748b; border: none; letter-spacing: 0.5px;")
            val_lbl.setStyleSheet(f"font-size: 14px; font-weight: 800; color: {color}; border: none;")

            tl.addWidget(t_lbl)
            tl.addWidget(val_lbl)
            grid.addWidget(tile, r, c)

        layout.addLayout(grid)
        layout.addStretch(1)
        return frame

    def _build_payment_card(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        # Section 1: Gross Collections by Payment Method
        hdr = QLabel("Collections by Payment Method")
        hdr.setStyleSheet("font-size: 15px; font-weight: 800; color: #0f172a; border: none;")
        layout.addWidget(hdr)

        sub_info = QLabel("Gross incoming tendered amounts across payment channels.")
        sub_info.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 500; border: none;")
        layout.addWidget(sub_info)

        self._payment_list_widget = QWidget()
        self._payment_list_layout = QVBoxLayout(self._payment_list_widget)
        self._payment_list_layout.setContentsMargins(0, 0, 0, 0)
        self._payment_list_layout.setSpacing(6)

        self._payment_empty_lbl = QLabel("No completed sale collections for this period.")
        self._payment_empty_lbl.setStyleSheet("font-size: 12px; color: #94a3b8; font-style: italic; border: none; padding: 10px 0;")
        self._payment_empty_lbl.setAlignment(Qt.AlignCenter)
        self._payment_list_layout.addWidget(self._payment_empty_lbl)

        layout.addWidget(self._payment_list_widget)

        # Divider
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: #f1f5f9; max-height: 1px; border: none;")
        layout.addWidget(sep)

        # Section 2: Customer Refunds Disbursed by Method Channel
        hdr_refunds = QLabel("Refunds Disbursed by Method")
        hdr_refunds.setStyleSheet("font-size: 13px; font-weight: 800; color: #dc2626; border: none;")
        layout.addWidget(hdr_refunds)

        self._refund_list_widget = QWidget()
        self._refund_list_layout = QVBoxLayout(self._refund_list_widget)
        self._refund_list_layout.setContentsMargins(0, 0, 0, 0)
        self._refund_list_layout.setSpacing(6)

        self._refund_empty_lbl = QLabel("No customer refunds processed for this period.")
        self._refund_empty_lbl.setStyleSheet("font-size: 12px; color: #94a3b8; font-style: italic; border: none; padding: 10px 0;")
        self._refund_empty_lbl.setAlignment(Qt.AlignCenter)
        self._refund_list_layout.addWidget(self._refund_empty_lbl)

        layout.addWidget(self._refund_list_widget)

        layout.addStretch(1)
        return frame

    # ── 6. Full-Width Table: Product Performance ─────────────────────

    def _build_product_performance_section(self):
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        hdr = QLabel("Product Contribution Leaderboard")
        hdr.setStyleSheet("font-size: 15px; font-weight: 800; color: #0f172a; border: none;")
        layout.addWidget(hdr)

        sub = QLabel("Direct contribution reflects pre-order-discount product performance net of customer return reversals.")
        sub.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 500; border: none;")
        layout.addWidget(sub)

        # Product Table (Net Metrics)
        self.product_table = QTableWidget()
        self.product_table.setColumnCount(6)
        self.product_table.setHorizontalHeaderLabels([
            "Rank",
            "Product / SKU",
            "Net Units",
            "Net Gross Revenue",
            "Net COGS",
            "Direct Margin",
        ])
        self.product_table.verticalHeader().setVisible(False)
        self.product_table.setAlternatingRowColors(True)
        self.product_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.product_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.product_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.product_table.setShowGrid(False)
        self.product_table.setMinimumHeight(240)
        self.product_table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                gridline-color: #f1f5f9;
                font-size: 12px;
                color: #0f172a;
            }
            QTableWidget::item {
                padding: 6px 10px;
                border-bottom: 1px solid #f1f5f9;
            }
            QTableWidget::item:selected {
                background-color: #f0fdf4;
                color: #0f172a;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #475569;
                font-weight: 700;
                font-size: 11px;
                border: none;
                border-bottom: 2px solid #e2e8f0;
                padding: 6px 10px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
        """)

        # Header sizing
        header = self.product_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)

        layout.addWidget(self.product_table)

        self._product_empty_lbl = QLabel("No product sales activity for this period.")
        self._product_empty_lbl.setStyleSheet("font-size: 12px; color: #94a3b8; font-style: italic; border: none; padding: 20px 0;")
        self._product_empty_lbl.setAlignment(Qt.AlignCenter)
        self._product_empty_lbl.setVisible(False)
        layout.addWidget(self._product_empty_lbl)

        self._content_layout.addWidget(card)

    # ── 7. Full-Width Table: Cashier Performance ─────────────────────

    def _build_cashier_performance_section(self):
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        hdr = QLabel("Cashier Operational Performance")
        hdr.setStyleSheet("font-size: 15px; font-weight: 800; color: #0f172a; border: none;")
        layout.addWidget(hdr)

        sub = QLabel("Operational transaction counts, net units, recognized revenue, and net collections attributed to original sale cashiers.")
        sub.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 500; border: none;")
        layout.addWidget(sub)

        # Cashier Table (7 Columns)
        self.cashier_table = QTableWidget()
        self.cashier_table.setColumnCount(7)
        self.cashier_table.setHorizontalHeaderLabels([
            "Cashier",
            "Completed Orders",
            "Net Units",
            "Net Sales",
            "Net Collections",
            "Net AOV",
            "Discounts Handled",
        ])
        self.cashier_table.verticalHeader().setVisible(False)
        self.cashier_table.setAlternatingRowColors(True)
        self.cashier_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.cashier_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.cashier_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.cashier_table.setShowGrid(False)
        self.cashier_table.setMinimumHeight(200)
        self.cashier_table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                gridline-color: #f1f5f9;
                font-size: 12px;
                color: #0f172a;
            }
            QTableWidget::item {
                padding: 6px 10px;
                border-bottom: 1px solid #f1f5f9;
            }
            QTableWidget::item:selected {
                background-color: #f0fdf4;
                color: #0f172a;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #475569;
                font-weight: 700;
                font-size: 11px;
                border: none;
                border-bottom: 2px solid #e2e8f0;
                padding: 6px 10px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
        """)

        # Header sizing
        header = self.cashier_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)

        layout.addWidget(self.cashier_table)

        self._cashier_empty_lbl = QLabel("No cashier sales activity for this period.")
        self._cashier_empty_lbl.setStyleSheet("font-size: 12px; color: #94a3b8; font-style: italic; border: none; padding: 20px 0;")
        self._cashier_empty_lbl.setAlignment(Qt.AlignCenter)
        self._cashier_empty_lbl.setVisible(False)
        layout.addWidget(self._cashier_empty_lbl)

        self._content_layout.addWidget(card)

    # ── 8. Paired Analytical Row 3 (Inventory ↔ Purchasing) ──────────

    def _build_inventory_and_purchasing_section(self):
        self._inventory_card = self._build_inventory_snapshot_card()
        self._purchasing_card = self._build_purchasing_intake_card()

        self._inv_purch_container = QWidget()
        self._inv_purch_layout = QHBoxLayout(self._inv_purch_container)
        self._inv_purch_layout.setContentsMargins(0, 0, 0, 0)
        self._inv_purch_layout.setSpacing(14)

        self._inv_purch_layout.addWidget(self._inventory_card, 1)
        self._inv_purch_layout.addWidget(self._purchasing_card, 1)

        self._content_layout.addWidget(self._inv_purch_container)

    def _build_inventory_snapshot_card(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        hdr = QLabel("Current Inventory Working Capital Valuation")
        hdr.setStyleSheet("font-size: 15px; font-weight: 800; color: #0f172a; border: none;")
        layout.addWidget(hdr)

        self.lbl_inv_caption = QLabel("Snapshot as of current system date. Reflects physical stock on hand across all active catalog products.")
        self.lbl_inv_caption.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 500; border: none;")
        layout.addWidget(self.lbl_inv_caption)

        # Metric Tiles Grid
        grid = QGridLayout()
        grid.setSpacing(10)

        self.lbl_inv_skus = QLabel("0")
        self.lbl_inv_units = QLabel("0")
        self.lbl_inv_cost = QLabel("₱0.00")
        self.lbl_inv_retail = QLabel("₱0.00")
        self.lbl_inv_spread = QLabel("₱0.00")

        tiles = [
            ("ACTIVE SKUS", self.lbl_inv_skus, "#0f172a", 0, 0),
            ("UNITS ON HAND", self.lbl_inv_units, "#0f172a", 0, 1),
            ("TOTAL COST VALUE", self.lbl_inv_cost, "#d97706", 1, 0),
            ("TOTAL RETAIL VALUE", self.lbl_inv_retail, "#2563eb", 1, 1),
            ("UNREALIZED MARGIN", self.lbl_inv_spread, "#059669", 2, 0),
        ]

        for title, val_lbl, color, r, c in tiles:
            tile = QFrame()
            tile.setStyleSheet("background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 4px;")
            tl = QVBoxLayout(tile)
            tl.setContentsMargins(8, 8, 8, 8)
            tl.setSpacing(4)

            t_lbl = QLabel(title)
            t_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748b; border: none; letter-spacing: 0.5px;")
            val_lbl.setStyleSheet(f"font-size: 15px; font-weight: 800; color: {color}; border: none;")

            tl.addWidget(t_lbl)
            tl.addWidget(val_lbl)

            if r == 2:
                grid.addWidget(tile, r, c, 1, 2)
            else:
                grid.addWidget(tile, r, c)

        layout.addLayout(grid)
        layout.addStretch(1)
        return frame

    def _build_purchasing_intake_card(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        hdr = QLabel("Received Purchasing Intake")
        hdr.setStyleSheet("font-size: 15px; font-weight: 800; color: #0f172a; border: none;")
        layout.addWidget(hdr)

        self.lbl_purch_caption = QLabel("Procurement inventory receipts are balance-sheet asset additions and are not deducted from operating profit.")
        self.lbl_purch_caption.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 500; border: none;")
        layout.addWidget(self.lbl_purch_caption)

        # Metric Tiles Grid
        grid = QGridLayout()
        grid.setSpacing(10)

        self.lbl_purch_orders = QLabel("0")
        self.lbl_purch_units = QLabel("0")
        self.lbl_purch_value = QLabel("₱0.00")

        tiles = [
            ("RECEIVED ORDERS", self.lbl_purch_orders, "#0f172a", 0, 0),
            ("UNITS RECEIVED", self.lbl_purch_units, "#0f172a", 0, 1),
            ("TOTAL INTAKE VALUE", self.lbl_purch_value, "#2563eb", 1, 0),
        ]

        for title, val_lbl, color, r, c in tiles:
            tile = QFrame()
            tile.setStyleSheet("background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 4px;")
            tl = QVBoxLayout(tile)
            tl.setContentsMargins(8, 8, 8, 8)
            tl.setSpacing(4)

            t_lbl = QLabel(title)
            t_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748b; border: none; letter-spacing: 0.5px;")
            val_lbl.setStyleSheet(f"font-size: 15px; font-weight: 800; color: {color}; border: none;")

            tl.addWidget(t_lbl)
            tl.addWidget(val_lbl)

            if r == 1:
                grid.addWidget(tile, r, c, 1, 2)
            else:
                grid.addWidget(tile, r, c)

        layout.addLayout(grid)
        layout.addStretch(1)
        return frame

    # ── Responsive Relayout ──────────────────────────────────────────

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        is_compact = self.width() < self.BREAKPOINT_WIDTH
        if is_compact != self._is_compact_layout:
            self._is_compact_layout = is_compact
            self._apply_responsive_layout(is_compact)

    def _apply_responsive_layout(self, is_compact: bool):
        """Rearrange existing widget instances between Wide (1x4) and Compact (2x2) layouts."""
        for c in self._kpi_cards:
            c.setParent(None)

        if is_compact:
            QWidget().setLayout(self._kpi_container.layout())
            grid = QGridLayout(self._kpi_container)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(12)
            grid.addWidget(self.card_net_sales, 0, 0)
            grid.addWidget(self.card_gross_profit, 0, 1)
            grid.addWidget(self.card_opex, 1, 0)
            grid.addWidget(self.card_net_operating_profit, 1, 1)

            self._analytical_layout.setDirection(QVBoxLayout.TopToBottom)
            self._tax_payment_layout.setDirection(QVBoxLayout.TopToBottom)
            self._inv_purch_layout.setDirection(QVBoxLayout.TopToBottom)
        else:
            QWidget().setLayout(self._kpi_container.layout())
            hbox = QHBoxLayout(self._kpi_container)
            hbox.setContentsMargins(0, 0, 0, 0)
            hbox.setSpacing(12)
            for c in self._kpi_cards:
                hbox.addWidget(c)

            self._analytical_layout.setDirection(QHBoxLayout.LeftToRight)
            self._tax_payment_layout.setDirection(QHBoxLayout.LeftToRight)
            self._inv_purch_layout.setDirection(QHBoxLayout.LeftToRight)

    # ── Centralized Data Orchestration ───────────────────────────────

    def _get_active_date_range(self) -> tuple[date, date]:
        """Compute start and end date based on active preset or custom pickers."""
        today = date.today()

        if self._active_preset == "today":
            return today, today
        elif self._active_preset == "yesterday":
            y = today - timedelta(days=1)
            return y, y
        elif self._active_preset == "last_7_days":
            return today - timedelta(days=6), today
        elif self._active_preset == "this_month":
            start = date(today.year, today.month, 1)
            return start, today
        elif self._active_preset == "last_month":
            first_this_month = date(today.year, today.month, 1)
            last_day_prev = first_this_month - timedelta(days=1)
            first_day_prev = date(last_day_prev.year, last_day_prev.month, 1)
            return first_day_prev, last_day_prev
        elif self._active_preset == "this_year":
            return date(today.year, 1, 1), today
        elif self._active_preset == "custom":
            start_q = self.dt_start.date()
            end_q = self.dt_end.date()
            start = date(start_q.year(), start_q.month(), start_q.day())
            end = date(end_q.year(), end_q.month(), end_q.day())
            if start > end:
                start = end
            return start, end
        return today, today

    def _reload_report_data(self):
        """Fetch report data atomically and bind to all presentation panels in one pass."""
        try:
            start_date, end_date = self._get_active_date_range()

            days_count = (end_date - start_date).days + 1
            self.lbl_active_period.setText(
                f"📅 Active Period: {start_date.strftime('%b %d, %Y')} – {end_date.strftime('%b %d, %Y')} ({days_count} {'Day' if days_count == 1 else 'Days'})"
            )

            # Atomic service fetch: retrieve all DTOs before updating UI state
            summary = self._report_service.get_financial_summary(
                start_date=start_date,
                end_date=end_date,
                actor=self._user,
            )
            trend_points = self._report_service.get_daily_financial_trend(
                start_date=start_date,
                end_date=end_date,
                actor=self._user,
            )
            opex_breakdown = self._report_service.get_expense_category_breakdown(
                start_date=start_date,
                end_date=end_date,
                actor=self._user,
            )
            payment_methods = self._report_service.get_payment_method_breakdown(
                start_date=start_date,
                end_date=end_date,
                actor=self._user,
            )
            refund_methods = self._report_service.get_refund_method_breakdown(
                start_date=start_date,
                end_date=end_date,
                actor=self._user,
            )
            products = self._report_service.get_product_performance(
                start_date=start_date,
                end_date=end_date,
                limit=10,
                actor=self._user,
            )
            cashiers = self._report_service.get_cashier_performance(
                start_date=start_date,
                end_date=end_date,
                actor=self._user,
            )
            purchasing = self._report_service.get_received_purchase_value(
                start_date=start_date,
                end_date=end_date,
                actor=self._user,
            )
            inventory = self._report_service.get_inventory_value(
                actor=self._user,
            )

            # Store in cached state
            self._current_summary = summary
            self._current_trend_points = trend_points
            self._current_opex_breakdown = opex_breakdown
            self._current_payment_methods = payment_methods
            self._current_refund_methods = refund_methods
            self._current_products = products
            self._current_cashiers = cashiers
            self._current_purchasing = purchasing
            self._current_inventory = inventory

            # Atomic Binding Pass
            self._bind_kpis(summary)
            self.chart_widget.set_data(trend_points)
            self._bind_pnl(summary)
            self._bind_opex_breakdown(opex_breakdown)
            self._bind_tax_tender(summary)
            self._bind_payment_methods(payment_methods)
            self._bind_refund_methods(refund_methods)
            self._bind_product_performance(products)
            self._bind_cashier_performance(cashiers)
            self._bind_inventory_snapshot(inventory)
            self._bind_purchasing_intake(purchasing)

        except (AuthorizationError, ValidationError) as e:
            self._toast.show_toast(str(e), "error")
        except Exception:
            self._toast.show_toast("Failed to load financial report data.", "error")

    # ── Data Binding Methods ─────────────────────────────────────────

    @staticmethod
    def _format_currency(val: Decimal) -> str:
        """Format decimal to standard Philippine Peso currency with accounting negative formatting."""
        if val < Decimal("0.00"):
            return f"-₱{abs(val):,.2f}"
        return f"₱{val:,.2f}"

    def _bind_kpis(self, summary: FinancialSummaryDTO):
        # 1. Net Sales
        self.card_net_sales.set_value(self._format_currency(summary.net_sales))
        self.card_net_sales.set_caption(f"Gross {self._format_currency(summary.gross_sales)} · Disc -₱{summary.discounts:,.2f} · Ret -₱{summary.sales_returns:,.2f}")

        # 2. Gross Profit
        self.card_gross_profit.set_value(self._format_currency(summary.gross_profit))
        self.card_gross_profit.set_caption(f"Gross Margin: {summary.gross_margin_percent:.1f}% · Net COGS -₱{summary.cogs:,.2f}")
        if summary.gross_profit < Decimal("0.00"):
            self.card_gross_profit._value_label.setStyleSheet("color: #dc2626; font-size: 26px; font-weight: 800; letter-spacing: -0.5px;")
        else:
            self.card_gross_profit._value_label.setStyleSheet("color: #059669; font-size: 26px; font-weight: 800; letter-spacing: -0.5px;")

        # 3. OPEX
        self.card_opex.set_value(self._format_currency(summary.operating_expenses))
        self.card_opex.set_caption("Active Overhead Disbursements")

        # 4. Net Operating Profit
        self.card_net_operating_profit.set_value(self._format_currency(summary.net_operating_profit))
        self.card_net_operating_profit.set_caption(f"Operating Margin: {summary.net_operating_margin_percent:.1f}%")
        if summary.net_operating_profit < Decimal("0.00"):
            self.card_net_operating_profit._value_label.setStyleSheet("color: #dc2626; font-size: 26px; font-weight: 800; letter-spacing: -0.5px;")
        else:
            self.card_net_operating_profit._value_label.setStyleSheet("color: #7c3aed; font-size: 26px; font-weight: 800; letter-spacing: -0.5px;")

    def _bind_pnl(self, summary: FinancialSummaryDTO):
        self._pnl_rows["gross_sales"][1].setText(self._format_currency(summary.gross_sales))
        self._pnl_rows["discounts"][1].setText(f"-₱{summary.discounts:,.2f}")
        self._pnl_rows["sales_returns"][1].setText(f"-₱{summary.sales_returns:,.2f}")
        self._pnl_rows["net_sales"][1].setText(self._format_currency(summary.net_sales))
        self._pnl_rows["cogs"][1].setText(f"-₱{summary.cogs:,.2f}")
        self._pnl_rows["gross_profit"][1].setText(self._format_currency(summary.gross_profit))
        self._pnl_rows["gross_margin"][1].setText(f"{summary.gross_margin_percent:.1f}%")
        self._pnl_rows["opex"][1].setText(f"-₱{summary.operating_expenses:,.2f}")
        self._pnl_rows["net_operating_profit"][1].setText(self._format_currency(summary.net_operating_profit))
        self._pnl_rows["net_operating_margin"][1].setText(f"{summary.net_operating_margin_percent:.1f}%")

        # Negative profit color handling
        gp_color = "#dc2626" if summary.gross_profit < Decimal("0.00") else "#059669"
        self._pnl_rows["gross_profit"][1].setStyleSheet(f"font-size: 14px; font-weight: 800; color: {gp_color}; border: none;")

        np_color = "#dc2626" if summary.net_operating_profit < Decimal("0.00") else "#7c3aed"
        self._pnl_rows["net_operating_profit"][1].setStyleSheet(f"font-size: 15px; font-weight: 800; color: {np_color}; border: none;")

    def _bind_opex_breakdown(self, breakdown: List[ExpenseCategoryBreakdownDTO]):
        while self._opex_list_layout.count() > 1:
            item = self._opex_list_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        if not breakdown:
            self._opex_empty_lbl.setVisible(True)
            return

        self._opex_empty_lbl.setVisible(False)

        for item in breakdown:
            row_widget = QWidget()
            row_layout = QVBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.setSpacing(3)

            top_h = QHBoxLayout()
            cat_name = QLabel(item.category_display)
            cat_name.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155; border: none;")

            amt_lbl = QLabel(f"₱{item.amount:,.2f} ({item.percentage:.1f}%)")
            amt_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #0f172a; border: none;")
            amt_lbl.setAlignment(Qt.AlignRight)

            top_h.addWidget(cat_name)
            top_h.addStretch(1)
            top_h.addWidget(amt_lbl)
            row_layout.addLayout(top_h)

            bar_track = QFrame()
            bar_track.setFixedHeight(5)
            bar_track.setStyleSheet("background-color: #f1f5f9; border-radius: 2px; border: none;")
            track_l = QHBoxLayout(bar_track)
            track_l.setContentsMargins(0, 0, 0, 0)
            track_l.setSpacing(0)

            pct_int = max(0, min(100, int(item.percentage)))
            if pct_int > 0:
                fill = QFrame()
                fill.setFixedHeight(5)
                fill.setStyleSheet("background-color: #d97706; border-radius: 2px; border: none;")
                track_l.addWidget(fill, stretch=pct_int)
            if pct_int < 100:
                track_l.addStretch(100 - pct_int)

            row_layout.addWidget(bar_track)
            self._opex_list_layout.addWidget(row_widget)

    def _bind_tax_tender(self, summary: FinancialSummaryDTO):
        self.lbl_gross_vat_val.setText(f"₱{summary.gross_output_vat:,.2f}")
        self.lbl_vat_reversals_val.setText(f"-₱{summary.vat_reversals:,.2f}")
        self.lbl_net_vat_val.setText(self._format_currency(summary.net_output_vat))

        self.lbl_collections_val.setText(f"₱{summary.total_collections:,.2f}")
        self.lbl_refunds_val.setText(f"-₱{summary.refunds_issued:,.2f}")
        self.lbl_net_collections_val.setText(self._format_currency(summary.net_collections))

    def _bind_payment_methods(self, methods: List[PaymentMethodSummaryDTO]):
        while self._payment_list_layout.count() > 1:
            item = self._payment_list_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        if not methods:
            self._payment_empty_lbl.setVisible(True)
            return

        self._payment_empty_lbl.setVisible(False)

        for item in methods:
            row_widget = QWidget()
            row_layout = QVBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.setSpacing(3)

            top_h = QHBoxLayout()
            method_lbl = QLabel(item.payment_method_display)
            method_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155; border: none;")

            amt_lbl = QLabel(f"{item.transaction_count} txns  ·  ₱{item.total_amount:,.2f} ({item.percentage:.1f}%)")
            amt_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #0f172a; border: none;")
            amt_lbl.setAlignment(Qt.AlignRight)

            top_h.addWidget(method_lbl)
            top_h.addStretch(1)
            top_h.addWidget(amt_lbl)
            row_layout.addLayout(top_h)

            bar_track = QFrame()
            bar_track.setFixedHeight(5)
            bar_track.setStyleSheet("background-color: #f1f5f9; border-radius: 2px; border: none;")
            track_l = QHBoxLayout(bar_track)
            track_l.setContentsMargins(0, 0, 0, 0)
            track_l.setSpacing(0)

            pct_int = max(0, min(100, int(item.percentage)))
            if pct_int > 0:
                fill = QFrame()
                fill.setFixedHeight(5)
                fill.setStyleSheet("background-color: #2563eb; border-radius: 2px; border: none;")
                track_l.addWidget(fill, stretch=pct_int)
            if pct_int < 100:
                track_l.addStretch(100 - pct_int)

            row_layout.addWidget(bar_track)
            self._payment_list_layout.addWidget(row_widget)

    def _bind_refund_methods(self, refunds: List[RefundMethodSummaryDTO]):
        while self._refund_list_layout.count() > 1:
            item = self._refund_list_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        if not refunds:
            self._refund_empty_lbl.setVisible(True)
            return

        self._refund_empty_lbl.setVisible(False)

        for ref in refunds:
            row_widget = QWidget()
            row_layout = QVBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.setSpacing(3)

            top_h = QHBoxLayout()
            ref_lbl = QLabel(ref.refund_method_display)
            ref_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155; border: none;")

            amt_lbl = QLabel(f"{ref.return_count} ret  ·  ₱{ref.total_refund_amount:,.2f} ({ref.percentage:.1f}%)")
            amt_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #dc2626; border: none;")
            amt_lbl.setAlignment(Qt.AlignRight)

            top_h.addWidget(ref_lbl)
            top_h.addStretch(1)
            top_h.addWidget(amt_lbl)
            row_layout.addLayout(top_h)

            bar_track = QFrame()
            bar_track.setFixedHeight(5)
            bar_track.setStyleSheet("background-color: #f1f5f9; border-radius: 2px; border: none;")
            track_l = QHBoxLayout(bar_track)
            track_l.setContentsMargins(0, 0, 0, 0)
            track_l.setSpacing(0)

            pct_int = max(0, min(100, int(ref.percentage)))
            if pct_int > 0:
                fill = QFrame()
                fill.setFixedHeight(5)
                fill.setStyleSheet("background-color: #dc2626; border-radius: 2px; border: none;")
                track_l.addWidget(fill, stretch=pct_int)
            if pct_int < 100:
                track_l.addStretch(100 - pct_int)

            row_layout.addWidget(bar_track)
            self._refund_list_layout.addWidget(row_widget)

    def _bind_product_performance(self, products: List[ProductPerformanceDTO]):
        self.product_table.setRowCount(0)

        if not products:
            self.product_table.setVisible(False)
            self._product_empty_lbl.setVisible(True)
            return

        self.product_table.setVisible(True)
        self._product_empty_lbl.setVisible(False)
        self.product_table.setRowCount(len(products))

        for row_idx, p in enumerate(products):
            # Rank
            rank_item = QTableWidgetItem(f"#{row_idx + 1}")
            rank_item.setTextAlignment(Qt.AlignCenter)
            rank_item.setForeground(QColor("#475569"))
            rank_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            self.product_table.setItem(row_idx, 0, rank_item)

            # Product / SKU
            prod_item = QTableWidgetItem(f"{p.product_name}\n({p.sku})")
            prod_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            prod_item.setForeground(QColor("#0f172a"))
            prod_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            prod_item.setToolTip(f"{p.product_name} [{p.sku}]")
            self.product_table.setItem(row_idx, 1, prod_item)

            # Net Units
            units_item = QTableWidgetItem(f"{p.net_units_sold:,}")
            units_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            units_item.setForeground(QColor("#334155"))
            self.product_table.setItem(row_idx, 2, units_item)

            # Net Gross Revenue
            rev_item = QTableWidgetItem(self._format_currency(p.net_gross_revenue))
            rev_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            rev_item.setForeground(QColor("#0f172a"))
            rev_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            self.product_table.setItem(row_idx, 3, rev_item)

            # Net Historical COGS
            cogs_item = QTableWidgetItem(f"-₱{p.net_historical_cogs:,.2f}" if p.net_historical_cogs >= 0 else f"₱{abs(p.net_historical_cogs):,.2f}")
            cogs_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            cogs_item.setForeground(QColor("#dc2626"))
            self.product_table.setItem(row_idx, 4, cogs_item)

            # Direct Contribution Margin
            contrib_val = p.direct_margin
            contrib_color = "#dc2626" if contrib_val < Decimal("0.00") else "#059669"
            contrib_item = QTableWidgetItem(self._format_currency(contrib_val))
            contrib_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            contrib_item.setForeground(QColor(contrib_color))
            contrib_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            self.product_table.setItem(row_idx, 5, contrib_item)

        self.product_table.resizeRowsToContents()

    def _bind_cashier_performance(self, cashiers: List[CashierPerformanceDTO]):
        self.cashier_table.setRowCount(0)

        if not cashiers:
            self.cashier_table.setVisible(False)
            self._cashier_empty_lbl.setVisible(True)
            return

        self.cashier_table.setVisible(True)
        self._cashier_empty_lbl.setVisible(False)
        self.cashier_table.setRowCount(len(cashiers))

        for row_idx, c in enumerate(cashiers):
            # Cashier Name
            name_item = QTableWidgetItem(c.cashier_name)
            name_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            name_item.setForeground(QColor("#0f172a"))
            name_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            name_item.setToolTip(c.cashier_name)
            self.cashier_table.setItem(row_idx, 0, name_item)

            # Completed Orders
            orders_item = QTableWidgetItem(f"{c.transaction_count:,}")
            orders_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            orders_item.setForeground(QColor("#334155"))
            self.cashier_table.setItem(row_idx, 1, orders_item)

            # Net Units
            units_item = QTableWidgetItem(f"{c.net_units:,}")
            units_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            units_item.setForeground(QColor("#334155"))
            self.cashier_table.setItem(row_idx, 2, units_item)

            # Net Sales
            sales_item = QTableWidgetItem(self._format_currency(c.net_sales))
            sales_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            sales_item.setForeground(QColor("#2563eb"))
            sales_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            self.cashier_table.setItem(row_idx, 3, sales_item)

            # Net Collections
            net_col_item = QTableWidgetItem(self._format_currency(c.net_collections))
            net_col_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            net_col_item.setForeground(QColor("#0f172a"))
            net_col_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            self.cashier_table.setItem(row_idx, 4, net_col_item)

            # Net AOV
            aov_item = QTableWidgetItem(f"₱{c.average_order_value:,.2f}")
            aov_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            aov_item.setForeground(QColor("#475569"))
            self.cashier_table.setItem(row_idx, 5, aov_item)

            # Discounts Handled
            disc_item = QTableWidgetItem(f"-₱{c.discounts:,.2f}")
            disc_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            disc_item.setForeground(QColor("#dc2626"))
            self.cashier_table.setItem(row_idx, 6, disc_item)

        self.cashier_table.resizeRowsToContents()

    def _bind_inventory_snapshot(self, inventory: InventoryValueDTO):
        self.lbl_inv_skus.setText(f"{inventory.total_products:,}")
        self.lbl_inv_units.setText(f"{inventory.total_units_on_hand:,}")
        self.lbl_inv_cost.setText(f"₱{inventory.current_cost_value:,.2f}")
        self.lbl_inv_retail.setText(f"₱{inventory.current_retail_value:,.2f}")
        self.lbl_inv_spread.setText(f"₱{inventory.potential_unrealized_margin:,.2f}")

    def _bind_purchasing_intake(self, intake: PurchaseIntakeSummaryDTO):
        self.lbl_purch_orders.setText(f"{intake.received_order_count:,}")
        self.lbl_purch_units.setText(f"{intake.total_units_received:,}")
        self.lbl_purch_value.setText(f"₱{intake.received_purchase_value:,.2f}")
