"""
RetailFlow POS - Apply Discount Dialog
Modal dialog for cashiers to apply fixed (₱) or percentage (%) discounts to a transaction.
"""

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)


class DiscountDialog(QDialog):
    """Modal checkout discount entry dialog."""

    def __init__(
        self,
        subtotal: Decimal,
        current_discount: Decimal = Decimal("0.00"),
        parent=None,
    ):
        super().__init__(parent)
        self.subtotal = subtotal
        self.applied_discount: Decimal = current_discount
        self.discount_type: str = "FIXED"  # FIXED or PERCENT

        self.setWindowTitle("Apply Transaction Discount")
        self.setFixedSize(400, 360)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            QDialog { background-color: #f8fafc; }
            QLabel#headerLabel { font-size: 18px; font-weight: 700; color: #0f172a; }
            QLabel#subtotalInfo { font-size: 12px; color: #64748b; font-weight: 500; }
            QLabel#fieldLabel { font-size: 13px; font-weight: 600; color: #334155; }
            QRadioButton { font-size: 13px; font-weight: 600; color: #0f172a; }
            QLineEdit { padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 6px; background: #ffffff; font-size: 14px; color: #0f172a; font-weight: 700; }
            QLineEdit:focus { border-color: #2563eb; }
            QPushButton#presetBtn { background-color: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 12px; font-weight: 700; padding: 6px 10px; }
            QPushButton#presetBtn:hover { background-color: #eff6ff; border-color: #2563eb; color: #2563eb; }
            QPushButton#applyButton { background-color: #2563eb; color: #ffffff; border: none; border-radius: 6px; padding: 10px; font-size: 14px; font-weight: 700; }
            QPushButton#applyButton:hover { background-color: #1d4ed8; }
            QPushButton#removeButton { background-color: #ffffff; color: #dc2626; border: 1px solid #fca5a5; border-radius: 6px; padding: 10px; font-size: 13px; font-weight: 600; }
            QPushButton#removeButton:hover { background-color: #fef2f2; }
            QPushButton#cancelButton { background-color: #e2e8f0; color: #334155; border: none; border-radius: 6px; padding: 10px; font-size: 13px; font-weight: 600; }
            QPushButton#cancelButton:hover { background-color: #cbd5e1; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Header
        header = QLabel("Apply Discount")
        header.setObjectName("headerLabel")
        layout.addWidget(header)

        subtotal_lbl = QLabel(f"Subtotal: ₱{self.subtotal:.2f}")
        subtotal_lbl.setObjectName("subtotalInfo")
        layout.addWidget(subtotal_lbl)

        # Type Selection (Fixed vs Percentage)
        type_layout = QHBoxLayout()
        self.rad_fixed = QRadioButton("Fixed Amount (₱)")
        self.rad_percent = QRadioButton("Percentage (%)")
        self.rad_fixed.setChecked(True)
        type_layout.addWidget(self.rad_fixed)
        type_layout.addWidget(self.rad_percent)
        layout.addLayout(type_layout)

        self.rad_fixed.toggled.connect(self._recalculate)
        self.rad_percent.toggled.connect(self._recalculate)

        # Value Field
        self.txt_val = QLineEdit()
        self.txt_val.setPlaceholderText("Enter discount value")
        self.txt_val.setText(f"{self.applied_discount:.2f}" if self.applied_discount > 0 else "")
        self.txt_val.textChanged.connect(self._recalculate)
        layout.addWidget(self.txt_val)

        # Preset Percentage Buttons
        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(6)
        for pct in [5, 10, 15, 20]:
            btn_pct = QPushButton(f"{pct}%")
            btn_pct.setObjectName("presetBtn")
            btn_pct.setCursor(Qt.PointingHandCursor)
            btn_pct.clicked.connect(lambda chk, p=pct: self._apply_preset_percent(p))
            preset_layout.addWidget(btn_pct)
        layout.addLayout(preset_layout)

        # Calculated Discount Result Preview
        self.lbl_preview = QLabel("Discount: ₱0.00")
        self.lbl_preview.setStyleSheet("font-size: 15px; font-weight: 800; color: #16a34a; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; padding: 8px; text-align: center;")
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_preview)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("cancelButton")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        if self.applied_discount > 0:
            self.btn_remove = QPushButton("Remove")
            self.btn_remove.setObjectName("removeButton")
            self.btn_remove.setCursor(Qt.PointingHandCursor)
            self.btn_remove.clicked.connect(self._remove_discount)
            btn_layout.addWidget(self.btn_remove)

        self.btn_apply = QPushButton("Apply Discount")
        self.btn_apply.setObjectName("applyButton")
        self.btn_apply.setDefault(True)
        self.btn_apply.setCursor(Qt.PointingHandCursor)
        self.btn_apply.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_apply)

        layout.addLayout(btn_layout)
        self._recalculate()

    def _apply_preset_percent(self, percent: int):
        self.rad_percent.setChecked(True)
        self.txt_val.setText(str(percent))

    def _remove_discount(self):
        self.applied_discount = Decimal("0.00")
        self.accept()

    def _recalculate(self):
        text = self.txt_val.text().strip()
        try:
            val = Decimal(text) if text else Decimal("0.00")
        except InvalidOperation:
            val = Decimal("0.00")

        if self.rad_percent.isChecked():
            self.discount_type = "PERCENT"
            calc = (self.subtotal * (val / Decimal("100"))).quantize(Decimal("0.01"))
            self.applied_discount = min(self.subtotal, calc)
        else:
            self.discount_type = "FIXED"
            self.applied_discount = min(self.subtotal, val)

        self.lbl_preview.setText(f"Discount: ₱{self.applied_discount:.2f}")
