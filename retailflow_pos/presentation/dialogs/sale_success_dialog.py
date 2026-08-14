"""
RetailFlow POS - Sale Success / Receipt Dialog
High-contrast modal dialog displayed after successful checkout completion.
Designed following Senior UI/UX Guidelines as a clean, modern Digital Receipt Card.
"""

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from application.dto.sales_dto import SaleResponseDTO
from presentation.styles.icons import IconManager


class SaleSuccessDialog(QDialog):
    """Modal dialog displaying transaction receipt breakdown and print options after checkout."""

    def __init__(self, response: SaleResponseDTO, parent=None):
        super().__init__(parent)
        self.response = response
        self.setObjectName("saleSuccessDialog")
        self.setWindowTitle("Sale Completed")
        self.setFixedSize(420, 500)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)

        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            QDialog#saleSuccessDialog {
                background-color: #ffffff;
                color: #0f172a;
            }
            QDialog#saleSuccessDialog QLabel {
                color: #0f172a;
                border: none;
                background: transparent;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # ── 1. Hero Success Banner ──
        banner = QFrame()
        banner.setObjectName("successBanner")
        banner.setStyleSheet("""
            QFrame#successBanner {
                background-color: #ecfdf5;
                border: 1px solid #a7f3d0;
                border-radius: 10px;
                padding: 12px;
            }
            QFrame#successBanner QLabel {
                border: none;
                background: transparent;
            }
        """)
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(0, 0, 0, 0)
        banner_layout.setSpacing(3)
        banner_layout.setAlignment(Qt.AlignCenter)

        icon_lbl = QLabel("✓")
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 28px; font-weight: 900; color: #16a34a;")
        banner_layout.addWidget(icon_lbl)

        title_lbl = QLabel("Sale Completed Successfully!")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 800; color: #065f46;")
        banner_layout.addWidget(title_lbl)

        layout.addWidget(banner)

        # ── 2. Digital Receipt Card ──
        receipt_card = QFrame()
        receipt_card.setObjectName("receiptCard")
        receipt_card.setStyleSheet("""
            QFrame#receiptCard {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 14px 16px;
            }
            QFrame#receiptCard QLabel {
                border: none;
                background: transparent;
                padding: 0px;
                margin: 0px;
            }
        """)
        receipt_layout = QVBoxLayout(receipt_card)
        receipt_layout.setContentsMargins(0, 0, 0, 0)
        receipt_layout.setSpacing(6)

        # Receipt Header Title
        receipt_hdr = QLabel("RETAILFLOW POS RECEIPT")
        receipt_hdr.setAlignment(Qt.AlignCenter)
        receipt_hdr.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748b; letter-spacing: 1.5px;")
        receipt_layout.addWidget(receipt_hdr)

        # Dotted Divider
        div1 = QLabel("──────────────────────────────────────────")
        div1.setAlignment(Qt.AlignCenter)
        div1.setStyleSheet("color: #cbd5e1; font-size: 10px;")
        receipt_layout.addWidget(div1)

        # Transaction No Row
        txn_row = QHBoxLayout()
        txn_lbl = QLabel("Transaction No:")
        txn_lbl.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 500;")
        txn_row.addWidget(txn_lbl)

        lbl_txn = QLabel(self.response.transaction_number)
        lbl_txn.setStyleSheet("color: #0f172a; font-size: 12px; font-weight: 700; font-family: monospace;")
        lbl_txn.setAlignment(Qt.AlignRight)
        txn_row.addWidget(lbl_txn)
        receipt_layout.addLayout(txn_row)

        # Date & Time Row
        date_row = QHBoxLayout()
        date_lbl = QLabel("Date & Time:")
        date_lbl.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 500;")
        date_row.addWidget(date_lbl)

        created_at_val = getattr(self.response, "created_at", None)
        if hasattr(created_at_val, "strftime"):
            time_str = created_at_val.strftime("%Y-%m-%d %H:%M")
        else:
            time_str = str(created_at_val) if created_at_val else "Just now"

        lbl_date = QLabel(time_str)
        lbl_date.setStyleSheet("color: #0f172a; font-size: 12px; font-weight: 600;")
        lbl_date.setAlignment(Qt.AlignRight)
        date_row.addWidget(lbl_date)
        receipt_layout.addLayout(date_row)

        # Payment Method Row
        method_row = QHBoxLayout()
        method_lbl = QLabel("Payment Method:")
        method_lbl.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 500;")
        method_row.addWidget(method_lbl)

        lbl_method = QLabel(self.response.payment_method)
        lbl_method.setStyleSheet("color: #0f172a; font-size: 12px; font-weight: 700;")
        lbl_method.setAlignment(Qt.AlignRight)
        method_row.addWidget(lbl_method)
        receipt_layout.addLayout(method_row)

        # Dotted Divider
        div2 = QLabel("──────────────────────────────────────────")
        div2.setAlignment(Qt.AlignCenter)
        div2.setStyleSheet("color: #cbd5e1; font-size: 10px;")
        receipt_layout.addWidget(div2)

        # Subtotal Row
        sub_row = QHBoxLayout()
        sub_lbl = QLabel("Subtotal:")
        sub_lbl.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 500;")
        sub_row.addWidget(sub_lbl)

        lbl_sub = QLabel(f"${self.response.subtotal:.2f}")
        lbl_sub.setStyleSheet("color: #0f172a; font-size: 12px; font-weight: 600;")
        lbl_sub.setAlignment(Qt.AlignRight)
        sub_row.addWidget(lbl_sub)
        receipt_layout.addLayout(sub_row)

        # Tax Row
        tax_row = QHBoxLayout()
        tax_lbl = QLabel("Tax (12% VAT):")
        tax_lbl.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 500;")
        tax_row.addWidget(tax_lbl)

        lbl_tax = QLabel(f"${self.response.tax_amount:.2f}")
        lbl_tax.setStyleSheet("color: #0f172a; font-size: 12px; font-weight: 600;")
        lbl_tax.setAlignment(Qt.AlignRight)
        tax_row.addWidget(lbl_tax)
        receipt_layout.addLayout(tax_row)

        # Dotted Divider
        div3 = QLabel("──────────────────────────────────────────")
        div3.setAlignment(Qt.AlignCenter)
        div3.setStyleSheet("color: #cbd5e1; font-size: 10px;")
        receipt_layout.addWidget(div3)

        # TOTAL PAID Row
        tot_row = QHBoxLayout()
        tot_lbl = QLabel("TOTAL PAID:")
        tot_lbl.setStyleSheet("color: #065f46; font-size: 13px; font-weight: 800; letter-spacing: 0.5px;")
        tot_row.addWidget(tot_lbl)

        lbl_tot = QLabel(f"${self.response.total_amount:.2f}")
        lbl_tot.setStyleSheet("color: #047857; font-size: 20px; font-weight: 800;")
        lbl_tot.setAlignment(Qt.AlignRight)
        tot_row.addWidget(lbl_tot)
        receipt_layout.addLayout(tot_row)

        # Amount Paid Row
        amount_paid_val = getattr(self.response, "amount_paid", getattr(self.response, "amount_tendered", Decimal("0.00")))
        tend_row = QHBoxLayout()
        tend_lbl = QLabel("Amount Paid:")
        tend_lbl.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 500;")
        tend_row.addWidget(tend_lbl)

        lbl_tend = QLabel(f"${amount_paid_val:.2f}")
        lbl_tend.setStyleSheet("color: #0f172a; font-size: 13px; font-weight: 600;")
        lbl_tend.setAlignment(Qt.AlignRight)
        tend_row.addWidget(lbl_tend)
        receipt_layout.addLayout(tend_row)

        # Change Due Row
        chg_row = QHBoxLayout()
        chg_lbl = QLabel("Change Due:")
        chg_lbl.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 500;")
        chg_row.addWidget(chg_lbl)

        lbl_chg = QLabel(f"${self.response.change_given:.2f}")
        lbl_chg.setStyleSheet("color: #2563eb; font-size: 15px; font-weight: 800;")
        lbl_chg.setAlignment(Qt.AlignRight)
        chg_row.addWidget(lbl_chg)
        receipt_layout.addLayout(chg_row)

        layout.addWidget(receipt_card)

        layout.addStretch()

        # ── 3. Action Buttons ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_print = QPushButton(" Print Receipt")
        self.btn_print.setIcon(IconManager.get_icon("print", color="#0f172a", size=16))
        self.btn_print.setFixedHeight(38)
        self.btn_print.setCursor(Qt.PointingHandCursor)
        self.btn_print.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                border-color: #94a3b8;
            }
        """)
        self.btn_print.clicked.connect(self._on_print_receipt)
        btn_layout.addWidget(self.btn_print, stretch=1)

        self.btn_done = QPushButton(" Start New Sale")
        self.btn_done.setIcon(IconManager.get_icon("check", color="#ffffff", size=16))
        self.btn_done.setFixedHeight(38)
        self.btn_done.setDefault(True)
        self.btn_done.setCursor(Qt.PointingHandCursor)
        self.btn_done.setStyleSheet("""
            QPushButton {
                background-color: #16a34a;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #15803d;
            }
        """)
        self.btn_done.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_done, stretch=2)

        layout.addLayout(btn_layout)

    def _on_print_receipt(self):
        """Simulate printing receipt."""
        QMessageBox.information(
            self,
            "Print Receipt",
            f"Receipt for transaction '{self.response.transaction_number}' sent to default printer.",
        )
