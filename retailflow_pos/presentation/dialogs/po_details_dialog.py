"""
RetailFlow POS - Purchase Order Details & Receiving Dialog
Frameless modal for inspecting purchase order line items and receiving wholesale stock.
"""

from typing import Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from application.dto.purchasing_dto import PurchaseOrderResponseDTO
from application.services.purchasing_service import PurchasingService
from domain.exceptions import RetailFlowError
from infrastructure.database.models.auth import User
from presentation.styles.icons import IconManager


class PODetailsDialog(QDialog):
    """Modal for inspecting PO details, reviewing items, and receiving stock."""

    def __init__(
        self,
        purchasing_service: PurchasingService,
        po_dto: PurchaseOrderResponseDTO,
        current_actor: User,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._purchasing_service = purchasing_service
        self._po = po_dto
        self._actor = current_actor
        self._drag_pos = QPoint()

        self.setWindowTitle(f"Purchase Order — {po_dto.po_number}")
        self.setFixedSize(620, 600)
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

        hdr_title = QLabel(f"Purchase Order: {self._po.po_number}")
        hdr_title.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: 800; font-family: 'Consolas', monospace;")
        hdr_text_layout.addWidget(hdr_title)

        hdr_sub = QLabel(f"Ordered from {self._po.supplier_name} on {self._po.order_date}")
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

        # Metadata Summary Card
        meta_card = QFrame()
        meta_card.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 10px 14px;
            }
        """)
        meta_layout = QVBoxLayout(meta_card)
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(4)

        def make_row(lbl1, val1, lbl2, val2):
            row = QHBoxLayout()
            c1 = QHBoxLayout()
            l1 = QLabel(lbl1)
            l1.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 600;")
            v1 = QLabel(val1)
            v1.setStyleSheet("color: #0f172a; font-size: 11px; font-weight: 800;")
            c1.addWidget(l1)
            c1.addWidget(v1)
            c1.addStretch()

            c2 = QHBoxLayout()
            l2 = QLabel(lbl2)
            l2.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 600;")
            v2 = QLabel(val2)
            v2.setStyleSheet("color: #0f172a; font-size: 11px; font-weight: 800;")
            c2.addWidget(l2)
            c2.addWidget(v2)
            c2.addStretch()

            row.addLayout(c1, 1)
            row.addLayout(c2, 1)
            return row

        meta_layout.addLayout(make_row("Supplier:", f"{self._po.supplier_name} ({self._po.supplier_code})", "Status:", self._po.status.upper()))
        meta_layout.addLayout(make_row("Payment Terms:", self._po.payment_terms.replace("_", " "), "Delivery Due:", self._po.expected_delivery or "Flexible"))
        if self._po.received_at:
            meta_layout.addLayout(make_row("Received On:", self._po.received_at, "Total Units:", f"{self._po.total_units} units"))
        if self._po.notes:
            note_lbl = QLabel(f"Delivery Note: {self._po.notes}")
            note_lbl.setStyleSheet("color: #475569; font-size: 11px; font-style: italic;")
            meta_layout.addWidget(note_lbl)

        body_layout.addWidget(meta_card)

        # Line Items Label
        lbl_items = QLabel("ORDERED PRODUCT LINE ITEMS")
        lbl_items.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        body_layout.addWidget(lbl_items)

        # Line Items Table
        self.tbl_items = QTableWidget()
        self.tbl_items.setColumnCount(4)
        self.tbl_items.setHorizontalHeaderLabels([
            "PRODUCT NAME",
            "QTY ORDERED",
            "UNIT COST",
            "SUBTOTAL",
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

        self.tbl_items.setRowCount(len(self._po.items))
        for row, it in enumerate(self._po.items):
            name_item = QTableWidgetItem(it.product_name)
            name_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.tbl_items.setItem(row, 0, name_item)

            qty_str = f"{it.quantity_ordered} pcs"
            if self._po.status == "RECEIVED":
                qty_str += f" (Rec: {it.quantity_received})"
            qty_item = QTableWidgetItem(qty_str)
            qty_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self.tbl_items.setItem(row, 1, qty_item)

            cost_item = QTableWidgetItem(f"₱{it.unit_cost:,.2f}")
            cost_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tbl_items.setItem(row, 2, cost_item)

            sub_item = QTableWidgetItem(f"₱{it.subtotal:,.2f}")
            sub_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tbl_items.setItem(row, 3, sub_item)

        body_layout.addWidget(self.tbl_items, stretch=1)

        # Order Grand Total Card
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

        sum_lbl = QLabel(f"{self._po.items_count} products · {self._po.total_units} total units")
        sum_lbl.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 600;")
        total_layout.addWidget(sum_lbl)
        total_layout.addStretch()

        g_lbl = QLabel(f"ORDER TOTAL: ₱{self._po.total_amount:,.2f}")
        g_lbl.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: 800;")
        total_layout.addWidget(g_lbl)

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

        btn_close_ft = QPushButton("Close")
        btn_close_ft.setFixedHeight(34)
        btn_close_ft.setCursor(Qt.PointingHandCursor)
        btn_close_ft.setStyleSheet("""
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
        btn_close_ft.clicked.connect(self.accept)
        footer_layout.addWidget(btn_close_ft)

        # Receive stock action button if ORDERED or DRAFT
        if self._po.status in ("ORDERED", "DRAFT"):
            btn_recv = QPushButton(" 📥 Receive Stock & Update Inventory")
            btn_recv.setIcon(IconManager.get_pixmap("check", color="#ffffff", size=14))
            btn_recv.setFixedHeight(34)
            btn_recv.setCursor(Qt.PointingHandCursor)
            btn_recv.setStyleSheet("""
                QPushButton {
                    background-color: #059669;
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: 800;
                    padding: 0 16px;
                }
                QPushButton:hover { background-color: #047857; }
            """)
            btn_recv.clicked.connect(self._receive_stock)
            footer_layout.addWidget(btn_recv)

        container_layout.addWidget(footer_card)

    def _receive_stock(self):
        try:
            self._purchasing_service.receive_stock(self._po.id, actor=self._actor)
            self.accept()
        except RetailFlowError as e:
            pass
        except Exception:
            pass

    def _on_header_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _on_header_mouse_move(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
