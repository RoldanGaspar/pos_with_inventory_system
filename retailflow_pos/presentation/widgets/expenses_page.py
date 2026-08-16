"""
RetailFlow POS - Store Operating Expenses Workstation Page
Provides real-time tracking of operating costs, category breakdowns, disbursement voucher feeds,
and modal workflows for recording, editing metadata, and soft-voiding expenses.
"""

from decimal import Decimal
from typing import Optional

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
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

from app.constants import (
    EXPENSE_CATEGORY_LABELS,
    ExpenseCategory,
    ExpenseStatus,
    PaymentMethod,
)
from application.dto.expense_dto import ExpenseFilterDTO, ExpenseResponseDTO
from application.services.expense_service import ExpenseService
from infrastructure.database.models.auth import User
from presentation.dialogs.expense_dialog import ExpenseDialog
from presentation.dialogs.void_expense_dialog import VoidExpenseDialog
from presentation.styles.icons import IconManager
from presentation.widgets.metric_card import MetricCardWidget
from presentation.widgets.toast_notification import ToastNotification


class ExpensesPage(QWidget):
    """Store operating expenses management workstation."""

    def __init__(
        self,
        current_user: User,
        expense_service: ExpenseService,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._user = current_user
        self._expense_service = expense_service
        self._expenses_list: list[ExpenseResponseDTO] = []
        self._page = 1
        self._page_size = 15
        self._total = 0
        self._active_category_chip = "all"

        # Search debounce timer
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._perform_search)

        self._init_ui()
        self.load_expenses()

    def _has_permission(self, code: str) -> bool:
        if not self._user:
            return False
        if hasattr(self._user, "is_admin") and self._user.is_admin():
            return True
        return self._user.has_permission(code)

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

        title_lbl = QLabel("Expenses")
        title_lbl.setStyleSheet("font-size: 22px; font-weight: 800; color: #0f172a; letter-spacing: -0.4px;")
        header_layout.addWidget(title_lbl)

        subtitle_lbl = QLabel("Track store overhead, operating costs, and expense disbursement vouchers.")
        subtitle_lbl.setStyleSheet("font-size: 13px; color: #64748b; font-weight: 500;")
        header_layout.addWidget(subtitle_lbl)

        hdr_row.addLayout(header_layout)
        hdr_row.addStretch()

        btn_refresh = QPushButton(" Refresh")
        btn_refresh.setIcon(IconManager.get_icon("clock", color="#475569", size=13))
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
        btn_refresh.clicked.connect(self.load_expenses)
        hdr_row.addWidget(btn_refresh)

        self.btn_new_expense = QPushButton(" + Record Expense")
        self.btn_new_expense.setIcon(IconManager.get_icon("plus", color="#ffffff", size=14))
        self.btn_new_expense.setFixedHeight(36)
        self.btn_new_expense.setCursor(Qt.PointingHandCursor)
        self.btn_new_expense.setStyleSheet("""
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
            QPushButton:disabled {
                background-color: #94a3b8;
            }
        """)
        can_create = self._has_permission("create_expenses")
        self.btn_new_expense.setEnabled(can_create)
        self.btn_new_expense.clicked.connect(self._open_new_expense_dialog)
        hdr_row.addWidget(self.btn_new_expense)

        main_layout.addLayout(hdr_row)

        # ── 2. Summary KPI Metric Cards Grid ──
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(12)

        self.card_total = MetricCardWidget(
            title="TOTAL EXPENSES (₱)",
            icon_name="expenses",
            accent_color="#2563eb",
            badge_bg="#eff6ff",
        )
        self.card_month = MetricCardWidget(
            title="THIS MONTH'S SPEND",
            icon_name="clock",
            accent_color="#7c3aed",
            badge_bg="#f3e8ff",
        )
        self.card_top_cat = MetricCardWidget(
            title="TOP EXPENSE CATEGORY",
            icon_name="dashboard",
            accent_color="#d97706",
            badge_bg="#fffbeb",
        )
        self.card_vouchers = MetricCardWidget(
            title="ACTIVE VOUCHERS",
            icon_name="check",
            accent_color="#059669",
            badge_bg="#ecfdf5",
        )

        for card in [self.card_total, self.card_month, self.card_top_cat, self.card_vouchers]:
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

        # Row 1: Search LineEdit + Status Dropdown + Payment Method Dropdown + Clear Filters
        top_filter_row = QHBoxLayout()
        top_filter_row.setSpacing(10)

        self.txt_search = QLineEdit()
        self.txt_search.addAction(IconManager.get_icon("search", color="#64748b", size=16), QLineEdit.LeadingPosition)
        self.txt_search.setPlaceholderText("Search by voucher #, title, payee, or reference #...")
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
        self.txt_search.textChanged.connect(self._on_search_text_changed)
        top_filter_row.addWidget(self.txt_search, 2)

        # Status Dropdown
        self.cmb_status = QComboBox()
        self.cmb_status.addItem("All Statuses", "all")
        self.cmb_status.addItem("PAID (Active)", ExpenseStatus.PAID.value)
        self.cmb_status.addItem("VOID (Cancelled)", ExpenseStatus.VOID.value)
        self.cmb_status.setFixedHeight(36)
        self.cmb_status.setStyleSheet("""
            QComboBox {
                padding: 4px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background-color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                color: #334155;
                min-width: 140px;
            }
            QComboBox:focus { border-color: #2563eb; }
        """)
        self.cmb_status.currentIndexChanged.connect(self._on_filter_changed)
        top_filter_row.addWidget(self.cmb_status)

        # Payment Method Dropdown
        self.cmb_payment = QComboBox()
        self.cmb_payment.addItem("All Payment Methods", "all")
        expense_payment_methods = [
            (PaymentMethod.CASH, "Cash"),
            (PaymentMethod.BANK_TRANSFER, "Bank Transfer"),
            (PaymentMethod.GCASH, "GCash"),
            (PaymentMethod.MAYA, "Maya"),
            (PaymentMethod.CREDIT_CARD, "Credit Card"),
            (PaymentMethod.DEBIT_CARD, "Debit Card"),
            (PaymentMethod.CHECK, "Check"),
        ]
        for method_enum, method_label in expense_payment_methods:
            self.cmb_payment.addItem(method_label, method_enum.value)
        self.cmb_payment.setFixedHeight(36)
        self.cmb_payment.setStyleSheet("""
            QComboBox {
                padding: 4px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background-color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                color: #334155;
                min-width: 150px;
            }
            QComboBox:focus { border-color: #2563eb; }
        """)
        self.cmb_payment.currentIndexChanged.connect(self._on_filter_changed)
        top_filter_row.addWidget(self.cmb_payment)

        self.btn_clear_filters = QPushButton("Clear")
        self.btn_clear_filters.setFixedHeight(36)
        self.btn_clear_filters.setCursor(Qt.PointingHandCursor)
        self.btn_clear_filters.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 600;
                padding: 0px 12px;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
                color: #0f172a;
            }
        """)
        self.btn_clear_filters.clicked.connect(self._clear_filters)
        self.btn_clear_filters.setVisible(False)
        top_filter_row.addWidget(self.btn_clear_filters)

        v_toolbar.addLayout(top_filter_row)

        # Row 2: Category Quick Filter Chips
        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)

        self._chip_buttons = {}
        categories_chips = [
            ("all", "All Expenses"),
            (ExpenseCategory.UTILITIES.value, "Utilities"),
            (ExpenseCategory.RENT.value, "Store Rent"),
            (ExpenseCategory.SALARIES.value, "Staff Wages"),
            (ExpenseCategory.SUPPLIES.value, "Supplies"),
            (ExpenseCategory.MAINTENANCE.value, "Maintenance"),
            (ExpenseCategory.TAXES_LICENSES.value, "Taxes & Permits"),
            (ExpenseCategory.MARKETING.value, "Marketing"),
            (ExpenseCategory.OTHER.value, "Other"),
        ]

        for cat_key, cat_label in categories_chips:
            btn = QPushButton(cat_label)
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, k=cat_key: self._on_chip_clicked(k))
            self._chip_buttons[cat_key] = btn
            chips_row.addWidget(btn)

        chips_row.addStretch()
        v_toolbar.addLayout(chips_row)

        self._update_chip_styles()
        main_layout.addWidget(toolbar_card)

        # ── 4. Expenses Table Feed ──
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Voucher #",
            "Category",
            "Expense & Payee",
            "Date",
            "Payment / Reference",
            "Amount",
            "Status",
            "Actions",
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                gridline-color: #f1f5f9;
                font-size: 13px;
                color: #0f172a;
            }
            QTableWidget::item {
                padding: 8px 10px;
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
                padding: 8px 10px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
        """)

        # Column Sizing & Alignment
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Voucher #
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Category
        header.setSectionResizeMode(2, QHeaderView.Stretch)           # Expense & Payee
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Date
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Payment / Ref
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Amount
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Status
        header.setSectionResizeMode(7, QHeaderView.Fixed)             # Actions
        self.table.setColumnWidth(7, 150)

        main_layout.addWidget(self.table, 1)

        # Empty State Placeholder (Overlay frame)
        self.empty_frame = QFrame(self.table)
        self.empty_frame.setStyleSheet("background: transparent; border: none;")
        empty_layout = QVBoxLayout(self.empty_frame)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_layout.setSpacing(8)

        self.empty_icon = QLabel()
        self.empty_icon.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.empty_icon)

        self.empty_title = QLabel("No Expenses Found")
        self.empty_title.setAlignment(Qt.AlignCenter)
        self.empty_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #475569;")
        empty_layout.addWidget(self.empty_title)

        self.empty_sub = QLabel("No operating expenses match your selected filters.")
        self.empty_sub.setAlignment(Qt.AlignCenter)
        self.empty_sub.setStyleSheet("font-size: 12px; color: #94a3b8; font-weight: 500;")
        empty_layout.addWidget(self.empty_sub)

        self.empty_frame.setVisible(False)

        # ── 5. Pagination Footer ──
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(4, 0, 4, 0)

        self.lbl_pagination_info = QLabel("Showing 0 of 0 vouchers")
        self.lbl_pagination_info.setStyleSheet("font-size: 12px; color: #64748b; font-weight: 500;")
        footer_layout.addWidget(self.lbl_pagination_info)

        footer_layout.addStretch()

        self.btn_prev = QPushButton("◀ Previous")
        self.btn_prev.setFixedHeight(32)
        self.btn_prev.setCursor(Qt.PointingHandCursor)
        self.btn_prev.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 600;
                padding: 0 12px;
            }
            QPushButton:hover { background-color: #f1f5f9; color: #0f172a; }
            QPushButton:disabled { color: #cbd5e1; border-color: #e2e8f0; background-color: #f8fafc; }
        """)
        self.btn_prev.clicked.connect(self._prev_page)
        footer_layout.addWidget(self.btn_prev)

        self.lbl_page_number = QLabel("Page 1 of 1")
        self.lbl_page_number.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155; padding: 0 8px;")
        footer_layout.addWidget(self.lbl_page_number)

        self.btn_next = QPushButton("Next ▶")
        self.btn_next.setFixedHeight(32)
        self.btn_next.setCursor(Qt.PointingHandCursor)
        self.btn_next.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 600;
                padding: 0 12px;
            }
            QPushButton:hover { background-color: #f1f5f9; color: #0f172a; }
            QPushButton:disabled { color: #cbd5e1; border-color: #e2e8f0; background-color: #f8fafc; }
        """)
        self.btn_next.clicked.connect(self._next_page)
        footer_layout.addWidget(self.btn_next)

        main_layout.addLayout(footer_layout)

    # ─── Data Loading & Queries ───

    def load_expenses(self):
        """Fetch summary KPI metrics and paginated expenses list."""
        self._refresh_kpi_cards()
        self._fetch_table_data()

    def _refresh_kpi_cards(self):
        """Update top 4 KPI stat cards from service."""
        try:
            metrics = self._expense_service.get_expense_metrics(actor=self._user)
            self.card_total.set_value(f"₱{metrics.total_expenses:,.2f}")
            self.card_total.set_caption("Lifetime active disbursements")

            self.card_month.set_value(f"₱{metrics.this_month_spend:,.2f}")
            self.card_month.set_caption("Current month (MTD)")

            self.card_top_cat.set_value(metrics.top_category_display)
            self.card_top_cat.set_caption("Primary cost driver this month")

            self.card_vouchers.set_value(str(metrics.active_vouchers_count))
            self.card_vouchers.set_caption("Paid disbursement vouchers")
        except Exception:
            self.card_total.set_value("₱0.00")
            self.card_month.set_value("₱0.00")
            self.card_top_cat.set_value("—")
            self.card_vouchers.set_value("0")

    def _fetch_table_data(self):
        """Perform search query via ExpenseService and populate table."""
        keyword = self.txt_search.text().strip() or None
        category = self._active_category_chip if self._active_category_chip != "all" else None
        status = self.cmb_status.currentData() if self.cmb_status.currentData() != "all" else None
        payment_method = self.cmb_payment.currentData() if self.cmb_payment.currentData() != "all" else None

        filters = ExpenseFilterDTO(
            keyword=keyword,
            category=category,
            status=status,
            payment_method=payment_method,
            page=self._page,
            page_size=self._page_size,
        )

        has_filters = bool(keyword or category or status or payment_method)
        self.btn_clear_filters.setVisible(has_filters)

        try:
            result = self._expense_service.search_expenses(filters, actor=self._user)
            self._expenses_list = result.items
            self._total = result.total
            self._render_table_rows()
            self._update_pagination_ui()
        except Exception as e:
            self._toast.show_toast(f"Failed to fetch expenses: {e}", "error")

    def _render_table_rows(self):
        """Render expense rows into QTableWidget."""
        self.table.setRowCount(len(self._expenses_list))

        if len(self._expenses_list) == 0:
            self._show_empty_state()
            return
        else:
            self.empty_frame.setVisible(False)

        for row_idx, exp in enumerate(self._expenses_list):
            is_void = exp.status.lower() == ExpenseStatus.VOID.value

            # 0. Voucher Number
            v_item = QTableWidgetItem(exp.voucher_number)
            v_font = QFont("Consolas, Courier New, monospace")
            v_font.setBold(True)
            v_item.setFont(v_font)
            v_item.setForeground(QColor("#64748b" if is_void else "#1e40af"))
            self.table.setItem(row_idx, 0, v_item)

            # 1. Category Badge
            cat_widget = self._create_category_badge(exp.category, exp.category_display, is_void)
            self.table.setCellWidget(row_idx, 1, cat_widget)

            # 2. Expense Title & Payee (Stacked Cell Widget)
            title_widget = self._create_title_payee_cell(exp.title, exp.payee, is_void)
            self.table.setCellWidget(row_idx, 2, title_widget)

            # 3. Disbursement Date
            date_item = QTableWidgetItem(exp.expense_date)
            date_item.setForeground(QColor("#64748b" if is_void else "#334155"))
            self.table.setItem(row_idx, 3, date_item)

            # 4. Payment Method & Reference #
            pay_ref_text = exp.payment_method_display
            if exp.reference_number:
                pay_ref_text += f"\n{exp.reference_number}"
            pay_item = QTableWidgetItem(pay_ref_text)
            pay_item.setForeground(QColor("#64748b"))
            self.table.setItem(row_idx, 4, pay_item)

            # 5. Formatted Amount (₱)
            amt_item = QTableWidgetItem(f"₱{exp.amount:,.2f}")
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            amt_font = QFont()
            amt_font.setBold(True)
            amt_item.setFont(amt_font)
            amt_item.setForeground(QColor("#94a3b8" if is_void else "#0f172a"))
            self.table.setItem(row_idx, 5, amt_item)

            # 6. Status Badge
            status_widget = self._create_status_badge(exp.status)
            self.table.setCellWidget(row_idx, 6, status_widget)

            # 7. Actions Container
            actions_widget = self._create_actions_widget(exp)
            self.table.setCellWidget(row_idx, 7, actions_widget)

            self.table.setRowHeight(row_idx, 46)

    def _create_category_badge(self, cat_key: str, cat_label: str, is_void: bool) -> QWidget:
        """Create category badge cell widget."""
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)

        lbl = QLabel(cat_label)
        if is_void:
            bg_color, text_color = "#f1f5f9", "#94a3b8"
        elif cat_key == ExpenseCategory.UTILITIES.value:
            bg_color, text_color = "#eff6ff", "#1e40af"
        elif cat_key == ExpenseCategory.RENT.value:
            bg_color, text_color = "#f5f3ff", "#6b21a8"
        elif cat_key == ExpenseCategory.SALARIES.value:
            bg_color, text_color = "#ecfdf5", "#065f46"
        elif cat_key == ExpenseCategory.SUPPLIES.value:
            bg_color, text_color = "#fffbeb", "#92400e"
        elif cat_key == ExpenseCategory.MAINTENANCE.value:
            bg_color, text_color = "#fef2f2", "#991b1b"
        elif cat_key == ExpenseCategory.TAXES_LICENSES.value:
            bg_color, text_color = "#f0fdfa", "#115e59"
        elif cat_key == ExpenseCategory.MARKETING.value:
            bg_color, text_color = "#fdf2f8", "#9d174d"
        else:
            bg_color, text_color = "#f8fafc", "#475569"

        lbl.setStyleSheet(f"""
            background-color: {bg_color};
            color: {text_color};
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
            padding: 3px 8px;
        """)
        layout.addWidget(lbl)
        layout.addStretch()
        return w

    def _create_title_payee_cell(self, title: str, payee: str, is_void: bool) -> QWidget:
        """Create stacked title and payee name cell widget."""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(1)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {'#94a3b8' if is_void else '#0f172a'};")
        layout.addWidget(lbl_title)

        lbl_payee = QLabel(payee)
        lbl_payee.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 500;")
        layout.addWidget(lbl_payee)

        return w

    def _create_status_badge(self, status: str) -> QWidget:
        """Create status pill badge."""
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)

        lbl = QLabel(status.upper())
        if status.lower() == ExpenseStatus.VOID.value:
            bg_color, text_color = "#fee2e2", "#dc2626"
        else:
            bg_color, text_color = "#dcfce7", "#15803d"

        lbl.setStyleSheet(f"""
            background-color: {bg_color};
            color: {text_color};
            border-radius: 4px;
            font-size: 11px;
            font-weight: 800;
            padding: 3px 8px;
        """)
        layout.addWidget(lbl)
        layout.addStretch()
        return w

    def _create_actions_widget(self, exp: ExpenseResponseDTO) -> QWidget:
        """Build permission-aware action buttons for row."""
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        is_paid = exp.status.lower() == ExpenseStatus.PAID.value
        can_edit = self._has_permission("edit_expenses")
        can_void = self._has_permission("void_expenses")

        if is_paid and (can_edit or can_void):
            if can_edit:
                btn_edit = QPushButton("Edit")
                btn_edit.setCursor(Qt.PointingHandCursor)
                btn_edit.setFixedHeight(26)
                btn_edit.setStyleSheet("""
                    QPushButton {
                        background-color: #f1f5f9;
                        color: #1e293b;
                        border: 1px solid #cbd5e1;
                        border-radius: 4px;
                        font-size: 11px;
                        font-weight: 600;
                        padding: 0 8px;
                    }
                    QPushButton:hover { background-color: #e2e8f0; color: #2563eb; }
                """)
                btn_edit.clicked.connect(lambda _, e=exp: self._open_edit_expense_dialog(e))
                layout.addWidget(btn_edit)

            if can_void:
                btn_void = QPushButton("Void")
                btn_void.setCursor(Qt.PointingHandCursor)
                btn_void.setFixedHeight(26)
                btn_void.setStyleSheet("""
                    QPushButton {
                        background-color: #ffffff;
                        color: #dc2626;
                        border: 1px solid #fca5a5;
                        border-radius: 4px;
                        font-size: 11px;
                        font-weight: 700;
                        padding: 0 8px;
                    }
                    QPushButton:hover { background-color: #fee2e2; color: #991b1b; }
                """)
                btn_void.clicked.connect(lambda _, e=exp: self._open_void_expense_dialog(e))
                layout.addWidget(btn_void)

        else:
            # View Only Action
            btn_view = QPushButton("View")
            btn_view.setCursor(Qt.PointingHandCursor)
            btn_view.setFixedHeight(26)
            btn_view.setStyleSheet("""
                QPushButton {
                    background-color: #f8fafc;
                    color: #475569;
                    border: 1px solid #cbd5e1;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: 600;
                    padding: 0 10px;
                }
                QPushButton:hover { background-color: #f1f5f9; color: #0f172a; }
            """)
            btn_view.clicked.connect(lambda _, e=exp: self._open_view_expense_dialog(e))
            layout.addWidget(btn_view)

        layout.addStretch()
        return w

    def _show_empty_state(self):
        """Position and render empty state frame."""
        has_filters = bool(
            self.txt_search.text().strip()
            or self._active_category_chip != "all"
            or self.cmb_status.currentData() != "all"
            or self.cmb_payment.currentData() != "all"
        )
        if has_filters:
            self.empty_title.setText("No Matching Expenses")
            self.empty_sub.setText("No operating expense vouchers match your active filter criteria.")
        else:
            self.empty_title.setText("No Operating Expenses Recorded")
            self.empty_sub.setText("Click '+ Record Expense' to issue your first store disbursement voucher.")

        self.empty_icon.setPixmap(IconManager.get_pixmap("expenses", color="#94a3b8", size=42))
        self.empty_frame.setGeometry(self.table.rect())
        self.empty_frame.setVisible(True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "empty_frame") and self.empty_frame.isVisible():
            self.empty_frame.setGeometry(self.table.rect())

    # ─── Filter Events ───

    def _on_search_text_changed(self):
        """Restart debounce timer when user types in search box."""
        self._search_timer.start()

    def _perform_search(self):
        """Execute search after debounce timer expires."""
        self._page = 1
        self._fetch_table_data()

    def _on_chip_clicked(self, category_key: str):
        """Handle category filter chip toggle."""
        self._active_category_chip = category_key
        self._update_chip_styles()
        self._page = 1
        self._fetch_table_data()

    def _update_chip_styles(self):
        """Highlight active category chip and uncheck others."""
        for key, btn in self._chip_buttons.items():
            is_active = key == self._active_category_chip
            btn.setChecked(is_active)
            if is_active:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2563eb;
                        color: #ffffff;
                        border: none;
                        border-radius: 14px;
                        font-size: 11px;
                        font-weight: 700;
                        padding: 0 12px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #ffffff;
                        color: #475569;
                        border: 1px solid #cbd5e1;
                        border-radius: 14px;
                        font-size: 11px;
                        font-weight: 600;
                        padding: 0 12px;
                    }
                    QPushButton:hover {
                        background-color: #f1f5f9;
                        color: #0f172a;
                    }
                """)

    def _on_filter_changed(self):
        """Handle dropdown filter selection change."""
        self._page = 1
        self._fetch_table_data()

    def _clear_filters(self):
        """Reset all search and dropdown filter controls."""
        self.txt_search.blockSignals(True)
        self.txt_search.clear()
        self.txt_search.blockSignals(False)

        self._active_category_chip = "all"
        self._update_chip_styles()

        self.cmb_status.blockSignals(True)
        self.cmb_status.setCurrentIndex(0)
        self.cmb_status.blockSignals(False)

        self.cmb_payment.blockSignals(True)
        self.cmb_payment.setCurrentIndex(0)
        self.cmb_payment.blockSignals(False)

        self._page = 1
        self._fetch_table_data()

    # ─── Pagination Controls ───

    def _update_pagination_ui(self):
        """Update pagination counter and button states."""
        total_pages = max(1, (self._total + self._page_size - 1) // self._page_size)
        start_idx = 0 if self._total == 0 else (self._page - 1) * self._page_size + 1
        end_idx = min(self._total, self._page * self._page_size)

        self.lbl_pagination_info.setText(f"Showing {start_idx}-{end_idx} of {self._total} vouchers")
        self.lbl_page_number.setText(f"Page {self._page} of {total_pages}")

        self.btn_prev.setEnabled(self._page > 1)
        self.btn_next.setEnabled(self._page < total_pages)

    def _prev_page(self):
        if self._page > 1:
            self._page -= 1
            self._fetch_table_data()

    def _next_page(self):
        total_pages = (self._total + self._page_size - 1) // self._page_size
        if self._page < total_pages:
            self._page += 1
            self._fetch_table_data()

    # ─── Modal Dialog Openers ───

    def _open_new_expense_dialog(self):
        """Open ExpenseDialog in Create Mode."""
        dialog = ExpenseDialog(
            expense_service=self._expense_service,
            current_actor=self._user,
            parent=self,
        )
        if dialog.exec() == QDialog.Accepted and dialog.result_dto:
            self._page = 1
            self.load_expenses()
            self._toast.show_toast(
                f"Expense voucher {dialog.result_dto.voucher_number} recorded successfully.", "success"
            )

    def _open_edit_expense_dialog(self, exp: ExpenseResponseDTO):
        """Open ExpenseDialog in Edit Metadata Mode."""
        dialog = ExpenseDialog(
            expense_service=self._expense_service,
            current_actor=self._user,
            expense_data=exp,
            parent=self,
        )
        if dialog.exec() == QDialog.Accepted and dialog.result_dto:
            self._fetch_table_data()
            self._toast.show_toast(
                f"Metadata for {dialog.result_dto.voucher_number} updated successfully.", "success"
            )

    def _open_void_expense_dialog(self, exp: ExpenseResponseDTO):
        """Open VoidExpenseDialog for soft-cancellation."""
        dialog = VoidExpenseDialog(
            expense_service=self._expense_service,
            current_actor=self._user,
            expense_data=exp,
            parent=self,
        )
        if dialog.exec() == QDialog.Accepted and dialog.result_dto:
            self.load_expenses()
            self._toast.show_toast(
                f"Voucher {dialog.result_dto.voucher_number} voided successfully.", "warning"
            )

    def _open_view_expense_dialog(self, exp: ExpenseResponseDTO):
        """Open ExpenseDialog in View/Read-Only Mode."""
        dialog = ExpenseDialog(
            expense_service=self._expense_service,
            current_actor=self._user,
            expense_data=exp,
            view_only=True,
            parent=self,
        )
        dialog.exec()
