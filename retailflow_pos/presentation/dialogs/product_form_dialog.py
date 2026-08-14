"""
RetailFlow POS - Modern SaaS Product Form Dialog
Custom frameless tabbed modal for creating and editing catalog products.
Features Live Profit Margin Calculation, Barcode Auto-Generator, and Segmented Tabs.
"""

from decimal import Decimal
import random

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from application.dto.product_dto import ProductFormDTO
from application.services.product_service import ProductService
from domain.exceptions import RetailFlowError
from infrastructure.database.models.auth import User
from infrastructure.database.models.product import Brand, Category, Product
from presentation.styles.icons import IconManager

_TAX_TYPES = [
    ("VAT (12%)", "vat"),
    ("Non-VAT", "non_vat"),
    ("Zero-Rated", "zero_rated"),
    ("Exempt", "exempt"),
]

_STATUSES = [
    ("● Active", "active"),
    ("● Inactive", "inactive"),
]


class ProductFormDialog(QDialog):
    """Custom frameless tabbed SaaS/POS modal for creating and editing products."""

    def __init__(
        self,
        service: ProductService,
        actor: User,
        product: Product | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._service = service
        self._actor = actor
        self._product = product
        self._drag_pos = QPoint()

        self.setObjectName("productFormDialog")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setFixedSize(620, 600)

        self._init_ui()
        if product is not None:
            self._populate(product)

    def _create_section_label(self, title: str) -> QLabel:
        """Create an uppercase section header label."""
        lbl = QLabel(title)
        lbl.setStyleSheet("""
            color: #64748b;
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 1.2px;
            margin-top: 4px;
            margin-bottom: 2px;
        """)
        return lbl

    def _create_field_group(
        self, label_text: str, input_widget: QWidget, required: bool = False, optional: bool = False, helper_text: str = ""
    ) -> QVBoxLayout:
        """Create a field vertical layout with high-contrast label and optional helper text."""
        group = QVBoxLayout()
        group.setContentsMargins(0, 0, 0, 0)
        group.setSpacing(3)

        lbl = QLabel()
        if required:
            lbl.setText(f"{label_text} <span style='color: #dc2626;'>*</span>")
        elif optional:
            lbl.setText(f"{label_text} <span style='color: #94a3b8; font-size: 11px; font-weight: 500;'>(Optional)</span>")
        else:
            lbl.setText(label_text)

        lbl.setStyleSheet("color: #0f172a; font-size: 12px; font-weight: 700;")
        group.addWidget(lbl)
        group.addWidget(input_widget)

        if helper_text:
            helper_lbl = QLabel(helper_text)
            helper_lbl.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 500; margin-top: 1px;")
            group.addWidget(helper_lbl)

        return group

    def _init_ui(self) -> None:
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
            QLineEdit, QComboBox, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
                padding: 6px 10px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background-color: #ffffff;
                font-size: 13px;
                color: #0f172a;
            }
            QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border-color: #2563eb;
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

        hdr_title = QLabel("Edit Product" if self._product else "Add New Product")
        hdr_title.setStyleSheet("color: #0f172a; font-size: 16px; font-weight: 800;")
        hdr_text_layout.addWidget(hdr_title)

        hdr_sub = QLabel("Configure product catalog details, pricing margins, and stock alerts.")
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

        # ── 2. Segmented Tab Bar ──
        tab_bar = QFrame()
        tab_bar.setStyleSheet("background-color: #f8fafc; border-bottom: 1px solid #e2e8f0; padding: 4px 18px;")
        tab_layout = QHBoxLayout(tab_bar)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(6)

        self.tab_buttons: list[QPushButton] = []
        tab_items = [
            (" General Info", "products"),
            (" Pricing & Tax", "tag"),
            (" Stock & Alerts", "alert_triangle"),
        ]

        for idx, (title, icon_k) in enumerate(tab_items):
            btn = QPushButton(title)
            btn.setIcon(IconManager.get_pixmap(icon_k, color="#475569", size=13))
            btn.setFixedHeight(30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda chk, i=idx: self._switch_tab(i))
            tab_layout.addWidget(btn)
            self.tab_buttons.append(btn)

        tab_layout.addStretch()
        container_layout.addWidget(tab_bar)

        # ── 3. Content Body & Stacked Tabs ──
        body_widget = QWidget()
        body_widget.setStyleSheet("background: transparent;")
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(18, 12, 18, 12)
        body_layout.setSpacing(10)

        # Error Banner (Preserved for tests)
        self._error_label = QLabel("")
        self._error_label.setObjectName("formErrorLabel")
        self._error_label.setStyleSheet("""
            QLabel#formErrorLabel {
                background-color: #fef2f2;
                color: #dc2626;
                border: 1px solid #fca5a5;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
                font-weight: 600;
            }
        """)
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)
        body_layout.addWidget(self._error_label)

        # Form Inputs Setup
        self._sku_input = QLineEdit()
        self._sku_input.setFixedHeight(36)
        self._sku_input.setPlaceholderText("e.g. BEV-001")
        self._sku_input.setAccessibleName("SKU")

        self._barcode_input = QLineEdit()
        self._barcode_input.setFixedHeight(36)
        self._barcode_input.setPlaceholderText("e.g. 4800010000017")
        self._barcode_input.setAccessibleName("Barcode")

        btn_auto_barcode = QPushButton(" Auto")
        btn_auto_barcode.setIcon(IconManager.get_pixmap("barcode", color="#2563eb", size=13))
        btn_auto_barcode.setFixedHeight(36)
        btn_auto_barcode.setCursor(Qt.PointingHandCursor)
        btn_auto_barcode.setStyleSheet("""
            QPushButton {
                background-color: #eff6ff;
                color: #2563eb;
                border: 1px solid #bfdbfe;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 700;
                padding: 0 8px;
            }
            QPushButton:hover { background-color: #dbeafe; }
        """)
        btn_auto_barcode.clicked.connect(self._auto_generate_barcode)

        barcode_container = QWidget()
        bc_l = QHBoxLayout(barcode_container)
        bc_l.setContentsMargins(0, 0, 0, 0)
        bc_l.setSpacing(6)
        bc_l.addWidget(self._barcode_input, stretch=1)
        bc_l.addWidget(btn_auto_barcode)

        self._name_input = QLineEdit()
        self._name_input.setFixedHeight(36)
        self._name_input.setPlaceholderText("e.g. Coca-Cola 1.5L")
        self._name_input.setAccessibleName("Product name")

        # Category Combo + [+]
        self._category_combo = QComboBox()
        self._category_combo.setFixedHeight(36)
        btn_add_cat = QPushButton("+")
        btn_add_cat.setFixedSize(36, 36)
        btn_add_cat.setToolTip("Add Category")
        btn_add_cat.setCursor(Qt.PointingHandCursor)
        btn_add_cat.setStyleSheet("QPushButton { background-color: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 6px; font-weight: 800; } QPushButton:hover { background-color: #e2e8f0; }")
        btn_add_cat.clicked.connect(self._quick_add_category)

        cat_container = QWidget()
        cat_l = QHBoxLayout(cat_container)
        cat_l.setContentsMargins(0, 0, 0, 0)
        cat_l.setSpacing(6)
        cat_l.addWidget(self._category_combo, stretch=1)
        cat_l.addWidget(btn_add_cat)

        # Brand Combo + [+]
        self._brand_combo = QComboBox()
        self._brand_combo.setFixedHeight(36)
        btn_add_brand = QPushButton("+")
        btn_add_brand.setFixedSize(36, 36)
        btn_add_brand.setToolTip("Add Brand")
        btn_add_brand.setCursor(Qt.PointingHandCursor)
        btn_add_brand.setStyleSheet("QPushButton { background-color: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 6px; font-weight: 800; } QPushButton:hover { background-color: #e2e8f0; }")
        btn_add_brand.clicked.connect(self._quick_add_brand)

        brand_container = QWidget()
        brand_l = QHBoxLayout(brand_container)
        brand_l.setContentsMargins(0, 0, 0, 0)
        brand_l.setSpacing(6)
        brand_l.addWidget(self._brand_combo, stretch=1)
        brand_l.addWidget(btn_add_brand)

        self._unit_combo = QComboBox()
        self._unit_combo.setFixedHeight(36)

        self._tax_combo = QComboBox()
        self._tax_combo.setFixedHeight(36)
        for label, value in _TAX_TYPES:
            self._tax_combo.addItem(label, value)

        self._cost_spin = QDoubleSpinBox()
        self._cost_spin.setFixedHeight(36)
        self._cost_spin.setDecimals(2)
        self._cost_spin.setRange(0, 99_999_999)
        self._cost_spin.setPrefix("₱ ")
        self._cost_spin.setAlignment(Qt.AlignRight)
        self._cost_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self._cost_spin.valueChanged.connect(self._update_margin_indicator)

        self._price_spin = QDoubleSpinBox()
        self._price_spin.setFixedHeight(36)
        self._price_spin.setDecimals(2)
        self._price_spin.setRange(0, 99_999_999)
        self._price_spin.setPrefix("₱ ")
        self._price_spin.setAlignment(Qt.AlignRight)
        self._price_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self._price_spin.valueChanged.connect(self._update_margin_indicator)

        self._reorder_spin = QSpinBox()
        self._reorder_spin.setFixedHeight(36)
        self._reorder_spin.setRange(0, 1_000_000)

        self._status_combo = QComboBox()
        self._status_combo.setFixedHeight(36)
        for label, value in _STATUSES:
            self._status_combo.addItem(label, value)

        self._description_input = QPlainTextEdit()
        self._description_input.setMaximumHeight(65)
        self._description_input.setPlaceholderText("Optional product notes...")

        # Profit Margin Live Badge
        self.lbl_margin_badge = QLabel("Profit Margin: 0.0% · ₱0.00 Profit")
        self.lbl_margin_badge.setAlignment(Qt.AlignCenter)
        self.lbl_margin_badge.setStyleSheet("font-size: 11px; font-weight: 800; color: #047857; background-color: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 6px; padding: 6px 10px;")

        # Tab Stack Widget
        self._tab_stack = QStackedWidget()

        # ── TAB 1: General Info ──
        tab1 = QWidget()
        t1_l = QVBoxLayout(tab1)
        t1_l.setContentsMargins(0, 0, 0, 0)
        t1_l.setSpacing(10)

        g1 = QGridLayout()
        g1.setHorizontalSpacing(12)
        g1.setVerticalSpacing(8)
        g1.addLayout(self._create_field_group("SKU", self._sku_input, required=True), 0, 0)
        g1.addLayout(self._create_field_group("Barcode", barcode_container, optional=True), 0, 1)
        g1.addLayout(self._create_field_group("Product Name", self._name_input, required=True), 1, 0, 1, 2)
        t1_l.addLayout(g1)

        g2 = QGridLayout()
        g2.setHorizontalSpacing(12)
        g2.setVerticalSpacing(8)
        g2.addLayout(self._create_field_group("Category", cat_container), 0, 0)
        g2.addLayout(self._create_field_group("Brand", brand_container), 0, 1)
        g2.addLayout(self._create_field_group("Unit", self._unit_combo), 1, 0)
        t1_l.addLayout(g2)

        t1_l.addLayout(self._create_field_group("Description", self._description_input, optional=True))
        t1_l.addStretch()
        self._tab_stack.addWidget(tab1)

        # ── TAB 2: Pricing & Tax ──
        tab2 = QWidget()
        t2_l = QVBoxLayout(tab2)
        t2_l.setContentsMargins(0, 0, 0, 0)
        t2_l.setSpacing(12)

        p_grid = QGridLayout()
        p_grid.setHorizontalSpacing(12)
        p_grid.setVerticalSpacing(8)
        p_grid.addLayout(self._create_field_group("Cost Price (₱)", self._cost_spin), 0, 0)
        p_grid.addLayout(self._create_field_group("Selling Price (₱)", self._price_spin), 0, 1)
        t2_l.addLayout(p_grid)

        t2_l.addWidget(self.lbl_margin_badge)

        tax_grid = QGridLayout()
        tax_grid.setHorizontalSpacing(12)
        tax_grid.setVerticalSpacing(8)
        tax_grid.addLayout(self._create_field_group("Tax Type", self._tax_combo), 0, 0)
        tax_grid.addLayout(self._create_field_group("Status", self._status_combo), 0, 1)
        t2_l.addLayout(tax_grid)
        t2_l.addStretch()
        self._tab_stack.addWidget(tab2)

        # ── TAB 3: Stock & Thresholds ──
        tab3 = QWidget()
        t3_l = QVBoxLayout(tab3)
        t3_l.setContentsMargins(0, 0, 0, 0)
        t3_l.setSpacing(12)

        s_grid = QGridLayout()
        s_grid.setHorizontalSpacing(12)
        s_grid.setVerticalSpacing(8)
        s_grid.addLayout(
            self._create_field_group("Reorder Alert Threshold", self._reorder_spin, helper_text="System triggers Low Stock alert when count reaches this level."),
            0,
            0,
        )
        t3_l.addLayout(s_grid)
        t3_l.addStretch()
        self._tab_stack.addWidget(tab3)

        body_layout.addWidget(self._tab_stack, stretch=1)
        container_layout.addWidget(body_widget, stretch=1)

        self._switch_tab(0)
        self._load_options()
        self._update_margin_indicator()

        # ── 4. Sticky Footer ──
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

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setFixedHeight(34)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 700;
                padding: 0 14px;
            }
            QPushButton:hover { background-color: #f1f5f9; color: #0f172a; }
        """)
        cancel_btn.clicked.connect(self.reject)
        footer_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save Product")
        save_btn.setIcon(IconManager.get_pixmap("check", color="#ffffff", size=14))
        save_btn.setObjectName("primaryButton")
        save_btn.setDefault(True)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setFixedHeight(34)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 800;
                padding: 0 16px;
            }
            QPushButton:hover { background-color: #1d4ed8; }
        """)
        save_btn.clicked.connect(self._save)
        footer_layout.addWidget(save_btn)

        container_layout.addWidget(footer_card)

    def _switch_tab(self, index: int):
        self._tab_stack.setCurrentIndex(index)
        for i, btn in enumerate(self.tab_buttons):
            if i == index:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2563eb;
                        color: #ffffff;
                        border: none;
                        border-radius: 6px;
                        font-size: 12px;
                        font-weight: 800;
                        padding: 0 12px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        color: #475569;
                        border: 1px solid transparent;
                        border-radius: 6px;
                        font-size: 12px;
                        font-weight: 600;
                        padding: 0 12px;
                    }
                    QPushButton:hover {
                        background-color: #f1f5f9;
                        border-color: #cbd5e1;
                        color: #0f172a;
                    }
                """)

    def _update_margin_indicator(self):
        cost = self._cost_spin.value()
        price = self._price_spin.value()
        profit = price - cost

        if cost > 0:
            margin_pct = (profit / cost) * 100.0
            if margin_pct >= 25:
                style = "color: #047857; background-color: #ecfdf5; border: 1px solid #a7f3d0;"
            elif margin_pct >= 10:
                style = "color: #d97706; background-color: #fffbeb; border: 1px solid #fde68a;"
            else:
                style = "color: #dc2626; background-color: #fef2f2; border: 1px solid #fecaca;"
            self.lbl_margin_badge.setText(f"Profit Margin:  +{margin_pct:.1f}%  (₱{profit:,.2f} profit / unit)")
        else:
            style = "color: #047857; background-color: #ecfdf5; border: 1px solid #a7f3d0;"
            self.lbl_margin_badge.setText(f"Profit Margin:  —  (₱{profit:,.2f} profit / unit)")

        self.lbl_margin_badge.setStyleSheet(f"font-size: 11px; font-weight: 800; border-radius: 6px; padding: 6px 10px; {style}")

    def _auto_generate_barcode(self):
        prefix = "480"  # Philippines EAN-13 prefix
        body = "".join([str(random.randint(0, 9)) for _ in range(9)])
        # Check digit calculation for EAN-13
        digits = [int(d) for d in prefix + body]
        checksum = (10 - sum(d * (3 if i % 2 == 1 else 1) for i, d in enumerate(digits)) % 10) % 10
        barcode = f"{prefix}{body}{checksum}"
        self._barcode_input.setText(barcode)

    def _on_header_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _on_header_mouse_move(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def _quick_add_category(self):
        text, ok = QInputDialog.getText(self, "Add Category", "Enter new Category name:")
        if ok and text.strip():
            try:
                cat = Category(name=text.strip())
                self._service._session.add(cat)
                self._service._session.commit()
                self._load_options()
                self._set_combo_by_data(self._category_combo, cat.id)
            except Exception as exc:
                self._service._session.rollback()
                QMessageBox.warning(self, "Error", f"Could not add category: {exc}")

    def _quick_add_brand(self):
        text, ok = QInputDialog.getText(self, "Add Brand", "Enter new Brand name:")
        if ok and text.strip():
            try:
                b = Brand(name=text.strip())
                self._service._session.add(b)
                self._service._session.commit()
                self._load_options()
                self._set_combo_by_data(self._brand_combo, b.id)
            except Exception as exc:
                self._service._session.rollback()
                QMessageBox.warning(self, "Error", f"Could not add brand: {exc}")

    def _load_options(self) -> None:
        curr_cat = self._category_combo.currentData()
        curr_brand = self._brand_combo.currentData()

        options = self._service.get_form_options(self._actor)

        self._category_combo.blockSignals(True)
        self._category_combo.clear()
        self._category_combo.addItem("— None —", None)
        for c in options.categories:
            self._category_combo.addItem(c.name, c.id)
        self._set_combo_by_data(self._category_combo, curr_cat)
        self._category_combo.blockSignals(False)

        self._brand_combo.blockSignals(True)
        self._brand_combo.clear()
        self._brand_combo.addItem("— None —", None)
        for b in options.brands:
            self._brand_combo.addItem(b.name, b.id)
        self._set_combo_by_data(self._brand_combo, curr_brand)
        self._brand_combo.blockSignals(False)

        self._unit_combo.clear()
        self._unit_combo.addItem("— None —", None)
        for u in options.units:
            self._unit_combo.addItem(u.name, u.id)

    def _populate(self, p: Product) -> None:
        """Pre-populate fields when editing an existing product."""
        self._sku_input.setText(p.sku or "")
        self._name_input.setText(p.name or "")

        bc_val = ""
        if hasattr(p, "barcodes") and p.barcodes:
            bc_val = p.barcodes[0].barcode
        elif hasattr(p, "barcode"):
            bc_val = getattr(p, "barcode") or ""
        self._barcode_input.setText(bc_val)

        self._description_input.setPlainText(p.description or "")

        self._set_combo_by_data(self._category_combo, p.category_id)
        self._set_combo_by_data(self._brand_combo, p.brand_id)
        self._set_combo_by_data(self._unit_combo, p.base_unit_id)
        self._set_combo_by_data(self._tax_combo, p.tax_type)

        status_str = "inactive" if (getattr(p, "status", None) == "archived") else (getattr(p, "status", None) or "active")
        self._set_combo_by_data(self._status_combo, status_str)

        self._cost_spin.setValue(float(p.cost_price or 0))
        self._price_spin.setValue(float(p.selling_price or 0))
        self._reorder_spin.setValue(int(p.reorder_level or 0))
        self._update_margin_indicator()

    def _set_combo_by_data(self, combo: QComboBox, val) -> None:
        if val is None:
            combo.setCurrentIndex(0)
            return
        for i in range(combo.count()):
            if combo.itemData(i) == val:
                combo.setCurrentIndex(i)
                return
        combo.setCurrentIndex(0)

    def _save(self) -> None:
        sku = self._sku_input.text().strip()
        name = self._name_input.text().strip()

        if not sku:
            self._show_error("SKU is required.")
            self._sku_input.setFocus()
            return
        if not name:
            self._show_error("Product Name is required.")
            self._name_input.setFocus()
            return

        dto = ProductFormDTO(
            sku=sku,
            name=name,
            barcode=self._barcode_input.text().strip() or "",
            category_id=self._category_combo.currentData(),
            brand_id=self._brand_combo.currentData(),
            base_unit_id=self._unit_combo.currentData(),
            tax_type=self._tax_combo.currentData() or "vat",
            cost_price=Decimal(str(self._cost_spin.value())),
            selling_price=Decimal(str(self._price_spin.value())),
            reorder_level=self._reorder_spin.value(),
            status=self._status_combo.currentData() or "active",
            description=self._description_input.toPlainText().strip() or None,
        )

        try:
            self._error_label.setVisible(False)
            if self._product:
                self._service.update(self._product.id, dto, self._actor)
            else:
                self._service.create(dto, self._actor)
            self.accept()
        except RetailFlowError as exc:
            self._show_error(str(exc))
        except Exception as exc:
            self._show_error(f"Unexpected error: {exc}")

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.setVisible(True)
