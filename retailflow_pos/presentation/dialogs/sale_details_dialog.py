"""
RetailFlow POS - Sale Details & Thermal Receipt Viewer Dialog
Displays authentic 80mm thermal POS receipt layout with line items, tax breakdown,
cashier details, and reprint actions.
"""

from decimal import Decimal

from PySide6.QtCore import QPoint, Qt
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

from application.dto.sales_dto import SaleResponseDTO
from presentation.styles.icons import IconManager


class SaleDetailsDialog(QDialog):
    """Modal displaying thermal receipt breakdown for a completed sale."""

    def __init__(self, sale: SaleResponseDTO, parent: QWidget | None = None):
        super().__init__(parent)
        self.sale = sale
        self._drag_pos = QPoint()

        self.setWindowTitle(f"Sale Receipt — #{sale.transaction_number}")
        self.setFixedSize(520, 640)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self._init_ui()

    @staticmethod
    def _format_datetime(dt_str: str) -> str:
        try:
            from datetime import datetime
            cleaned = dt_str.replace("Z", "")
            if "T" in cleaned:
                dt = datetime.fromisoformat(cleaned)
            else:
                dt = datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%b %d, %Y · %I:%M %p")
        except Exception:
            return dt_str

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

        hdr_title = QLabel(f"Transaction #{self.sale.transaction_number}")
        hdr_title.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: 800; font-family: 'Consolas', monospace;")
        hdr_text_layout.addWidget(hdr_title)

        hdr_sub = QLabel(f"Completed sale · {self._format_datetime(self.sale.created_at)}")
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

        # ── 2. Scrollable Thermal Receipt Card ──
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { background-color: #f1f5f9; border: none; }")

        receipt_wrapper = QWidget()
        receipt_wrapper_l = QVBoxLayout(receipt_wrapper)
        receipt_wrapper_l.setContentsMargins(18, 14, 18, 14)
        receipt_wrapper_l.setAlignment(Qt.AlignHCenter)

        # White Paper Receipt Box
        receipt_paper = QFrame()
        receipt_paper.setFixedWidth(420)
        receipt_paper.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 16px;
            }
        """)
        paper_l = QVBoxLayout(receipt_paper)
        paper_l.setContentsMargins(0, 0, 0, 0)
        paper_l.setSpacing(8)

        # Receipt Brand Header
        brand_l = QVBoxLayout()
        brand_l.setSpacing(2)
        brand_l.setAlignment(Qt.AlignCenter)

        store_name = QLabel("RETAILFLOW POS STORE")
        store_name.setAlignment(Qt.AlignCenter)
        store_name.setStyleSheet("font-size: 15px; font-weight: 800; color: #0f172a; letter-spacing: 0.5px;")
        brand_l.addWidget(store_name)

        doc_type = QLabel("OFFICIAL SALES RECEIPT")
        doc_type.setAlignment(Qt.AlignCenter)
        doc_type.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748b; letter-spacing: 1px;")
        brand_l.addWidget(doc_type)

        vat_reg = QLabel("VAT Reg. TIN: 000-123-456-789")
        vat_reg.setAlignment(Qt.AlignCenter)
        vat_reg.setStyleSheet("font-size: 10px; color: #94a3b8;")
        brand_l.addWidget(vat_reg)
        paper_l.addLayout(brand_l)

        # Divider Dash
        dash1 = QLabel("--------------------------------------------------")
        dash1.setAlignment(Qt.AlignCenter)
        dash1.setStyleSheet("color: #cbd5e1; font-family: monospace; font-size: 10px;")
        paper_l.addWidget(dash1)

        # Meta info
        meta_grid = QVBoxLayout()
        meta_grid.setSpacing(3)

        def make_meta_row(k: str, v: str):
            r = QHBoxLayout()
            kl = QLabel(k)
            kl.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 500;")
            vl = QLabel(v)
            vl.setStyleSheet("font-size: 11px; color: #0f172a; font-weight: 700;")
            vl.setAlignment(Qt.AlignRight)
            r.addWidget(kl)
            r.addWidget(vl)
            return r

        meta_grid.addLayout(make_meta_row("TXN #:", self.sale.transaction_number))
        meta_grid.addLayout(make_meta_row("Date/Time:", self._format_datetime(self.sale.created_at)))
        meta_grid.addLayout(make_meta_row("Payment:", self.sale.payment_method.upper()))
        meta_grid.addLayout(make_meta_row("Status:", "COMPLETED"))
        paper_l.addLayout(meta_grid)

        # Divider Dash
        dash2 = QLabel("--------------------------------------------------")
        dash2.setAlignment(Qt.AlignCenter)
        dash2.setStyleSheet("color: #cbd5e1; font-family: monospace; font-size: 10px;")
        paper_l.addWidget(dash2)

        # Items Table
        self.tbl_items = QTableWidget()
        self.tbl_items.setColumnCount(4)
        self.tbl_items.setHorizontalHeaderLabels(["ITEM", "PRICE", "QTY", "TOTAL"])
        self.tbl_items.verticalHeader().setVisible(False)
        self.tbl_items.setShowGrid(False)
        self.tbl_items.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                border: none;
                font-size: 11px;
                color: #0f172a;
            }
            QHeaderView::section {
                background-color: #ffffff;
                color: #64748b;
                font-size: 9px;
                font-weight: 800;
                letter-spacing: 0.5px;
                border: none;
                border-bottom: 1px dashed #cbd5e1;
                padding: 4px;
            }
            QTableWidget::item {
                border: none;
                padding: 2px 4px;
            }
        """)

        header = self.tbl_items.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        self.tbl_items.setRowCount(len(self.sale.items))
        for row, item in enumerate(self.sale.items):
            self.tbl_items.setRowHeight(row, 28)

            name_item = QTableWidgetItem(item.product_name)
            name_item.setFlags(Qt.ItemIsEnabled)
            self.tbl_items.setItem(row, 0, name_item)

            price_item = QTableWidgetItem(f"₱{item.unit_price:.2f}")
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            price_item.setFlags(Qt.ItemIsEnabled)
            self.tbl_items.setItem(row, 1, price_item)

            qty_item = QTableWidgetItem(str(item.quantity))
            qty_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            qty_item.setFlags(Qt.ItemIsEnabled)
            self.tbl_items.setItem(row, 2, qty_item)

            sub_item = QTableWidgetItem(f"₱{item.subtotal:.2f}")
            sub_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            sub_item.setFlags(Qt.ItemIsEnabled)
            self.tbl_items.setItem(row, 3, sub_item)

        paper_l.addWidget(self.tbl_items)
        self.tbl_items.setFixedHeight(min(200, len(self.sale.items) * 28 + 35))

        # Divider Dash
        dash3 = QLabel("--------------------------------------------------")
        dash3.setAlignment(Qt.AlignCenter)
        dash3.setStyleSheet("color: #cbd5e1; font-family: monospace; font-size: 10px;")
        paper_l.addWidget(dash3)

        # Financial Summary Section
        summary_l = QVBoxLayout()
        summary_l.setSpacing(3)

        for label_text, val_text in [
            ("Subtotal:", f"₱{self.sale.subtotal:,.2f}"),
            ("Tax (12% VAT):", f"₱{self.sale.tax_amount:,.2f}"),
            ("Discount:", f"-₱{self.sale.discount_amount:,.2f}" if self.sale.discount_amount > 0 else "₱0.00"),
        ]:
            r = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 500;")
            val = QLabel(val_text)
            val.setStyleSheet("color: #0f172a; font-size: 11px; font-weight: 700;")
            val.setAlignment(Qt.AlignRight)
            r.addWidget(lbl)
            r.addWidget(val)
            summary_l.addLayout(r)

        # Total Paid Row
        tot_r = QHBoxLayout()
        t_lbl = QLabel("TOTAL PAID:")
        t_lbl.setStyleSheet("font-size: 13px; font-weight: 800; color: #0f172a;")
        t_val = QLabel(f"₱{self.sale.total_amount:,.2f}")
        t_val.setStyleSheet("font-size: 18px; font-weight: 800; color: #047857;")
        t_val.setAlignment(Qt.AlignRight)
        tot_r.addWidget(t_lbl)
        tot_r.addWidget(t_val)
        summary_l.addLayout(tot_r)

        # Tender & Change
        for label_text, val_text in [
            ("Amount Tendered:", f"₱{self.sale.amount_paid:,.2f}"),
            ("Change Given:", f"₱{self.sale.change_given:,.2f}"),
        ]:
            r = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 500;")
            val = QLabel(val_text)
            val.setStyleSheet("color: #0f172a; font-size: 11px; font-weight: 700;")
            val.setAlignment(Qt.AlignRight)
            r.addWidget(lbl)
            r.addWidget(val)
            summary_l.addLayout(r)

        paper_l.addLayout(summary_l)

        # Footer Thank You Note
        foot_note = QLabel("Thank you for shopping with us!\nPlease keep this receipt for returns.")
        foot_note.setAlignment(Qt.AlignCenter)
        foot_note.setStyleSheet("font-size: 10px; color: #94a3b8; margin-top: 10px;")
        paper_l.addWidget(foot_note)

        receipt_wrapper_l.addWidget(receipt_paper)
        scroll_area.setWidget(receipt_wrapper)
        container_layout.addWidget(scroll_area, stretch=1)

        # ── 3. Action Buttons Footer ──
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

        btn_print = QPushButton(" Re-print Receipt")
        btn_print.setIcon(IconManager.get_pixmap("print", color="#2563eb", size=14))
        btn_print.setFixedHeight(34)
        btn_print.setCursor(Qt.PointingHandCursor)
        btn_print.setStyleSheet("""
            QPushButton {
                background-color: #eff6ff;
                color: #2563eb;
                border: 1px solid #bfdbfe;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                padding: 0px 14px;
            }
            QPushButton:hover {
                background-color: #2563eb;
                color: #ffffff;
            }
        """)
        btn_print.clicked.connect(self._reprint_receipt)
        footer_layout.addWidget(btn_print)

        footer_layout.addStretch()

        btn_close_ft = QPushButton("Close")
        btn_close_ft.setFixedHeight(34)
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
        footer_layout.addWidget(btn_close_ft)

        container_layout.addWidget(footer_card)

    def _on_header_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _on_header_mouse_move(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def _reprint_receipt(self):
        """Simulate re-printing receipt."""
        from presentation.dialogs.sale_success_dialog import SaleSuccessDialog
        dlg = SaleSuccessDialog(self.sale, self.parent())
        dlg.exec()
