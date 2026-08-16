"""
RetailFlow POS - Purchase Order Dialog
Frameless modal for creating new purchase orders, adding product line items,
and setting expected delivery dates.
"""

from decimal import Decimal
from typing import List, Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from application.dto.purchasing_dto import CreatePOItemDTO, CreatePurchaseOrderDTO
from application.dto.supplier_dto import SupplierFilterDTO
from application.services.product_service import ProductService
from application.services.purchasing_service import PurchasingService
from application.services.supplier_service import SupplierService
from domain.exceptions import RetailFlowError
from infrastructure.database.models.auth import User
from presentation.styles.icons import IconManager


class PurchaseOrderDialog(QDialog):
    """Modal for issuing a new purchase order to a wholesale supplier."""

    def __init__(
        self,
        purchasing_service: PurchasingService,
        supplier_service: SupplierService,
        product_service: ProductService,
        current_actor: User,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._purchasing_service = purchasing_service
        self._supplier_service = supplier_service
        self._product_service = product_service
        self._actor = current_actor
        self._drag_pos = QPoint()

        # Temporary line items list: list of dicts {product_id, name, qty, cost, subtotal}
        self._items: List[dict] = []

        self.setWindowTitle("Create Purchase Order")
        self.setFixedSize(680, 640)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self._init_ui()
        self._populate_suppliers()
        self._populate_products()

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

        hdr_title = QLabel("Issue New Purchase Order")
        hdr_title.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: 800;")
        hdr_text_layout.addWidget(hdr_title)

        hdr_sub = QLabel("Select wholesale vendor, add catalog items, and issue restocking PO.")
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
        body_layout.setSpacing(10)

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

        # Row 1: Supplier & Payment Terms
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        f_sup_col = QVBoxLayout()
        f_sup_col.setSpacing(4)
        lbl_sup = QLabel("WHOLESALE SUPPLIER *")
        lbl_sup.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_sup_col.addWidget(lbl_sup)
        self.cmb_supplier = QComboBox()
        self.cmb_supplier.setFixedHeight(34)
        self.cmb_supplier.setStyleSheet(self._input_combo_style())
        f_sup_col.addWidget(self.cmb_supplier)
        row1.addLayout(f_sup_col, 2)

        f_terms_col = QVBoxLayout()
        f_terms_col.setSpacing(4)
        lbl_terms = QLabel("PAYMENT TERMS")
        lbl_terms.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_terms_col.addWidget(lbl_terms)
        self.cmb_terms = QComboBox()
        self.cmb_terms.addItem("Net 30 Days", "NET_30")
        self.cmb_terms.addItem("Net 15 Days", "NET_15")
        self.cmb_terms.addItem("Net 60 Days", "NET_60")
        self.cmb_terms.addItem("Cash on Delivery (COD)", "COD")
        self.cmb_terms.setFixedHeight(34)
        self.cmb_terms.setStyleSheet(self._input_combo_style())
        f_terms_col.addWidget(self.cmb_terms)
        row1.addLayout(f_terms_col, 1)

        body_layout.addLayout(row1)

        # Row 2: Expected Delivery & Notes
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        f_exp_col = QVBoxLayout()
        f_exp_col.setSpacing(4)
        lbl_exp = QLabel("EXPECTED DELIVERY (YYYY-MM-DD)")
        lbl_exp.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_exp_col.addWidget(lbl_exp)
        self.txt_delivery = QLineEdit()
        self.txt_delivery.setPlaceholderText("e.g. 2026-08-20")
        self.txt_delivery.setFixedHeight(34)
        self.txt_delivery.setStyleSheet(self._input_style())
        f_exp_col.addWidget(self.txt_delivery)
        row2.addLayout(f_exp_col, 1)

        f_notes_col = QVBoxLayout()
        f_notes_col.setSpacing(4)
        lbl_notes = QLabel("DELIVERY NOTES / REFERENCE")
        lbl_notes.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_notes_col.addWidget(lbl_notes)
        self.txt_notes = QLineEdit()
        self.txt_notes.setPlaceholderText("e.g. Deliver to Gate 2 Loading Dock...")
        self.txt_notes.setFixedHeight(34)
        self.txt_notes.setStyleSheet(self._input_style())
        f_notes_col.addWidget(self.txt_notes)
        row2.addLayout(f_notes_col, 2)

        body_layout.addLayout(row2)

        # ── Item Adder Box ──
        add_box = QFrame()
        add_box.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 8px 10px;
            }
        """)
        add_layout = QHBoxLayout(add_box)
        add_layout.setContentsMargins(0, 0, 0, 0)
        add_layout.setSpacing(8)

        self.cmb_product = QComboBox()
        self.cmb_product.setFixedHeight(32)
        self.cmb_product.setStyleSheet(self._input_combo_style())
        self.cmb_product.currentIndexChanged.connect(self._on_product_selected)
        add_layout.addWidget(self.cmb_product, stretch=3)

        self.spn_qty = QSpinBox()
        self.spn_qty.setRange(1, 99999)
        self.spn_qty.setValue(24)
        self.spn_qty.setPrefix("Qty: ")
        self.spn_qty.setFixedHeight(32)
        self.spn_qty.setStyleSheet(self._input_spin_style())
        add_layout.addWidget(self.spn_qty, stretch=1)

        self.spn_cost = QDoubleSpinBox()
        self.spn_cost.setRange(0.01, 999999.00)
        self.spn_cost.setValue(25.00)
        self.spn_cost.setPrefix("₱ ")
        self.spn_cost.setFixedHeight(32)
        self.spn_cost.setStyleSheet(self._input_spin_style())
        add_layout.addWidget(self.spn_cost, stretch=1)

        btn_add_item = QPushButton(" + Add")
        btn_add_item.setIcon(IconManager.get_pixmap("plus", color="#ffffff", size=12))
        btn_add_item.setFixedHeight(32)
        btn_add_item.setCursor(Qt.PointingHandCursor)
        btn_add_item.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 800;
                padding: 0 12px;
            }
            QPushButton:hover { background-color: #1d4ed8; }
        """)
        btn_add_item.clicked.connect(self._add_item)
        add_layout.addWidget(btn_add_item)

        body_layout.addWidget(add_box)

        # Items Table
        self.tbl_items = QTableWidget()
        self.tbl_items.setColumnCount(5)
        self.tbl_items.setHorizontalHeaderLabels([
            "PRODUCT NAME",
            "QUANTITY",
            "UNIT COST",
            "SUBTOTAL",
            "ACTION",
        ])
        self.tbl_items.verticalHeader().setVisible(False)
        self.tbl_items.setShowGrid(False)
        self.tbl_items.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #64748b;
                font-size: 10px;
                font-weight: 800;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                padding: 6px 8px;
            }
        """)

        header = self.tbl_items.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.tbl_items.setColumnWidth(4, 60)

        body_layout.addWidget(self.tbl_items, stretch=1)

        # Live Order Total Card
        total_card = QFrame()
        total_card.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 10px 14px;
            }
        """)
        total_layout = QHBoxLayout(total_card)
        total_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_items_summary = QLabel("0 products · 0 units")
        self.lbl_items_summary.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 600;")
        total_layout.addWidget(self.lbl_items_summary)
        total_layout.addStretch()

        self.lbl_grand_total = QLabel("ORDER TOTAL: ₱0.00")
        self.lbl_grand_total.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: 800;")
        total_layout.addWidget(self.lbl_grand_total)

        body_layout.addWidget(total_card)
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

        btn_draft = QPushButton("Save as Draft")
        btn_draft.setFixedHeight(34)
        btn_draft.setCursor(Qt.PointingHandCursor)
        btn_draft.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                padding: 0 14px;
            }
            QPushButton:hover { background-color: #e2e8f0; color: #0f172a; }
        """)
        btn_draft.clicked.connect(lambda: self._on_save(status="DRAFT"))
        footer_layout.addWidget(btn_draft)

        btn_issue = QPushButton("Issue Purchase Order")
        btn_issue.setIcon(IconManager.get_pixmap("check", color="#ffffff", size=14))
        btn_issue.setFixedHeight(34)
        btn_issue.setCursor(Qt.PointingHandCursor)
        btn_issue.setStyleSheet("""
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
        btn_issue.clicked.connect(lambda: self._on_save(status="ORDERED"))
        footer_layout.addWidget(btn_issue)

        container_layout.addWidget(footer_card)

    def _populate_suppliers(self):
        try:
            res = self._supplier_service.search(SupplierFilterDTO(is_active=True, page_size=100))
            self.cmb_supplier.clear()
            for s in res.items:
                self.cmb_supplier.addItem(f"{s.name} ({s.code})", s.id)
        except Exception:
            pass

    def _populate_products(self):
        try:
            from application.dto.product_dto import ProductFilterDTO
            res = self._product_service.search(ProductFilterDTO(status="active", page_size=100), actor=self._actor)
            self.cmb_product.clear()
            for p in res.items:
                self.cmb_product.addItem(p.name, (p.id, p.cost_price))
        except Exception:
            pass

    def _on_product_selected(self):
        data = self.cmb_product.currentData()
        if data:
            _pid, cost = data
            self.spn_cost.setValue(float(cost))

    def _add_item(self):
        data = self.cmb_product.currentData()
        if not data:
            return
        prod_id, _ = data
        prod_name = self.cmb_product.currentText()
        qty = self.spn_qty.value()
        cost = Decimal(str(self.spn_cost.value()))
        subtotal = cost * Decimal(qty)

        # Check if already in list
        for it in self._items:
            if it["product_id"] == prod_id:
                it["quantity"] += qty
                it["subtotal"] = it["unit_cost"] * Decimal(it["quantity"])
                self._render_items()
                return

        self._items.append({
            "product_id": prod_id,
            "product_name": prod_name,
            "quantity": qty,
            "unit_cost": cost,
            "subtotal": subtotal,
        })
        self._render_items()

    def _remove_item(self, index: int):
        if 0 <= index < len(self._items):
            self._items.pop(index)
            self._render_items()

    def _render_items(self):
        self.tbl_items.setRowCount(len(self._items))
        total = Decimal("0.00")
        total_units = 0

        for row, it in enumerate(self._items):
            total += it["subtotal"]
            total_units += it["quantity"]

            name_item = QTableWidgetItem(it["product_name"])
            name_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.tbl_items.setItem(row, 0, name_item)

            qty_item = QTableWidgetItem(f"{it['quantity']} pcs")
            qty_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self.tbl_items.setItem(row, 1, qty_item)

            cost_item = QTableWidgetItem(f"₱{it['unit_cost']:,.2f}")
            cost_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tbl_items.setItem(row, 2, cost_item)

            sub_item = QTableWidgetItem(f"₱{it['subtotal']:,.2f}")
            sub_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tbl_items.setItem(row, 3, sub_item)

            btn_del = QPushButton("✕")
            btn_del.setFixedSize(24, 24)
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setStyleSheet("""
                QPushButton {
                    background-color: #fee2e2;
                    color: #dc2626;
                    border: none;
                    border-radius: 4px;
                    font-size: 10px;
                    font-weight: 800;
                }
                QPushButton:hover { background-color: #dc2626; color: #ffffff; }
            """)
            btn_del.clicked.connect(lambda chk, r=row: self._remove_item(r))

            w = QWidget()
            wl = QHBoxLayout(w)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setAlignment(Qt.AlignCenter)
            wl.addWidget(btn_del)
            self.tbl_items.setCellWidget(row, 4, w)

        self.lbl_items_summary.setText(f"{len(self._items)} products · {total_units} total units")
        self.lbl_grand_total.setText(f"ORDER TOTAL: ₱{total:,.2f}")

    def _on_save(self, status: str = "ORDERED"):
        supplier_id = self.cmb_supplier.currentData()
        if not supplier_id:
            self._show_error("Please select a wholesale supplier.")
            return

        if not self._items:
            self._show_error("Please add at least one product line item.")
            return

        items_dto = [
            CreatePOItemDTO(
                product_id=it["product_id"],
                quantity=it["quantity"],
                unit_cost=it["unit_cost"],
            )
            for it in self._items
        ]

        delivery_str = self.txt_delivery.text().strip() or None
        notes = self.txt_notes.text().strip() or None
        terms = self.cmb_terms.currentData()

        try:
            dto = CreatePurchaseOrderDTO(
                supplier_id=supplier_id,
                items=items_dto,
                expected_delivery=delivery_str,
                payment_terms=terms,
                status=status,
                notes=notes,
            )
            self._purchasing_service.create_po(dto, actor=self._actor)
            self.accept()
        except RetailFlowError as e:
            self._show_error(str(e))
        except Exception as e:
            self._show_error(str(e))

    def _show_error(self, msg: str):
        self.error_banner.setText(msg)
        self.error_banner.show()

    def _on_header_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _on_header_mouse_move(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def _input_style(self) -> str:
        return """
            QLineEdit {
                padding: 4px 10px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 12px;
                color: #0f172a;
            }
            QLineEdit:focus { border-color: #2563eb; }
        """

    def _input_combo_style(self) -> str:
        return """
            QComboBox {
                padding: 4px 10px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                color: #0f172a;
            }
            QComboBox:focus { border-color: #2563eb; }
        """

    def _input_spin_style(self) -> str:
        return """
            QSpinBox, QDoubleSpinBox {
                padding: 4px 8px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                color: #0f172a;
            }
            QSpinBox:focus, QDoubleSpinBox:focus { border-color: #2563eb; }
        """
