"""
RetailFlow POS - Return Details Viewer Dialog
Read-only inspector dialog displaying finalized return voucher breakdown, line items, and audit context.
"""

from decimal import Decimal
from typing import Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from application.dto.returns_dto import SalesReturnDTO
from presentation.styles.icons import IconManager


class ReturnDetailsDialog(QDialog):
    """Read-only modal displaying finalized return voucher metadata and items."""

    def __init__(self, return_dto: SalesReturnDTO, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.ret = return_dto
        self._drag_pos = QPoint()

        self.setWindowTitle(f"Return Voucher — #{return_dto.return_number}")
        self.setMinimumSize(480, 520)
        self.resize(540, 680)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self._init_ui()

    def _init_ui(self):
        container = QFrame(self)
        container.setObjectName("dialogContainerCard")
        container.setStyleSheet("""
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
        dialog_layout.addWidget(container)

        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 1. Draggable Header ──
        header = QFrame()
        header.setObjectName("dialogHeaderCard")
        header.setStyleSheet("""
            QFrame#dialogHeaderCard {
                background-color: #f8fafc;
                border-bottom: 1px solid #e2e8f0;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                padding: 12px 18px;
            }
        """)
        header.mousePressEvent = self._on_header_mouse_press
        header.mouseMoveEvent = self._on_header_mouse_move

        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(0, 0, 0, 0)

        hdr_text_layout = QVBoxLayout()
        hdr_text_layout.setSpacing(2)

        hdr_title = QLabel(f"Return #{self.ret.return_number}")
        hdr_title.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: 800; font-family: 'Consolas', monospace;")
        hdr_text_layout.addWidget(hdr_title)

        hdr_sub = QLabel(f"Original Sale: #{self.ret.sale_transaction_number} · Date: {self.ret.return_date}")
        hdr_sub.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 500;")
        hdr_text_layout.addWidget(hdr_sub)
        hdr_layout.addLayout(hdr_text_layout)
        hdr_layout.addStretch()

        # Status badge
        badge = QLabel("COMPLETED")
        badge.setStyleSheet("""
            background-color: #ecfdf5;
            color: #047857;
            border: 1px solid #a7f3d0;
            border-radius: 6px;
            padding: 3px 8px;
            font-size: 10px;
            font-weight: 800;
        """)
        hdr_layout.addWidget(badge)
        hdr_layout.addSpacing(8)

        btn_close = QPushButton()
        btn_close.setIcon(IconManager.get_pixmap("close", color="#64748b", size=14))
        btn_close.setFixedSize(28, 28)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("background: transparent; border: none; border-radius: 6px;")
        btn_close.clicked.connect(self.accept)
        hdr_layout.addWidget(btn_close)
        main_layout.addWidget(header)

        # ── 2. Scrollable Body ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background-color: #ffffff; border: none;")

        body_widget = QWidget()
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(18, 14, 18, 14)
        body_layout.setSpacing(12)

        # Summary Info Card
        info_card = QFrame()
        info_card.setStyleSheet("background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 12px;")
        info_grid = QVBoxLayout(info_card)
        info_grid.setSpacing(6)

        def add_info_row(label: str, val: str):
            r = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 600;")
            v = QLabel(val)
            v.setStyleSheet("color: #0f172a; font-size: 11px; font-weight: 700;")
            r.addWidget(lbl)
            r.addStretch()
            r.addWidget(v)
            info_grid.addLayout(r)

        reason_display = self.ret.reason_code.replace("_", " ").title()
        add_info_row("Reason:", reason_display)
        if self.ret.reason_notes:
            add_info_row("Notes:", self.ret.reason_notes)

        method_str = "Cash" if self.ret.refund_payment_method == "cash" else f"Original Method ({self.ret.original_payment_method_snapshot})"
        add_info_row("Refund Method:", method_str)
        if self.ret.refund_reference:
            add_info_row("Refund Reference:", self.ret.refund_reference)

        add_info_row("Processed By:", f"{self.ret.cashier_name} (Cashier)")
        add_info_row("Approved By:", f"{self.ret.approver_name} (Manager/Admin)")
        body_layout.addWidget(info_card)

        # Returned Items Table
        lbl_items_hdr = QLabel("RETURNED ITEMS")
        lbl_items_hdr.setStyleSheet("color: #475569; font-size: 10px; font-weight: 800; letter-spacing: 1px;")
        body_layout.addWidget(lbl_items_hdr)

        tbl = QTableWidget()
        tbl.setColumnCount(4)
        tbl.setHorizontalHeaderLabels(["Product", "Qty", "Condition", "Refund"])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        tbl.verticalHeader().setVisible(False)
        tbl.setSelectionMode(QTableWidget.NoSelection)
        tbl.setFocusPolicy(Qt.NoFocus)
        tbl.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                gridline-color: #f1f5f9;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #475569;
                font-size: 10px;
                font-weight: 700;
                padding: 6px;
                border: none;
                border-bottom: 1px solid #e2e8f0;
            }
        """)

        tbl.setRowCount(len(self.ret.items))
        for r, item in enumerate(self.ret.items):
            tbl.setRowHeight(r, 36)

            # Product Name
            p_item = QTableWidgetItem(item.product_name)
            p_item.setForeground(QColor("#0f172a"))
            p_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            tbl.setItem(r, 0, p_item)

            # Qty
            q_item = QTableWidgetItem(str(item.quantity))
            q_item.setForeground(QColor("#475569"))
            q_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            tbl.setItem(r, 1, q_item)

            # Disposition
            disp_lbl = QLabel("Restocked" if item.disposition == "restock" else "Written Off")
            disp_lbl.setAlignment(Qt.AlignCenter)
            if item.disposition == "restock":
                disp_lbl.setStyleSheet("color: #0369a1; background-color: #f0f9ff; border: 1px solid #bae6fd; font-size: 9px; font-weight: 700; border-radius: 4px; padding: 2px 6px;")
            else:
                disp_lbl.setStyleSheet("color: #b91c1c; background-color: #fef2f2; border: 1px solid #fecaca; font-size: 9px; font-weight: 700; border-radius: 4px; padding: 2px 6px;")
            tbl.setCellWidget(r, 2, disp_lbl)

            # Line Refund
            ref_item = QTableWidgetItem(f"₱{item.total_refund_amount:,.2f}")
            ref_item.setForeground(QColor("#0f172a"))
            ref_item.setFont(QFont("Consolas", 9, QFont.Bold))
            ref_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tbl.setItem(r, 3, ref_item)

        tbl.setFixedHeight(min(200, 38 + len(self.ret.items) * 36))
        body_layout.addWidget(tbl)

        # Financial Summary Card
        fin_card = QFrame()
        fin_card.setStyleSheet("background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 12px;")
        fin_layout = QVBoxLayout(fin_card)
        fin_layout.setSpacing(4)

        def add_fin_row(label: str, val: str, is_total: bool = False, is_negative: bool = False):
            r = QHBoxLayout()
            lbl = QLabel(label)
            v = QLabel(val)
            if is_total:
                lbl.setStyleSheet("color: #0f172a; font-size: 13px; font-weight: 800;")
                v.setStyleSheet("color: #dc2626; font-size: 14px; font-weight: 800; font-family: 'Consolas', monospace;")
            else:
                lbl.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 600;")
                val_color = "#b91c1c" if is_negative else "#0f172a"
                v.setStyleSheet(f"color: {val_color}; font-size: 11px; font-weight: 700; font-family: 'Consolas', monospace;")
            r.addWidget(lbl)
            r.addStretch()
            r.addWidget(v)
            fin_layout.addLayout(r)

        add_fin_row("Gross Items Returned:", f"₱{self.ret.subtotal_returned:,.2f}")
        add_fin_row("Discount Reversal:", f"-₱{self.ret.discount_reversal:,.2f}", is_negative=True)
        add_fin_row("Refundable Taxable Base:", f"₱{self.ret.taxable_reversal:,.2f}")
        add_fin_row("Output VAT Reversal:", f"₱{self.ret.tax_reversal:,.2f}")

        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("background-color: #e2e8f0; max-height: 1px; margin: 4px 0;")
        fin_layout.addWidget(div)

        add_fin_row("TOTAL CUSTOMER REFUND:", f"₱{self.ret.total_refund_amount:,.2f}", is_total=True)
        body_layout.addWidget(fin_card)

        scroll.setWidget(body_widget)
        main_layout.addWidget(scroll)

        # ── 3. Footer ──
        footer = QFrame()
        footer.setStyleSheet("""
            background-color: #f8fafc;
            border-top: 1px solid #e2e8f0;
            border-bottom-left-radius: 12px;
            border-bottom-right-radius: 12px;
            padding: 10px 18px;
        """)
        ft_layout = QHBoxLayout(footer)
        ft_layout.setContentsMargins(0, 0, 0, 0)
        ft_layout.addStretch()

        btn_close_ft = QPushButton("Close")
        btn_close_ft.setFixedHeight(32)
        btn_close_ft.setFixedWidth(80)
        btn_close_ft.setCursor(Qt.PointingHandCursor)
        btn_close_ft.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                color: #0f172a;
            }
        """)
        btn_close_ft.clicked.connect(self.accept)
        ft_layout.addWidget(btn_close_ft)
        main_layout.addWidget(footer)

    def _on_header_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _on_header_mouse_move(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
