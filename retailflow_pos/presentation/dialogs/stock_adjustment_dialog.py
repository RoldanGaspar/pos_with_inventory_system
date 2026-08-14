"""
RetailFlow POS - Modern Stock Adjustment Dialog
Frameless modal for stock-in, damage write-off, or physical inventory audit adjustments
with live count preview transformation and quick preset reasons.
"""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from infrastructure.database.models.product import Product
from presentation.styles.icons import IconManager


class StockAdjustmentDialog(QDialog):
    """Modal for adjusting product stock-on-hand."""

    def __init__(self, product: Product, parent: QWidget | None = None):
        super().__init__(parent)
        self.product = product
        self.new_quantity = product.stock_quantity
        self.adjustment_reason = ""
        self._drag_pos = QPoint()

        self.setWindowTitle(f"Stock Adjustment — {product.sku}")
        self.setFixedSize(500, 520)
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

        hdr_title = QLabel("Stock Level Adjustment")
        hdr_title.setStyleSheet("color: #0f172a; font-size: 16px; font-weight: 800;")
        hdr_text_layout.addWidget(hdr_title)

        hdr_sub = QLabel("Record inventory receipt, damage write-off, or physical audit count.")
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
        body_layout.setContentsMargins(18, 14, 18, 14)
        body_layout.setSpacing(12)

        # Product Info Banner
        prod_frame = QFrame()
        prod_frame.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 10px 14px;
            }
        """)
        prod_layout = QHBoxLayout(prod_frame)
        prod_layout.setContentsMargins(0, 0, 0, 0)
        prod_layout.setSpacing(10)

        ico = QLabel()
        ico.setFixedSize(36, 36)
        ico.setAlignment(Qt.AlignCenter)
        ico.setStyleSheet("background-color: #eff6ff; border: 1px solid #dbeafe; border-radius: 8px;")
        ico.setPixmap(IconManager.get_pixmap("products", color="#2563eb", size=18))
        prod_layout.addWidget(ico)

        p_info = QVBoxLayout()
        p_info.setSpacing(2)
        title_lbl = QLabel(self.product.name)
        title_lbl.setStyleSheet("font-size: 14px; font-weight: 800; color: #0f172a;")
        p_info.addWidget(title_lbl)

        cat_name = getattr(self.product, 'category_name', '') or (self.product.category.name if getattr(self.product, 'category', None) else 'Uncategorized')
        sku_lbl = QLabel(f"SKU: {self.product.sku}  ·  Category: {cat_name}")
        sku_lbl.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 500;")
        p_info.addWidget(sku_lbl)
        prod_layout.addLayout(p_info, stretch=1)

        curr_stock_box = QVBoxLayout()
        curr_stock_box.setSpacing(2)
        curr_stock_box.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        cs_lbl = QLabel("CURRENT STOCK")
        cs_lbl.setStyleSheet("font-size: 9px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        cs_val = QLabel(f"{self.product.stock_quantity} Units")
        cs_val.setStyleSheet("font-size: 15px; font-weight: 800; color: #2563eb;")
        curr_stock_box.addWidget(cs_lbl)
        curr_stock_box.addWidget(cs_val)
        prod_layout.addLayout(curr_stock_box)

        body_layout.addWidget(prod_frame)

        # Adjustment Mode Selection Tabs
        lbl_type = QLabel("ADJUSTMENT TYPE")
        lbl_type.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        body_layout.addWidget(lbl_type)

        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(6)

        self.btn_mode_add = QPushButton(" 📥 Add Stock (+)")
        self.btn_mode_deduct = QPushButton(" ⚠️ Deduct Stock (-)")
        self.btn_mode_audit = QPushButton(" 📝 Physical Count")

        self.mode_buttons = [
            (self.btn_mode_add, 1),
            (self.btn_mode_deduct, 2),
            (self.btn_mode_audit, 0),
        ]

        for btn, mode_val in self.mode_buttons:
            btn.setFixedHeight(34)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda chk, m=mode_val: self._set_mode(m))
            mode_layout.addWidget(btn)

        body_layout.addLayout(mode_layout)

        # Hidden QComboBox for backward compatibility
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems([
            "Set Exact Count (Physical Audit)",
            "Add Stock (+) [Stock-In / Restock]",
            "Deduct Stock (-) [Damage / Loss / Expired]",
        ])
        self.cmb_mode.hide()
        self.cmb_mode.currentIndexChanged.connect(self._on_mode_changed)

        # Quantity Input Card
        qty_card = QFrame()
        qty_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 10px 14px;
            }
        """)
        qty_layout = QVBoxLayout(qty_card)
        qty_layout.setContentsMargins(0, 0, 0, 0)
        qty_layout.setSpacing(8)

        qty_input_row = QHBoxLayout()
        self.lbl_target = QLabel("Quantity to Add (+):")
        self.lbl_target.setStyleSheet("color: #0f172a; font-size: 12px; font-weight: 700;")
        qty_input_row.addWidget(self.lbl_target)

        self.spn_qty = QSpinBox()
        self.spn_qty.setRange(0, 999999)
        self.spn_qty.setValue(10)
        self.spn_qty.setFixedWidth(130)
        self.spn_qty.setFixedHeight(34)
        self.spn_qty.setStyleSheet("""
            QSpinBox {
                padding: 4px 8px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 700;
                color: #0f172a;
            }
            QSpinBox:focus { border-color: #2563eb; }
        """)
        self.spn_qty.valueChanged.connect(self._update_preview)
        qty_input_row.addWidget(self.spn_qty, alignment=Qt.AlignRight)
        qty_layout.addLayout(qty_input_row)

        # Live Stock Preview Badge
        self.lbl_preview = QLabel("Current: 25 Units  ➔  New Total: 35 Units (+10)")
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setStyleSheet("""
            font-size: 12px;
            font-weight: 800;
            color: #047857;
            background-color: #ecfdf5;
            border: 1px solid #a7f3d0;
            border-radius: 6px;
            padding: 8px;
        """)
        qty_layout.addWidget(self.lbl_preview)

        body_layout.addWidget(qty_card)

        # Reason Input
        lbl_reason = QLabel("REASON / REFERENCE")
        lbl_reason.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        body_layout.addWidget(lbl_reason)

        self.txt_reason = QLineEdit()
        self.txt_reason.setPlaceholderText("e.g. Supplier delivery PO-102, routine physical audit, damage...")
        self.txt_reason.setFixedHeight(36)
        self.txt_reason.setStyleSheet("""
            QLineEdit {
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 13px;
                color: #0f172a;
            }
            QLineEdit:focus { border-color: #2563eb; }
        """)
        body_layout.addWidget(self.txt_reason)

        # Quick Preset Chips
        chips_l = QHBoxLayout()
        chips_l.setSpacing(6)
        for preset in ["Supplier Delivery", "Physical Audit", "Damage Write-Off"]:
            p_btn = QPushButton(preset)
            p_btn.setFixedHeight(24)
            p_btn.setCursor(Qt.PointingHandCursor)
            p_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f1f5f9;
                    color: #475569;
                    border: 1px solid #e2e8f0;
                    border-radius: 12px;
                    font-size: 10px;
                    font-weight: 700;
                    padding: 0 10px;
                }
                QPushButton:hover { background-color: #e2e8f0; color: #0f172a; }
            """)
            p_btn.clicked.connect(lambda chk, t=preset: self.txt_reason.setText(t))
            chips_l.addWidget(p_btn)
        chips_l.addStretch()
        body_layout.addLayout(chips_l)

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
                font-size: 13px;
                font-weight: 700;
                padding: 0 14px;
            }
            QPushButton:hover { background-color: #f1f5f9; color: #0f172a; }
        """)
        btn_cancel.clicked.connect(self.reject)
        footer_layout.addWidget(btn_cancel)

        btn_save = QPushButton("Save Stock Adjustment")
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
                font-size: 13px;
                font-weight: 800;
                padding: 0 16px;
            }
            QPushButton:hover { background-color: #1d4ed8; }
        """)
        btn_save.clicked.connect(self._on_save)
        footer_layout.addWidget(btn_save)

        container_layout.addWidget(footer_card)

        self._set_mode(1)  # Default: Add Stock

    def _set_mode(self, mode_idx: int):
        self.cmb_mode.setCurrentIndex(mode_idx)
        for btn, m in self.mode_buttons:
            if m == mode_idx:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2563eb;
                        color: #ffffff;
                        border: none;
                        border-radius: 6px;
                        font-size: 11px;
                        font-weight: 800;
                        padding: 0 10px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #ffffff;
                        color: #475569;
                        border: 1px solid #cbd5e1;
                        border-radius: 6px;
                        font-size: 11px;
                        font-weight: 600;
                        padding: 0 10px;
                    }
                    QPushButton:hover { background-color: #f1f5f9; color: #0f172a; }
                """)
        self._on_mode_changed(mode_idx)

    def _on_mode_changed(self, idx: int):
        if idx == 0:  # Set exact (Physical audit)
            self.lbl_target.setText("New Total Count:")
            self.spn_qty.setValue(self.product.stock_quantity)
        elif idx == 1:  # Add stock
            self.lbl_target.setText("Quantity to Add (+):")
            self.spn_qty.setValue(10)
        elif idx == 2:  # Deduct stock
            self.lbl_target.setText("Quantity to Deduct (-):")
            self.spn_qty.setValue(1)
        self._update_preview()

    def _update_preview(self):
        mode_idx = self.cmb_mode.currentIndex()
        val = self.spn_qty.value()
        curr = self.product.stock_quantity

        if mode_idx == 0:
            target = val
            delta = target - curr
            delta_str = f"+{delta}" if delta > 0 else str(delta)
        elif mode_idx == 1:
            target = curr + val
            delta_str = f"+{val}"
        elif mode_idx == 2:
            target = max(0, curr - val)
            delta_str = f"-{val}"
        else:
            target = curr
            delta_str = "0"

        if target == 0:
            style = "color: #dc2626; background-color: #fef2f2; border: 1px solid #fecaca;"
        elif target <= getattr(self.product, 'reorder_level', 5):
            style = "color: #d97706; background-color: #fffbeb; border: 1px solid #fde68a;"
        else:
            style = "color: #047857; background-color: #ecfdf5; border: 1px solid #a7f3d0;"

        self.lbl_preview.setText(f"Current: {curr} Units  ➔  New Total: {target} Units ({delta_str})")
        self.lbl_preview.setStyleSheet(f"font-size: 12px; font-weight: 800; border-radius: 6px; padding: 8px; {style}")

    def _on_header_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _on_header_mouse_move(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def _on_save(self):
        mode_idx = self.cmb_mode.currentIndex()
        val = self.spn_qty.value()

        if mode_idx == 0:
            self.new_quantity = val
        elif mode_idx == 1:
            self.new_quantity = self.product.stock_quantity + val
        elif mode_idx == 2:
            self.new_quantity = max(0, self.product.stock_quantity - val)

        self.adjustment_reason = self.txt_reason.text().strip() or self.cmb_mode.currentText()
        self.accept()
