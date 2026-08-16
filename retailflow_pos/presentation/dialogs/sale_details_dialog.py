"""
RetailFlow POS - Sale Details & Thermal Receipt Viewer Dialog
Displays authentic 80mm thermal POS receipt layout with line items, tax breakdown,
cashier details, reprint actions, and integrated Return History / Return Processing.
"""

from decimal import Decimal
from typing import List, Optional

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
from application.dto.sales_dto import SaleResponseDTO
from application.services.auth_service import AuthenticationService
from application.services.returns_service import ReturnsService
from infrastructure.database.models.auth import User
from presentation.dialogs.return_details_dialog import ReturnDetailsDialog
from presentation.styles.icons import IconManager


class SaleDetailsDialog(QDialog):
    """Modal displaying thermal receipt breakdown and return history for a completed sale."""

    def __init__(
        self,
        sale: SaleResponseDTO,
        returns_service: Optional[ReturnsService] = None,
        auth_service: Optional[AuthenticationService] = None,
        current_user: Optional[User] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.sale = sale
        self._returns_service = returns_service
        self._auth_service = auth_service
        self._current_user = current_user
        self._drag_pos = QPoint()

        self.setWindowTitle(f"Sale Receipt — #{sale.transaction_number}")
        self.setMinimumSize(480, 520)
        self.resize(540, 680)
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
            QPushButton:hover {
                background-color: #fee2e2;
            }
        """)
        btn_close.clicked.connect(self.reject)
        header_layout.addWidget(btn_close)

        container_layout.addWidget(header_card)

        # ── 2. Thermal Paper Scroll Area ──
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setStyleSheet("background-color: #f1f5f9; border: none;")

        receipt_wrapper = QWidget()
        receipt_wrapper.setStyleSheet("background-color: #f1f5f9;")
        receipt_wrapper_l = QVBoxLayout(receipt_wrapper)
        receipt_wrapper_l.setContentsMargins(18, 14, 18, 14)
        receipt_wrapper_l.setSpacing(12)

        # White Paper Sheet
        receipt_paper = QFrame()
        receipt_paper.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
        """)
        paper_l = QVBoxLayout(receipt_paper)
        paper_l.setContentsMargins(16, 16, 16, 16)
        paper_l.setSpacing(8)

        # Store Header
        store_title = QLabel("RETAILFLOW POS STORE")
        store_title.setAlignment(Qt.AlignCenter)
        store_title.setStyleSheet("font-size: 14px; font-weight: 800; color: #0f172a; letter-spacing: 0.5px;")
        paper_l.addWidget(store_title)

        store_sub = QLabel("Official Sales Invoice / Thermal Receipt")
        store_sub.setAlignment(Qt.AlignCenter)
        store_sub.setStyleSheet("font-size: 10px; color: #64748b;")
        paper_l.addWidget(store_sub)

        # Metadata Row
        meta_card = QFrame()
        meta_card.setStyleSheet("background-color: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 6px; padding: 6px 8px;")
        meta_l = QVBoxLayout(meta_card)
        meta_l.setSpacing(3)

        for label_text, val_text in [
            ("Terminal Ref:", f"POS-T1 · {self.sale.transaction_number}"),
            ("Payment Method:", f"{self.sale.payment_method.upper()}"),
            ("Status:", f"{self.sale.status.upper()}"),
        ]:
            r = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 600;")
            val = QLabel(val_text)
            val.setStyleSheet("color: #0f172a; font-size: 10px; font-weight: 700;")
            val.setAlignment(Qt.AlignRight)
            r.addWidget(lbl)
            r.addWidget(val)
            meta_l.addLayout(r)

        paper_l.addWidget(meta_card)

        # Line Items Table
        table_label = QLabel("PURCHASED ITEMS")
        table_label.setStyleSheet("font-size: 10px; font-weight: 800; color: #475569; letter-spacing: 0.5px; margin-top: 4px;")
        paper_l.addWidget(table_label)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Item Description", "Qty", "Price", "Total"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setFocusPolicy(Qt.NoFocus)
        table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                gridline-color: #f8fafc;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #475569;
                font-size: 9px;
                font-weight: 800;
                padding: 4px;
                border: none;
                border-bottom: 1px solid #e2e8f0;
            }
        """)

        table.setRowCount(len(self.sale.items))
        for row_idx, item in enumerate(self.sale.items):
            table.setRowHeight(row_idx, 28)

            desc = QTableWidgetItem(item.product_name)
            desc.setForeground(QColor("#0f172a"))
            table.setItem(row_idx, 0, desc)

            qty = QTableWidgetItem(f"{item.quantity}x")
            qty.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            qty.setForeground(QColor("#64748b"))
            table.setItem(row_idx, 1, qty)

            pr = QTableWidgetItem(f"₱{item.unit_price:,.2f}")
            pr.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            pr.setForeground(QColor("#64748b"))
            table.setItem(row_idx, 2, pr)

            tot = QTableWidgetItem(f"₱{item.subtotal:,.2f}")
            tot.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tot.setForeground(QColor("#0f172a"))
            table.setItem(row_idx, 3, tot)

        table.setFixedHeight(min(160, 30 + len(self.sale.items) * 28))
        paper_l.addWidget(table)

        # Financial Summary
        summary_card = QFrame()
        summary_card.setStyleSheet("background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 10px;")
        summary_l = QVBoxLayout(summary_card)
        summary_l.setSpacing(3)

        for label_text, val_text in [
            ("Subtotal:", f"₱{self.sale.subtotal:,.2f}"),
            ("Discount:", f"-₱{self.sale.discount_amount:,.2f}"),
            ("Output VAT (12%):", f"₱{self.sale.tax_amount:,.2f}"),
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

        # Total Line
        tot_r = QHBoxLayout()
        t_lbl = QLabel("TOTAL DUE:")
        t_lbl.setStyleSheet("font-size: 13px; font-weight: 800; color: #0f172a;")
        t_val = QLabel(f"₱{self.sale.total_amount:,.2f}")
        t_val.setStyleSheet("font-size: 16px; font-weight: 800; color: #047857;")
        t_val.setAlignment(Qt.AlignRight)
        tot_r.addWidget(t_lbl)
        tot_r.addWidget(t_val)
        summary_l.addLayout(tot_r)

        paper_l.addWidget(summary_card)
        receipt_wrapper_l.addWidget(receipt_paper)

        # ── Return History Section ──
        if self._returns_service:
            self.history_card = QFrame()
            self.history_card.setStyleSheet("background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px;")
            self.history_layout = QVBoxLayout(self.history_card)
            self.history_layout.setSpacing(8)
            receipt_wrapper_l.addWidget(self.history_card)
            self._load_return_history()

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

        # Process Return Button
        can_return = self._current_user and (self._current_user.is_admin() or self._current_user.has_permission("return_sales"))
        if self._returns_service and can_return:
            self.btn_process_return = QPushButton(" Process Return")
            self.btn_process_return.setIcon(IconManager.get_pixmap("arrow-left", color="#2563eb", size=13))
            self.btn_process_return.setFixedHeight(34)
            self.btn_process_return.setCursor(Qt.PointingHandCursor)
            self.btn_process_return.setStyleSheet("""
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
                QPushButton:disabled {
                    background-color: #f1f5f9;
                    color: #94a3b8;
                    border-color: #e2e8f0;
                }
            """)
            self.btn_process_return.clicked.connect(self._open_process_return)
            footer_layout.addWidget(self.btn_process_return)
            self._update_return_button_state()

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

    def _load_return_history(self):
        """Fetch and render completed returns for this sale."""
        while self.history_layout.count():
            item = self.history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            returns = self._returns_service.get_returns_for_sale(self.sale.id, actor=self._current_user)

            hdr_row = QHBoxLayout()
            lbl_hdr = QLabel(f"RETURN HISTORY ({len(returns)})")
            lbl_hdr.setStyleSheet("color: #475569; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
            hdr_row.addWidget(lbl_hdr)
            hdr_row.addStretch()
            self.history_layout.addLayout(hdr_row)

            if not returns:
                lbl_none = QLabel("No return records for this transaction.")
                lbl_none.setStyleSheet("color: #94a3b8; font-size: 11px; font-style: italic;")
                self.history_layout.addWidget(lbl_none)
                return

            for r in returns:
                r_card = QFrame()
                r_card.setStyleSheet("background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 10px;")
                r_layout = QHBoxLayout(r_card)
                r_layout.setContentsMargins(0, 0, 0, 0)

                v_info = QVBoxLayout()
                v_info.setSpacing(2)

                lbl_num = QLabel(f"Voucher #{r.return_number}  ·  {r.return_date}")
                lbl_num.setStyleSheet("color: #0f172a; font-size: 11px; font-weight: 700; font-family: 'Consolas', monospace;")
                v_info.addWidget(lbl_num)

                lbl_meta = QLabel(f"Refunded: ₱{r.total_refund_amount:,.2f} ({r.refund_payment_method.title()}) · Cashier: {r.cashier_name}")
                lbl_meta.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 500;")
                v_info.addWidget(lbl_meta)
                r_layout.addLayout(v_info, 1)

                btn_view = QPushButton("View Details")
                btn_view.setFixedHeight(26)
                btn_view.setCursor(Qt.PointingHandCursor)
                btn_view.setStyleSheet("""
                    QPushButton {
                        background-color: #ffffff;
                        color: #2563eb;
                        border: 1px solid #bfdbfe;
                        border-radius: 4px;
                        font-size: 10px;
                        font-weight: 700;
                        padding: 0 8px;
                    }
                    QPushButton:hover { background-color: #eff6ff; }
                """)
                btn_view.clicked.connect(lambda checked, ret_dto=r: self._open_return_details(ret_dto))
                r_layout.addWidget(btn_view)
                self.history_layout.addWidget(r_card)

        except Exception as e:
            lbl_err = QLabel(f"Could not load returns: {str(e)}")
            lbl_err.setStyleSheet("color: #b91c1c; font-size: 10px;")
            self.history_layout.addWidget(lbl_err)

    def _update_return_button_state(self):
        """Disable Process Return button if sale is already fully returned."""
        if not hasattr(self, "btn_process_return"):
            return
        try:
            summary = self._returns_service.get_sale_return_summary(self.sale.id, actor=self._current_user)
            if summary.derived_state == "full":
                self.btn_process_return.setEnabled(False)
                self.btn_process_return.setToolTip("Sale has already been fully returned.")
            else:
                self.btn_process_return.setEnabled(True)
                self.btn_process_return.setToolTip("")
        except Exception:
            pass

    def _open_process_return(self):
        """Open ProcessReturnDialog modal."""
        from presentation.dialogs.process_return_dialog import ProcessReturnDialog
        dlg = ProcessReturnDialog(
            sale=self.sale,
            current_user=self._current_user,
            returns_service=self._returns_service,
            auth_service=self._auth_service,
            parent=self,
        )
        if dlg.exec() == QDialog.Accepted and dlg.final_return_dto:
            self._load_return_history()
            self._update_return_button_state()
            if self.parent() and hasattr(self.parent(), "load_sales"):
                self.parent().load_sales()

    def _open_return_details(self, return_dto: SalesReturnDTO):
        """Open read-only ReturnDetailsDialog."""
        dlg = ReturnDetailsDialog(return_dto=return_dto, parent=self)
        dlg.exec()

    def _on_header_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _on_header_mouse_move(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
