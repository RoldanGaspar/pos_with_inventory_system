"""
RetailFlow POS - POS Checkout Workstation Page
High-speed cashier terminal interface with live product search, vector scanner badge,
filter chips, interactive cart steppers, customer selector card, discount modal,
quick cash tender shortcuts, hold/resume orders, and F12 checkout controls.
"""

from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from application.dto.product_dto import ProductFilterDTO
from application.dto.sales_dto import CartItemDTO, CartSummaryDTO, CheckoutRequestDTO
from application.services.product_service import ProductService
from application.services.sales_service import SalesService
from domain.exceptions import DomainError
from infrastructure.database.models.auth import User
from presentation.dialogs.discount_dialog import DiscountDialog
from presentation.dialogs.payment_dialog import PaymentDialog
from presentation.dialogs.sale_success_dialog import SaleSuccessDialog
from presentation.styles.icons import IconManager
from presentation.widgets.toast_notification import ToastNotification


class POSPage(QWidget):
    """Point of Sale cashier workstation terminal widget."""

    sale_completed = Signal(str)  # transaction_number

    def __init__(
        self,
        current_user: User | None,
        product_service: ProductService,
        sales_service: SalesService,
        parent=None,
    ):
        super().__init__(parent)
        self._user = current_user
        self._product_service = product_service
        self._sales_service = sales_service

        self._cart_items: dict[int, CartItemDTO] = {}
        self._discount_amount: Decimal = Decimal("0.00")
        self._customer_name: str = "Walk-in Customer"
        self._held_orders: list[dict[int, CartItemDTO]] = []
        self._active_chip: str = "all"  # all, favorites, recent

        self._init_ui()
        self.load_products()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # ─── LEFT PANE: Product Catalog & Search ───
        left_pane = QFrame()
        left_pane.setObjectName("posLeftPane")
        left_pane.setStyleSheet("""
            QFrame#posLeftPane {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                padding: 12px;
            }
        """)
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # Header with Title + Scanner Badge
        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(0, 0, 0, 0)

        catalog_header = QLabel("Product Catalog")
        catalog_header.setObjectName("catalogHeader")
        catalog_header.setStyleSheet("font-size: 15px; font-weight: 800; color: #0f172a;")
        hdr_row.addWidget(catalog_header)

        hdr_row.addStretch()

        # Embedded Scanner Active Badge
        scanner_badge = QWidget()
        scanner_badge.setFixedHeight(28)
        scanner_badge_layout = QHBoxLayout(scanner_badge)
        scanner_badge_layout.setContentsMargins(8, 2, 8, 2)
        scanner_badge_layout.setSpacing(5)

        scanner_icon = QLabel()
        scanner_icon.setPixmap(IconManager.get_pixmap("barcode", color="#059669", size=13))
        scanner_badge_layout.addWidget(scanner_icon)

        scanner_txt = QLabel("● Scanner Active")
        scanner_txt.setStyleSheet("color: #047857; font-size: 10px; font-weight: 800;")
        scanner_badge_layout.addWidget(scanner_txt)

        scanner_badge.setStyleSheet("""
            QWidget {
                background-color: #ecfdf5;
                border-radius: 6px;
                border: 1px solid #a7f3d0;
            }
        """)
        hdr_row.addWidget(scanner_badge)
        left_layout.addLayout(hdr_row)

        # Search Bar + Category Dropdown Toolbar
        search_layout = QHBoxLayout()
        search_layout.setSpacing(8)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search product name / SKU / Scan barcode  ·  F2")
        self.txt_search.addAction(IconManager.get_icon("search", color="#64748b", size=16), QLineEdit.LeadingPosition)
        self.txt_search.setObjectName("posSearchInput")
        self.txt_search.setFixedHeight(36)
        self.txt_search.textChanged.connect(self.load_products)
        self.txt_search.returnPressed.connect(self._on_search_enter)
        search_layout.addWidget(self.txt_search, stretch=3)

        # Category Filter Dropdown
        self.cmb_category = QComboBox()
        self.cmb_category.addItem("All Categories", None)
        self.cmb_category.setFixedHeight(36)
        self.cmb_category.setStyleSheet("""
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
        self.cmb_category.currentIndexChanged.connect(self.load_products)
        search_layout.addWidget(self.cmb_category, stretch=1)

        left_layout.addLayout(search_layout)

        # Quick Catalog Chips Bar (All | Favorites | Recent)
        chips_layout = QHBoxLayout()
        chips_layout.setSpacing(6)
        chips_layout.setContentsMargins(0, 0, 0, 2)

        self.btn_chip_all = QPushButton(" All Products")
        self.btn_chip_fav = QPushButton(" Favorites ⭐")
        self.btn_chip_rec = QPushButton(" Recent")

        for chip_btn, mode in [(self.btn_chip_all, "all"), (self.btn_chip_fav, "favorites"), (self.btn_chip_rec, "recent")]:
            chip_btn.setCursor(Qt.PointingHandCursor)
            chip_btn.setFixedHeight(28)
            chip_btn.clicked.connect(lambda chk, m=mode: self._set_catalog_chip(m))
            chips_layout.addWidget(chip_btn)

        chips_layout.addStretch()
        left_layout.addLayout(chips_layout)
        self._update_chip_styles()

        # Keyboard Shortcuts
        self._f2_shortcut = QShortcut(QKeySequence("F2"), self)
        self._f2_shortcut.activated.connect(self._focus_search)

        self._f4_shortcut = QShortcut(QKeySequence("F4"), self)
        self._f4_shortcut.activated.connect(self._select_customer)

        self._f8_shortcut = QShortcut(QKeySequence("F8"), self)
        self._f8_shortcut.activated.connect(self._hold_order)

        self._f12_shortcut = QShortcut(QKeySequence("F12"), self)
        self._f12_shortcut.activated.connect(self.open_checkout)

        # Products Table Grid
        self.tbl_products = QTableWidget()
        self.tbl_products.setColumnCount(5)
        self.tbl_products.setHorizontalHeaderLabels(["SKU", "PRODUCT NAME", "PRICE", "STOCK", ""])

        self.tbl_products.verticalHeader().setVisible(False)
        self.tbl_products.setAlternatingRowColors(True)
        self.tbl_products.setShowGrid(False)
        self.tbl_products.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
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

        header = self.tbl_products.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.tbl_products.setColumnWidth(3, 100)
        self.tbl_products.setColumnWidth(4, 75)

        self.tbl_products.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_products.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_products.doubleClicked.connect(self._on_product_double_clicked)
        left_layout.addWidget(self.tbl_products)

        main_layout.addWidget(left_pane, stretch=3)

        # ─── RIGHT PANE: Cart & Checkout Workstation ───
        right_pane = QFrame()
        right_pane.setObjectName("posRightPane")
        right_pane.setMinimumWidth(380)
        right_pane.setStyleSheet("""
            QFrame#posRightPane {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                padding: 12px;
            }
        """)
        right_layout = QVBoxLayout(right_pane)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # 1. Top Cart Header
        cart_header_layout = QHBoxLayout()
        cart_title = QLabel("Current Order")
        cart_title.setObjectName("cartTitle")
        cart_title.setStyleSheet("font-size: 15px; font-weight: 800; color: #0f172a;")
        cart_header_layout.addWidget(cart_title)

        self.lbl_item_count = QLabel("0 Items")
        self.lbl_item_count.setStyleSheet("""
            font-size: 11px;
            font-weight: 800;
            color: #2563eb;
            background-color: #eff6ff;
            padding: 2px 8px;
            border-radius: 10px;
            border: 1px solid #bfdbfe;
        """)
        cart_header_layout.addWidget(self.lbl_item_count)

        cart_header_layout.addStretch()

        # Secondary Held Orders Link
        self.btn_held_orders = QPushButton(" Held Orders (0)")
        self.btn_held_orders.setIcon(IconManager.get_pixmap("pause", color="#64748b", size=12))
        self.btn_held_orders.setCursor(Qt.PointingHandCursor)
        self.btn_held_orders.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #64748b;
                font-size: 11px;
                font-weight: 700;
                border: none;
                padding: 2px 4px;
            }
            QPushButton:hover {
                color: #d97706;
                text-decoration: underline;
            }
        """)
        self.btn_held_orders.clicked.connect(self._resume_held_order)
        cart_header_layout.addWidget(self.btn_held_orders)
        right_layout.addLayout(cart_header_layout)

        # 2. Rich Empty Cart Overlay
        self.empty_cart_widget = QWidget()
        self.empty_cart_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        empty_layout = QVBoxLayout(self.empty_cart_widget)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_layout.setSpacing(6)

        empty_icon = QLabel()
        empty_icon.setPixmap(IconManager.get_pixmap("pos", color="#cbd5e1", size=40))
        empty_icon.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_icon)

        empty_title = QLabel("Start a new sale")
        empty_title.setAlignment(Qt.AlignCenter)
        empty_title.setStyleSheet("font-size: 14px; font-weight: 800; color: #0f172a; border: none; background: transparent;")
        empty_layout.addWidget(empty_title)

        empty_hint = QLabel("Scan barcode or click '+ Add' on catalog items")
        empty_hint.setAlignment(Qt.AlignCenter)
        empty_hint.setStyleSheet("font-size: 11px; color: #64748b; border: none; background: transparent;")
        empty_layout.addWidget(empty_hint)

        shortcuts_label = QLabel("F2 Search  ·  F4 Customer  ·  F8 Hold  ·  F12 Pay")
        shortcuts_label.setAlignment(Qt.AlignCenter)
        shortcuts_label.setStyleSheet("""
            font-size: 10px;
            font-weight: 700;
            color: #94a3b8;
            background-color: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 4px 10px;
            margin-top: 6px;
        """)
        empty_layout.addWidget(shortcuts_label)

        right_layout.addWidget(self.empty_cart_widget, stretch=1)

        # 3. Middle Cart Table Grid
        self.tbl_cart = QTableWidget()
        self.tbl_cart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tbl_cart.setColumnCount(5)
        self.tbl_cart.setHorizontalHeaderLabels(["PRODUCT", "PRICE", "QTY", "SUBTOTAL", ""])

        self.tbl_cart.verticalHeader().setVisible(False)
        self.tbl_cart.setShowGrid(False)
        self.tbl_cart.setWordWrap(True)
        self.tbl_cart.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
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
                padding: 6px 8px;
            }
            QTableWidget::item {
                padding: 4px 6px;
                border-bottom: 1px solid #f1f5f9;
            }
        """)

        cart_header = self.tbl_cart.horizontalHeader()
        cart_header.setSectionResizeMode(0, QHeaderView.Stretch)
        cart_header.setSectionResizeMode(1, QHeaderView.Fixed)
        cart_header.setSectionResizeMode(2, QHeaderView.Fixed)
        cart_header.setSectionResizeMode(3, QHeaderView.Fixed)
        cart_header.setSectionResizeMode(4, QHeaderView.Fixed)

        self.tbl_cart.setColumnWidth(1, 75)
        self.tbl_cart.setColumnWidth(2, 90)
        self.tbl_cart.setColumnWidth(3, 80)
        self.tbl_cart.setColumnWidth(4, 28)

        self.tbl_cart.setEditTriggers(QTableWidget.NoEditTriggers)
        right_layout.addWidget(self.tbl_cart, stretch=1)
        self.tbl_cart.hide()

        # 4. Pinned Bottom Workstation Summary Footer
        bottom_footer_widget = QWidget()
        bottom_footer_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        bottom_footer_layout = QVBoxLayout(bottom_footer_widget)
        bottom_footer_layout.setContentsMargins(0, 0, 0, 0)
        bottom_footer_layout.setSpacing(6)

        # Unified Customer Card Row
        cust_frame = QFrame()
        cust_frame.setCursor(Qt.PointingHandCursor)
        cust_frame.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 6px 10px;
            }
            QFrame:hover {
                background-color: #f1f5f9;
                border-color: #cbd5e1;
            }
        """)
        cust_layout = QHBoxLayout(cust_frame)
        cust_layout.setContentsMargins(0, 0, 0, 0)

        cust_icon = QLabel()
        cust_icon.setPixmap(IconManager.get_pixmap("customers", color="#475569", size=15))
        cust_layout.addWidget(cust_icon)

        self.lbl_customer = QLabel(self._customer_name)
        self.lbl_customer.setStyleSheet("color: #0f172a; font-size: 12px; font-weight: 700;")
        cust_layout.addWidget(self.lbl_customer, stretch=1)

        cust_arrow = QLabel()
        cust_arrow.setPixmap(IconManager.get_pixmap("chevron_right", color="#94a3b8", size=12))
        cust_layout.addWidget(cust_arrow)

        cust_frame.mousePressEvent = lambda ev: self._select_customer()
        bottom_footer_layout.addWidget(cust_frame)

        # Order Summary Container Card
        summary_frame = QFrame()
        summary_frame.setObjectName("posSummaryFrame")
        summary_frame.setStyleSheet("""
            QFrame#posSummaryFrame {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 8px 10px;
            }
        """)
        summary_layout = QVBoxLayout(summary_frame)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(4)

        # Subtotal Row
        subtotal_row = QHBoxLayout()
        subtotal_lbl = QLabel("Subtotal:")
        subtotal_lbl.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 500;")
        subtotal_row.addWidget(subtotal_lbl)

        self.lbl_subtotal = QLabel("₱0.00")
        self.lbl_subtotal.setStyleSheet("color: #0f172a; font-size: 12px; font-weight: 700;")
        self.lbl_subtotal.setAlignment(Qt.AlignRight)
        subtotal_row.addWidget(self.lbl_subtotal)
        summary_layout.addLayout(subtotal_row)

        # Tax Row
        tax_row = QHBoxLayout()
        tax_lbl = QLabel("Tax (12% VAT):")
        tax_lbl.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 500;")
        tax_row.addWidget(tax_lbl)

        self.lbl_tax = QLabel("₱0.00")
        self.lbl_tax.setStyleSheet("color: #0f172a; font-size: 12px; font-weight: 700;")
        self.lbl_tax.setAlignment(Qt.AlignRight)
        tax_row.addWidget(self.lbl_tax)
        summary_layout.addLayout(tax_row)

        # Discount Selector Row
        discount_frame = QFrame()
        discount_frame.setCursor(Qt.PointingHandCursor)
        discount_frame.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
            }
            QFrame:hover QLabel#discVal {
                color: #2563eb;
                text-decoration: underline;
            }
        """)
        discount_row = QHBoxLayout(discount_frame)
        discount_row.setContentsMargins(0, 0, 0, 0)
        discount_row.setSpacing(4)

        disc_icon = QLabel()
        disc_icon.setPixmap(IconManager.get_pixmap("tag", color="#64748b", size=13))
        discount_row.addWidget(disc_icon)

        disc_lbl = QLabel("Discount:")
        disc_lbl.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 500;")
        discount_row.addWidget(disc_lbl)

        self.lbl_discount_val = QLabel("None")
        self.lbl_discount_val.setObjectName("discVal")
        self.lbl_discount_val.setStyleSheet("color: #0f172a; font-size: 11px; font-weight: 700;")
        self.lbl_discount_val.setAlignment(Qt.AlignRight)
        discount_row.addWidget(self.lbl_discount_val, stretch=1)

        disc_arrow = QLabel()
        disc_arrow.setPixmap(IconManager.get_pixmap("chevron_right", color="#94a3b8", size=12))
        discount_row.addWidget(disc_arrow)

        discount_frame.mousePressEvent = lambda ev: self._open_discount_dialog()

        # Hidden spinbox for backward compatibility with existing tests
        self.spn_discount = QDoubleSpinBox()
        self.spn_discount.setRange(0, 999999)
        self.spn_discount.hide()
        self.spn_discount.valueChanged.connect(self._on_discount_changed)

        summary_layout.addWidget(discount_frame)

        # Thin Divider
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: #e2e8f0; border: none; margin: 3px 0px;")
        summary_layout.addWidget(divider)

        # Hero Dominant "TOTAL DUE" Banner
        total_card = QFrame()
        total_card.setObjectName("posTotalCard")
        total_card.setStyleSheet("""
            QFrame#posTotalCard {
                background-color: #ecfdf5;
                border: 1px solid #a7f3d0;
                border-radius: 8px;
                padding: 6px 12px;
            }
        """)
        total_layout = QHBoxLayout(total_card)
        total_layout.setContentsMargins(0, 0, 0, 0)

        total_lbl = QLabel("TOTAL DUE")
        total_lbl.setObjectName("posTotalLabel")
        total_lbl.setStyleSheet("font-size: 11px; font-weight: 800; color: #065f46; letter-spacing: 0.5px;")
        total_layout.addWidget(total_lbl)

        self.lbl_total = QLabel("₱0.00")
        self.lbl_total.setObjectName("posTotalAmount")
        self.lbl_total.setStyleSheet("font-size: 24px; font-weight: 800; color: #047857; letter-spacing: -0.5px;")
        self.lbl_total.setAlignment(Qt.AlignRight)
        total_layout.addWidget(self.lbl_total)

        summary_layout.addWidget(total_card)
        bottom_footer_layout.addWidget(summary_frame)

        # Cashier Quick Cash Tender Shortcuts Bar
        quick_tender_layout = QHBoxLayout()
        quick_tender_layout.setSpacing(5)

        for amt_label in ["Exact", "₱50", "₱100", "₱500", "₱1,000"]:
            btn_q = QPushButton(amt_label)
            btn_q.setProperty("class", "quickCashPill")
            btn_q.setCursor(Qt.PointingHandCursor)
            btn_q.setFixedHeight(26)
            btn_q.clicked.connect(self.open_checkout)
            quick_tender_layout.addWidget(btn_q)

        bottom_footer_layout.addLayout(quick_tender_layout)

        # Action Bar (Hold + Clear Order + Primary Action PAY Button)
        action_bar = QHBoxLayout()
        action_bar.setSpacing(6)

        btn_hold = QPushButton(" Hold (F8)")
        btn_hold.setIcon(IconManager.get_pixmap("pause", color="#d97706", size=13))
        btn_hold.setFixedHeight(38)
        btn_hold.setCursor(Qt.PointingHandCursor)
        btn_hold.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #d97706;
                border: 1px solid #fde68a;
                border-radius: 8px;
                font-size: 11px;
                font-weight: 700;
                padding: 0px 8px;
            }
            QPushButton:hover {
                background-color: #fffbeb;
                border-color: #f59e0b;
            }
        """)
        btn_hold.clicked.connect(self._hold_order)
        action_bar.addWidget(btn_hold)

        self.btn_clear = QPushButton(" Clear")
        self.btn_clear.setIcon(IconManager.get_pixmap("trash", color="#dc2626", size=13))
        self.btn_clear.setFixedHeight(38)
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #dc2626;
                border: 1px solid #fca5a5;
                border-radius: 8px;
                font-size: 11px;
                font-weight: 700;
                padding: 0px 8px;
            }
            QPushButton:hover {
                background-color: #fef2f2;
                border-color: #ef4444;
            }
        """)
        self.btn_clear.clicked.connect(self.clear_cart)
        action_bar.addWidget(self.btn_clear)

        self.btn_checkout = QPushButton(" CHARGE ₱0.00 (F12) →")
        self.btn_checkout.setIcon(IconManager.get_pixmap("check", color="#ffffff", size=15))
        self.btn_checkout.setObjectName("btnCheckout")
        self.btn_checkout.setFixedHeight(38)
        self.btn_checkout.setCursor(Qt.PointingHandCursor)
        self.btn_checkout.clicked.connect(self.open_checkout)
        action_bar.addWidget(self.btn_checkout, stretch=1)

        bottom_footer_layout.addLayout(action_bar)
        right_layout.addWidget(bottom_footer_widget, stretch=0)

        main_layout.addWidget(right_pane, stretch=2)

        # Toast Notification overlay
        self._toast = ToastNotification(right_pane)

        self._update_cart_display()
        self._populate_categories()

    def _set_catalog_chip(self, mode: str):
        self._active_chip = mode
        self._update_chip_styles()
        self.load_products()

    def _update_chip_styles(self):
        chips = [
            (self.btn_chip_all, "all"),
            (self.btn_chip_fav, "favorites"),
            (self.btn_chip_rec, "recent"),
        ]
        for btn, mode in chips:
            is_active = self._active_chip == mode
            if is_active:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2563eb;
                        color: #ffffff;
                        border: none;
                        border-radius: 14px;
                        font-size: 11px;
                        font-weight: 700;
                        padding: 0px 12px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f1f5f9;
                        color: #475569;
                        border: 1px solid #e2e8f0;
                        border-radius: 14px;
                        font-size: 11px;
                        font-weight: 600;
                        padding: 0px 12px;
                    }
                    QPushButton:hover {
                        background-color: #e2e8f0;
                        color: #0f172a;
                    }
                """)

    def _focus_search(self):
        """F2 shortcut handler."""
        self.txt_search.setFocus()
        self.txt_search.selectAll()

    def _select_customer(self):
        """F4 shortcut or Customer card handler."""
        text, ok = QInputDialog.getText(self, "Select Customer", "Enter customer name / loyalty ID:", text=self._customer_name)
        if ok and text.strip():
            self._customer_name = text.strip()
            self.lbl_customer.setText(self._customer_name)

    def _open_discount_dialog(self):
        """Open discount modal."""
        subtotal = sum((item.subtotal for item in self._cart_items.values()), Decimal("0.00"))
        dlg = DiscountDialog(subtotal=subtotal, current_discount=self._discount_amount, parent=self)
        if dlg.exec() == DiscountDialog.Accepted:
            self._discount_amount = dlg.applied_discount
            self.spn_discount.setValue(float(self._discount_amount))
            self._update_cart_display()

    def _hold_order(self):
        """F8 shortcut or Hold Order handler."""
        if not self._cart_items:
            self._toast.show_toast("Cart is empty. Nothing to hold.", is_error=True)
            return

        self._held_orders.append(dict(self._cart_items))
        self._cart_items.clear()
        self.btn_held_orders.setText(f" Held Orders ({len(self._held_orders)})")
        self._update_cart_display()
        self._toast.show_toast(f"Order held successfully ({len(self._held_orders)} held)")

    def _resume_held_order(self):
        """Resume last held order."""
        if not self._held_orders:
            self._toast.show_toast("No held orders available.")
            return

        held_cart = self._held_orders.pop()
        self._cart_items = held_cart
        self.btn_held_orders.setText(f" Held Orders ({len(self._held_orders)})")
        self._update_cart_display()
        self._toast.show_toast("Restored held order!")

    def _populate_categories(self):
        try:
            options = self._product_service.get_form_options(self._user)
            for cat in options.categories:
                self.cmb_category.addItem(cat.name, cat.id)
        except Exception:
            pass

    def load_products(self):
        """Fetch and render products matching search filter."""
        try:
            keyword = self.txt_search.text().strip() or None
            category_id = self.cmb_category.currentData()
            filters = ProductFilterDTO(keyword=keyword, category_id=category_id, page_size=50)

            result = self._product_service.search(filters, self._user)
            self.tbl_products.setRowCount(len(result.items))

            dark_color = QColor("#0f172a")

            for row, p in enumerate(result.items):
                self.tbl_products.setRowHeight(row, 44)

                # Store product object on first item (Required for tests)
                sku_item = QTableWidgetItem(p.sku)
                sku_item.setForeground(QColor("#64748b"))
                sku_item.setFont(QFont("Consolas", 10))
                sku_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                sku_item.setData(Qt.UserRole, p)
                self.tbl_products.setItem(row, 0, sku_item)

                name_item = QTableWidgetItem(p.name)
                name_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                name_item.setForeground(dark_color)
                name_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.tbl_products.setItem(row, 1, name_item)

                price_item = QTableWidgetItem(f"₱{p.selling_price:,.2f}")
                price_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                price_item.setForeground(dark_color)
                price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tbl_products.setItem(row, 2, price_item)

                # Live Stock Badge Widget
                stock_widget = QLabel()
                stock_widget.setAlignment(Qt.AlignCenter)
                if p.stock_quantity == 0:
                    stock_widget.setText("Out of stock")
                    stock_widget.setStyleSheet("color: #dc2626; font-size: 10px; font-weight: 800; background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 2px 6px;")
                elif p.stock_quantity <= 10:
                    stock_widget.setText(f"● {p.stock_quantity} left")
                    stock_widget.setStyleSheet("color: #d97706; font-size: 10px; font-weight: 800; background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 2px 6px;")
                else:
                    stock_widget.setText(f"● {p.stock_quantity} in stock")
                    stock_widget.setStyleSheet("color: #047857; font-size: 10px; font-weight: 800; background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px; padding: 2px 6px;")

                self.tbl_products.setCellWidget(row, 3, stock_widget)

                # Action Button: "+ Add" button (Required for tests)
                if p.stock_quantity > 0:
                    add_btn = QPushButton("+ Add")
                    add_btn.setFixedSize(58, 28)
                    add_btn.setCursor(Qt.PointingHandCursor)
                    add_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #2563eb;
                            color: #ffffff;
                            border: none;
                            border-radius: 6px;
                            font-size: 11px;
                            font-weight: 800;
                        }
                        QPushButton:hover { background-color: #1d4ed8; }
                    """)
                    add_btn.clicked.connect(lambda checked, item=p: self.add_to_cart(item))
                    self.tbl_products.setCellWidget(row, 4, add_btn)
                else:
                    sold_out_lbl = QLabel("Sold Out")
                    sold_out_lbl.setAlignment(Qt.AlignCenter)
                    sold_out_lbl.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 700;")
                    self.tbl_products.setCellWidget(row, 4, sold_out_lbl)

        except DomainError as exc:
            self._toast.show_toast(str(exc), is_error=True)

    def _on_product_double_clicked(self, index):
        """Add product to cart on row double-click."""
        row = index.row()
        item = self.tbl_products.item(row, 0)
        if item:
            product = item.data(Qt.UserRole)
            if product and product.stock_quantity > 0:
                self.add_to_cart(product)

    def _on_search_enter(self):
        """Auto-add exact SKU or Barcode match on Enter key in search field."""
        search_text = self.txt_search.text().strip()
        if not search_text:
            return

        for row in range(self.tbl_products.rowCount()):
            item = self.tbl_products.item(row, 0)
            if item:
                product = item.data(Qt.UserRole)
                if product and (product.sku.lower() == search_text.lower() or product.barcode == search_text):
                    if product.stock_quantity > 0:
                        self.add_to_cart(product)
                        self.txt_search.clear()
                        return
                    else:
                        self._toast.show_toast(f"'{product.name}' is out of stock.", is_error=True)
                        return

    def add_to_cart(self, product):
        """Add product or increment quantity in cart."""
        pid = product.id
        current_qty = self._cart_items[pid].quantity if pid in self._cart_items else 0
        new_qty = current_qty + 1

        if new_qty > product.stock_quantity:
            self._toast.show_toast(f"Cannot add more '{product.name}'. Max stock is {product.stock_quantity}.", is_error=True)
            return

        self._cart_items[pid] = CartItemDTO(
            product_id=product.id,
            sku=product.sku,
            name=product.name,
            unit_price=product.selling_price,
            quantity=new_qty,
            available_stock=product.stock_quantity,
        )

        self._update_cart_display()
        self._toast.show_toast(f"Added '{product.name}' to order")

    def _on_qty_changed(self, product_id: int, new_qty: int):
        """Handle inline [-] Qty [+] control value change."""
        if product_id not in self._cart_items:
            return

        if new_qty <= 0:
            self.remove_from_cart(product_id)
            return

        item = self._cart_items[product_id]
        if new_qty > item.available_stock:
            self._toast.show_toast(f"Cannot exceed available stock ({item.available_stock}).", is_error=True)
            return

        self._cart_items[product_id] = CartItemDTO(
            product_id=item.product_id,
            sku=item.sku,
            name=item.name,
            unit_price=item.unit_price,
            quantity=new_qty,
            available_stock=item.available_stock,
        )
        self._update_cart_display()

    def remove_from_cart(self, product_id: int):
        """Remove item from cart completely."""
        if product_id in self._cart_items:
            removed = self._cart_items.pop(product_id)
            self._update_cart_display()
            self._toast.show_toast(f"Removed '{removed.name}' from order")

    def clear_cart(self):
        """Clear all items from current cart."""
        self._cart_items.clear()
        self.spn_discount.setValue(0.0)
        self._discount_amount = Decimal("0.00")
        self._update_cart_display()

    def _on_discount_changed(self, val: float):
        self._discount_amount = Decimal(str(val))
        self._update_cart_display()

    def _update_cart_display(self):
        """Render cart table with inline quantity steppers and update subtotal, tax, and totals."""
        subtotal = sum((item.subtotal for item in self._cart_items.values()), Decimal("0.00"))
        taxable = max(Decimal("0.00"), subtotal - self._discount_amount)
        tax = (taxable * Decimal("0.12")).quantize(Decimal("0.01"))
        total = max(Decimal("0.00"), subtotal - self._discount_amount + tax)
        total_items = sum(item.quantity for item in self._cart_items.values())

        has_items = total_items > 0
        self.empty_cart_widget.setVisible(not has_items)
        self.tbl_cart.setVisible(has_items)

        self.lbl_item_count.setText(f"{total_items} Items")
        self.lbl_subtotal.setText(f"₱{subtotal:.2f}")
        self.lbl_tax.setText(f"₱{tax:.2f}")
        self.lbl_total.setText(f"₱{total:.2f}")

        if self._discount_amount > 0:
            self.lbl_discount_val.setText(f"₱{self._discount_amount:.2f}")
        else:
            self.lbl_discount_val.setText("None")

        if has_items:
            self.btn_checkout.setText(f" CHARGE ₱{total:,.2f} (F12) →")
            self.btn_checkout.setEnabled(True)
        else:
            self.btn_checkout.setText(" CHARGE ₱0.00 (F12) →")
            self.btn_checkout.setEnabled(False)

        items_list = list(self._cart_items.values())
        self.tbl_cart.setRowCount(len(items_list))

        dark_color = QColor("#0f172a")

        for row, item in enumerate(items_list):
            self.tbl_cart.setRowHeight(row, 46)

            # Col 0: Product Info (Name + SKU subtext)
            info_widget = QWidget()
            info_layout = QVBoxLayout(info_widget)
            info_layout.setContentsMargins(4, 2, 4, 2)
            info_layout.setSpacing(1)

            name_lbl = QLabel(item.name)
            name_lbl.setStyleSheet("color: #0f172a; font-size: 12px; font-weight: 700;")
            info_layout.addWidget(name_lbl)

            sku_lbl = QLabel(f"SKU: {item.sku}")
            sku_lbl.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 500;")
            info_layout.addWidget(sku_lbl)

            self.tbl_cart.setCellWidget(row, 0, info_widget)

            # Col 1: Unit Price
            price_item = QTableWidgetItem(f"₱{item.unit_price:.2f}")
            price_item.setForeground(dark_color)
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tbl_cart.setItem(row, 1, price_item)

            # Col 2: Inline Stepper [-] Qty [+]
            qty_widget = QWidget()
            qty_layout = QHBoxLayout(qty_widget)
            qty_layout.setContentsMargins(0, 0, 0, 0)
            qty_layout.setSpacing(3)

            btn_minus = QPushButton("-")
            btn_minus.setProperty("class", "cartQtyBtn")
            btn_minus.setFixedSize(22, 22)
            btn_minus.setCursor(Qt.PointingHandCursor)
            btn_minus.clicked.connect(lambda checked, pid=item.product_id, q=item.quantity: self._on_qty_changed(pid, q - 1))
            qty_layout.addWidget(btn_minus)

            lbl_qty = QLabel(str(item.quantity))
            lbl_qty.setAlignment(Qt.AlignCenter)
            lbl_qty.setStyleSheet("font-weight: 800; color: #0f172a; font-size: 12px; min-width: 22px;")
            qty_layout.addWidget(lbl_qty)

            btn_plus = QPushButton("+")
            btn_plus.setProperty("class", "cartQtyBtn")
            btn_plus.setFixedSize(22, 22)
            btn_plus.setCursor(Qt.PointingHandCursor)
            btn_plus.clicked.connect(lambda checked, pid=item.product_id, q=item.quantity: self._on_qty_changed(pid, q + 1))
            qty_layout.addWidget(btn_plus)

            self.tbl_cart.setCellWidget(row, 2, qty_widget)

            # Col 3: Subtotal
            sub_item = QTableWidgetItem(f"₱{item.subtotal:.2f}")
            sub_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            sub_item.setForeground(dark_color)
            sub_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tbl_cart.setItem(row, 3, sub_item)

            # Col 4: Trash Delete Button
            btn_del = QPushButton()
            btn_del.setIcon(IconManager.get_pixmap("trash", color="#ef4444", size=13))
            btn_del.setFixedSize(22, 22)
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #fef2f2; }
            """)
            btn_del.clicked.connect(lambda checked, pid=item.product_id: self.remove_from_cart(pid))
            self.tbl_cart.setCellWidget(row, 4, btn_del)

    def open_checkout(self):
        """Open payment dialog and process checkout transaction."""
        if not self._cart_items:
            self._toast.show_toast("Cart is empty.", is_error=True)
            return

        subtotal = sum((item.subtotal for item in self._cart_items.values()), Decimal("0.00"))
        taxable = max(Decimal("0.00"), subtotal - self._discount_amount)
        tax = (taxable * Decimal("0.12")).quantize(Decimal("0.01"))
        total = max(Decimal("0.00"), subtotal - self._discount_amount + tax)

        dlg = PaymentDialog(
            total_amount=total,
            subtotal=subtotal,
            discount=self._discount_amount,
            tax=tax,
            parent=self,
        )

        if dlg.exec() == PaymentDialog.Accepted:
            try:
                req = CheckoutRequestDTO(
                    items=list(self._cart_items.values()),
                    discount_amount=self._discount_amount,
                    payment_method=dlg.payment_method,
                    amount_tendered=dlg.amount_tendered,
                    reference_number=dlg.reference_number,
                )
                res = self._sales_service.process_checkout(req, self._user)
                self.sale_completed.emit(res.transaction_number)

                self.clear_cart()
                self.load_products()

                success_dlg = SaleSuccessDialog(res, parent=self)
                success_dlg.exec()
            except DomainError as exc:
                self._toast.show_toast(str(exc), is_error=True)
            except Exception as exc:
                self._toast.show_toast(f"Unexpected error: {exc}", is_error=True)
