"""
RetailFlow POS - Payment Processing Dialog
High-speed cashier payment processing modal with segmented payment method tabs,
quick tender shortcuts, live change calculation, and reference number validation.
"""

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from presentation.styles.icons import IconManager


class PaymentDialog(QDialog):
    """Modal checkout payment entry dialog."""

    def __init__(
        self,
        total_amount: Decimal,
        subtotal: Decimal = Decimal("0.00"),
        discount: Decimal = Decimal("0.00"),
        tax: Decimal = Decimal("0.00"),
        parent=None,
    ):
        super().__init__(parent)
        self.total_amount = total_amount
        self.subtotal = subtotal
        self.discount = discount
        self.tax = tax

        self.payment_method: str = "CASH"
        self.amount_tendered: Decimal = Decimal("0.00")
        self.change_given: Decimal = Decimal("0.00")
        self.reference_number: str = ""

        self.setWindowTitle("Checkout - Payment Processing")
        self.setFixedSize(500, 520)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #f8fafc;
            }
            QLabel#headerLabel {
                font-size: 18px;
                font-weight: 800;
                color: #0f172a;
                letter-spacing: -0.3px;
            }
            QLabel#fieldLabel {
                font-size: 12px;
                font-weight: 700;
                color: #334155;
            }
            QLineEdit {
                padding: 8px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background-color: #ffffff;
                font-size: 15px;
                font-weight: 700;
                color: #0f172a;
            }
            QLineEdit:focus {
                border-color: #2563eb;
            }
            QPushButton#quickCashBtn {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                padding: 6px 10px;
            }
            QPushButton#quickCashBtn:hover {
                background-color: #eff6ff;
                border-color: #2563eb;
                color: #2563eb;
            }
            QPushButton#payButton {
                background-color: #16a34a;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-size: 15px;
                font-weight: 800;
            }
            QPushButton#payButton:hover {
                background-color: #15803d;
            }
            QPushButton#payButton:disabled {
                background-color: #e2e8f0;
                color: #94a3b8;
            }
            QPushButton#cancelButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 12px;
                font-size: 14px;
                font-weight: 700;
            }
            QPushButton#cancelButton:hover {
                background-color: #f1f5f9;
                color: #0f172a;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(12)

        # 1. Header
        hdr_l = QHBoxLayout()
        header = QLabel("Complete Transaction")
        header.setObjectName("headerLabel")
        hdr_l.addWidget(header)
        hdr_l.addStretch()
        layout.addLayout(hdr_l)

        # 2. Total Amount Hero Card
        total_card = QFrame()
        total_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 12px 16px;
            }
            QLabel { border: none; background: transparent; }
        """)
        tc_layout = QHBoxLayout(total_card)
        tc_layout.setContentsMargins(0, 0, 0, 0)

        tc_text = QVBoxLayout()
        tc_text.setSpacing(2)
        tc_lbl = QLabel("TOTAL AMOUNT DUE")
        tc_lbl.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        self.lbl_total = QLabel(f"₱{self.total_amount:,.2f}")
        self.lbl_total.setStyleSheet("font-size: 26px; font-weight: 800; color: #0f172a; letter-spacing: -0.5px;")
        tc_text.addWidget(tc_lbl)
        tc_text.addWidget(self.lbl_total)
        tc_layout.addLayout(tc_text)
        tc_layout.addStretch()

        layout.addWidget(total_card)

        # 3. Payment Method Tabs
        lbl_method = QLabel("PAYMENT METHOD")
        lbl_method.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        layout.addWidget(lbl_method)

        method_layout = QHBoxLayout()
        method_layout.setSpacing(6)
        self.method_buttons: dict[str, QPushButton] = {}

        for m_name, icon_key in [("CASH", "pos"), ("CARD", "star"), ("GCASH", "tag"), ("MAYA", "clock")]:
            btn = QPushButton(f" {m_name}")
            btn.setFixedHeight(36)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda chk, m=m_name: self._set_method(m))
            method_layout.addWidget(btn)
            self.method_buttons[m_name] = btn

        layout.addLayout(method_layout)
        self._update_method_buttons()

        # 4. Form Fields
        form_card = QFrame()
        form_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 12px 16px;
            }
            QLabel { border: none; background: transparent; }
        """)
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(10)

        # Amount Tendered
        t_row = QVBoxLayout()
        t_row.setSpacing(4)
        t_lbl = QLabel("Amount Tendered (₱):")
        t_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #334155;")
        self.txt_tendered = QLineEdit()
        self.txt_tendered.setPlaceholderText(f"{self.total_amount:.2f}")
        self.txt_tendered.setText(f"{self.total_amount:.2f}")
        self.txt_tendered.textChanged.connect(self._recalculate_change)
        t_row.addWidget(t_lbl)
        t_row.addWidget(self.txt_tendered)
        form_layout.addLayout(t_row)

        # Quick Cash Shortcuts
        self.quick_layout = QHBoxLayout()
        self.quick_layout.setSpacing(6)

        btn_exact = QPushButton("Exact")
        btn_exact.setObjectName("quickCashBtn")
        btn_exact.setCursor(Qt.PointingHandCursor)
        btn_exact.clicked.connect(lambda: self.txt_tendered.setText(f"{self.total_amount:.2f}"))
        self.quick_layout.addWidget(btn_exact)

        base = int(self.total_amount)
        denominations = [base + 50, base + 100, 500 if base < 500 else 1000, 1000 if base < 1000 else 2000]
        # Deduplicate and sort
        unique_denoms = sorted(list(set([d for d in denominations if d >= self.total_amount])))[:4]
        if not unique_denoms:
            unique_denoms = [int(self.total_amount) + 50, int(self.total_amount) + 100]

        for amt in unique_denoms:
            btn_amt = QPushButton(f"₱{amt}")
            btn_amt.setObjectName("quickCashBtn")
            btn_amt.setCursor(Qt.PointingHandCursor)
            btn_amt.clicked.connect(lambda chk, a=amt: self.txt_tendered.setText(f"{a:.2f}"))
            self.quick_layout.addWidget(btn_amt)

        form_layout.addLayout(self.quick_layout)

        # Reference Number (for digital payments)
        self.ref_row = QVBoxLayout()
        self.ref_row.setSpacing(4)
        self.lbl_ref = QLabel("Reference / Approval Number:")
        self.lbl_ref.setStyleSheet("font-size: 11px; font-weight: 700; color: #334155;")
        self.txt_ref = QLineEdit()
        self.txt_ref.setPlaceholderText("e.g. 104829375019")
        self.ref_row.addWidget(self.lbl_ref)
        self.ref_row.addWidget(self.txt_ref)
        form_layout.addLayout(self.ref_row)
        self.lbl_ref.hide()
        self.txt_ref.hide()

        layout.addWidget(form_card)

        # 5. Live Change Display Card
        self.lbl_change = QLabel("Change: ₱0.00")
        self.lbl_change.setAlignment(Qt.AlignCenter)
        self.lbl_change.setStyleSheet(
            "font-size: 16px; font-weight: 800; color: #047857; background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px; padding: 10px;"
        )
        layout.addWidget(self.lbl_change)

        # 6. Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("cancelButton")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel, stretch=1)

        self.btn_pay = QPushButton("Complete Sale (Enter)")
        self.btn_pay.setObjectName("payButton")
        self.btn_pay.setDefault(True)
        self.btn_pay.setCursor(Qt.PointingHandCursor)
        self.btn_pay.clicked.connect(self._attempt_payment)
        btn_layout.addWidget(self.btn_pay, stretch=2)

        layout.addLayout(btn_layout)

        self._recalculate_change()

    def _set_method(self, method: str):
        self.payment_method = method
        self._update_method_buttons()

        is_digital = method in ["CARD", "GCASH", "MAYA"]
        if is_digital:
            self.lbl_ref.show()
            self.txt_ref.show()
            self.txt_tendered.setText(f"{self.total_amount:.2f}")
        else:
            self.lbl_ref.hide()
            self.txt_ref.hide()

        self._recalculate_change()

    def _update_method_buttons(self):
        for m, btn in self.method_buttons.items():
            if m == self.payment_method:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2563eb;
                        color: #ffffff;
                        border: none;
                        border-radius: 6px;
                        font-size: 12px;
                        font-weight: 800;
                    }
                """)
            else:
                btn.setStyleSheet("""
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
                        border-color: #94a3b8;
                    }
                """)

    def _recalculate_change(self):
        text = self.txt_tendered.text().strip()
        try:
            val = Decimal(text) if text else Decimal("0.00")
        except InvalidOperation:
            val = Decimal("0.00")

        self.amount_tendered = val
        diff = val - self.total_amount
        if diff >= 0:
            self.change_given = diff
            self.lbl_change.setText(f"Change Due:  ₱{diff:,.2f}")
            self.lbl_change.setStyleSheet(
                "font-size: 16px; font-weight: 800; color: #047857; background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px; padding: 10px;"
            )
            self.btn_pay.setEnabled(True)
        else:
            self.change_given = Decimal("0.00")
            shortage = abs(diff)
            self.lbl_change.setText(f"Shortage:  -₱{shortage:,.2f}")
            self.lbl_change.setStyleSheet(
                "font-size: 16px; font-weight: 800; color: #dc2626; background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 10px;"
            )
            self.btn_pay.setEnabled(False)

    def _attempt_payment(self):
        if self.amount_tendered < self.total_amount:
            QMessageBox.warning(self, "Insufficient Payment", "Amount tendered is less than total due.")
            return

        if self.payment_method in ["CARD", "GCASH", "MAYA"]:
            ref = self.txt_ref.text().strip()
            if not ref:
                QMessageBox.warning(self, "Reference Required", f"Please enter reference number for {self.payment_method}.")
                self.txt_ref.setFocus()
                return
            self.reference_number = ref

        self.accept()
