"""
RetailFlow POS - Process Customer Return Dialog
Production modal for line-item return selection, condition grading, non-mutating preview,
manager approval, and idempotent return processing.
"""

import uuid
from decimal import Decimal
from typing import Dict, List, Optional

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.constants import (
    PaymentMethod,
    RefundMethod,
    ReturnDisposition,
    ReturnReason,
)
from application.dto.returns_dto import (
    ProcessReturnRequestDTO,
    ReturnableLineItemDTO,
    ReturnItemRequestDTO,
    ReturnPreviewDTO,
    SalesReturnDTO,
)
from application.dto.sales_dto import SaleResponseDTO
from application.services.auth_service import AuthenticationService
from application.services.returns_service import SUPPORTED_ELECTRONIC_METHODS, ReturnsService
from domain.exceptions import AuthorizationError, RetailFlowError, ValidationError
from infrastructure.database.models.auth import User
from presentation.dialogs.manager_override_dialog import ManagerOverrideDialog
from presentation.styles.icons import IconManager


class ProcessReturnDialog(QDialog):
    """Interactive modal dialog for processing customer returns."""

    def __init__(
        self,
        sale: SaleResponseDTO,
        current_user: User,
        returns_service: ReturnsService,
        auth_service: AuthenticationService,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.sale = sale
        self._current_user = current_user
        self._returns_service = returns_service
        self._auth_service = auth_service
        self.idempotency_key = f"UI-{uuid.uuid4()}"
        self.final_return_dto: Optional[SalesReturnDTO] = None
        self._drag_pos = QPoint()

        self._returnable_lines: List[ReturnableLineItemDTO] = []
        self._line_controls: Dict[int, Dict] = {}
        self._latest_preview: Optional[ReturnPreviewDTO] = None

        # Debounce timer for preview calculations
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(150)
        self._preview_timer.timeout.connect(self._fetch_preview)

        self.setWindowTitle(f"Process Return — #{sale.transaction_number}")
        self.setMinimumSize(600, 520)
        self.resize(740, 680)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self._init_ui()
        self._load_returnable_items()

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

        hdr_title = QLabel(f"Process Return — #{self.sale.transaction_number}")
        hdr_title.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: 800; font-family: 'Consolas', monospace;")
        hdr_text_layout.addWidget(hdr_title)

        hdr_sub = QLabel(f"Original Sale: ₱{self.sale.total_amount:,.2f} ({self.sale.payment_method.upper()}) · Operator: {self._current_user.full_name}")
        hdr_sub.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 500;")
        hdr_text_layout.addWidget(hdr_sub)
        hdr_layout.addLayout(hdr_text_layout)
        hdr_layout.addStretch()

        btn_close = QPushButton()
        btn_close.setIcon(IconManager.get_pixmap("close", color="#64748b", size=14))
        btn_close.setFixedSize(28, 28)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("background: transparent; border: none; border-radius: 6px;")
        btn_close.clicked.connect(self.reject)
        hdr_layout.addWidget(btn_close)
        main_layout.addWidget(header)

        # ── 2. Stacked Content (Step 1: Configure / Step 2: Review) ──
        self.stack = QStackedWidget()

        self.step_configure = self._build_configure_step()
        self.step_review = self._build_review_step()

        self.stack.addWidget(self.step_configure)
        self.stack.addWidget(self.step_review)
        main_layout.addWidget(self.stack)

    def _build_configure_step(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background-color: #ffffff; border: none;")

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 14, 20, 14)
        body_layout.setSpacing(14)

        # Error Banner
        self.lbl_config_error = QLabel("")
        self.lbl_config_error.setWordWrap(True)
        self.lbl_config_error.setStyleSheet("""
            background-color: #fef2f2;
            color: #b91c1c;
            border: 1px solid #fecaca;
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 11px;
            font-weight: 600;
        """)
        self.lbl_config_error.setVisible(False)
        body_layout.addWidget(self.lbl_config_error)

        # ── Section 1: Returnable Items ──
        lbl_sec1 = QLabel("1. SELECT ITEMS TO RETURN")
        lbl_sec1.setStyleSheet("color: #475569; font-size: 11px; font-weight: 800; letter-spacing: 0.5px;")
        body_layout.addWidget(lbl_sec1)

        self.items_container = QVBoxLayout()
        self.items_container.setSpacing(8)
        body_layout.addLayout(self.items_container)

        # ── Section 2: Reason & Notes ──
        lbl_sec2 = QLabel("2. RETURN REASON")
        lbl_sec2.setStyleSheet("color: #475569; font-size: 11px; font-weight: 800; letter-spacing: 0.5px;")
        body_layout.addWidget(lbl_sec2)

        reason_card = QFrame()
        reason_card.setStyleSheet("background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px;")
        reason_layout = QVBoxLayout(reason_card)
        reason_layout.setSpacing(8)

        r_row = QHBoxLayout()
        lbl_rc = QLabel("Reason Code:")
        lbl_rc.setStyleSheet("color: #475569; font-size: 11px; font-weight: 700;")
        r_row.addWidget(lbl_rc)

        self.cmb_reason = QComboBox()
        self.cmb_reason.setFixedHeight(32)
        self.cmb_reason.setStyleSheet("""
            QComboBox {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 0 10px;
                font-size: 12px;
                color: #0f172a;
            }
        """)
        self.cmb_reason.addItem("Defective / Damaged", ReturnReason.DEFECTIVE.value)
        self.cmb_reason.addItem("Wrong Item Delivered", ReturnReason.WRONG_ITEM.value)
        self.cmb_reason.addItem("Customer Changed Mind", ReturnReason.CUSTOMER_CHANGE_MIND.value)
        self.cmb_reason.addItem("Expired Product", ReturnReason.EXPIRED.value)
        self.cmb_reason.addItem("Other (Notes Required)", ReturnReason.OTHER.value)
        self.cmb_reason.currentIndexChanged.connect(self._on_reason_changed)
        r_row.addWidget(self.cmb_reason, 1)
        reason_layout.addLayout(r_row)

        self.txt_notes = QLineEdit()
        self.txt_notes.setPlaceholderText("Optional notes / remarks")
        self.txt_notes.setFixedHeight(32)
        self.txt_notes.setStyleSheet("""
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 0 10px;
                font-size: 12px;
                color: #0f172a;
            }
            QLineEdit:focus {
                border: 1px solid #2563eb;
            }
        """)
        reason_layout.addWidget(self.txt_notes)
        body_layout.addWidget(reason_card)

        # ── Section 3: Refund Method ──
        lbl_sec3 = QLabel("3. REFUND PAYMENT METHOD")
        lbl_sec3.setStyleSheet("color: #475569; font-size: 11px; font-weight: 800; letter-spacing: 0.5px;")
        body_layout.addWidget(lbl_sec3)

        method_card = QFrame()
        method_card.setStyleSheet("background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px;")
        method_layout = QVBoxLayout(method_card)
        method_layout.setSpacing(8)

        self.rb_cash = QRadioButton("Cash")
        self.rb_cash.setChecked(True)
        self.rb_cash.setStyleSheet("font-size: 12px; font-weight: 600; color: #0f172a;")
        self.rb_cash.toggled.connect(self._on_method_toggled)
        method_layout.addWidget(self.rb_cash)

        orig_pm = self.sale.payment_method.upper()
        self._is_electronic_sale = (
            orig_pm != "CASH"
            and orig_pm in SUPPORTED_ELECTRONIC_METHODS
        )

        self.rb_orig = QRadioButton(f"Original Payment Method — {orig_pm}")
        self.rb_orig.setStyleSheet("font-size: 12px; font-weight: 600; color: #0f172a;")
        self.rb_orig.toggled.connect(self._on_method_toggled)
        self.rb_orig.setVisible(self._is_electronic_sale)
        method_layout.addWidget(self.rb_orig)

        self.ref_row = QWidget()
        ref_layout = QHBoxLayout(self.ref_row)
        ref_layout.setContentsMargins(20, 0, 0, 0)
        lbl_ref = QLabel("Refund Ref #:")
        lbl_ref.setStyleSheet("color: #475569; font-size: 11px; font-weight: 700;")
        ref_layout.addWidget(lbl_ref)

        self.txt_ref = QLineEdit()
        self.txt_ref.setPlaceholderText("External refund transaction reference *")
        self.txt_ref.setFixedHeight(30)
        self.txt_ref.setStyleSheet("""
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 0 10px;
                font-size: 12px;
                color: #0f172a;
            }
        """)
        ref_layout.addWidget(self.txt_ref, 1)
        self.ref_row.setVisible(False)
        method_layout.addWidget(self.ref_row)
        body_layout.addWidget(method_card)

        # ── Section 4: Refund Preview ──
        lbl_sec4 = QLabel("4. REFUND PREVIEW")
        lbl_sec4.setStyleSheet("color: #475569; font-size: 11px; font-weight: 800; letter-spacing: 0.5px;")
        body_layout.addWidget(lbl_sec4)

        prev_card = QFrame()
        prev_card.setStyleSheet("background-color: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 12px;")
        self.prev_layout = QVBoxLayout(prev_card)
        self.prev_layout.setSpacing(4)

        self.lbl_prev_subtotal = QLabel("₱0.00")
        self.lbl_prev_discount = QLabel("-₱0.00")
        self.lbl_prev_taxable = QLabel("₱0.00")
        self.lbl_prev_vat = QLabel("₱0.00")
        self.lbl_prev_total = QLabel("₱0.00")

        def add_prev_row(label: str, val_lbl: QLabel, is_total: bool = False, is_negative: bool = False):
            r = QHBoxLayout()
            lbl = QLabel(label)
            if is_total:
                lbl.setStyleSheet("color: #0f172a; font-size: 13px; font-weight: 800;")
                val_lbl.setStyleSheet("color: #dc2626; font-size: 15px; font-weight: 800; font-family: 'Consolas', monospace;")
            else:
                lbl.setStyleSheet("color: #475569; font-size: 11px; font-weight: 600;")
                color = "#b91c1c" if is_negative else "#0f172a"
                val_lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 700; font-family: 'Consolas', monospace;")
            r.addWidget(lbl)
            r.addStretch()
            r.addWidget(val_lbl)
            self.prev_layout.addLayout(r)

        add_prev_row("Gross Items Returned:", self.lbl_prev_subtotal)
        add_prev_row("Discount Reversal:", self.lbl_prev_discount, is_negative=True)
        add_prev_row("Refundable Taxable Base:", self.lbl_prev_taxable)
        add_prev_row("Output VAT Reversal:", self.lbl_prev_vat)

        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("background-color: #bfdbfe; max-height: 1px; margin: 4px 0;")
        self.prev_layout.addWidget(div)

        add_prev_row("ESTIMATED CUSTOMER REFUND:", self.lbl_prev_total, is_total=True)

        lbl_helper = QLabel("Final refund amount and item availability are revalidated when the return is confirmed.")
        lbl_helper.setWordWrap(True)
        lbl_helper.setStyleSheet("color: #3b82f6; font-size: 10px; font-weight: 500; margin-top: 4px;")
        self.prev_layout.addWidget(lbl_helper)
        body_layout.addWidget(prev_card)

        scroll.setWidget(body)
        layout.addWidget(scroll)

        # Footer
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

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(34)
        btn_cancel.setFixedWidth(80)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #f1f5f9; color: #0f172a; }
        """)
        btn_cancel.clicked.connect(self.reject)
        ft_layout.addWidget(btn_cancel)
        ft_layout.addStretch()

        self.btn_review = QPushButton("Review Return →")
        self.btn_review.setFixedHeight(34)
        self.btn_review.setFixedWidth(130)
        self.btn_review.setCursor(Qt.PointingHandCursor)
        self.btn_review.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover { background-color: #1d4ed8; }
            QPushButton:disabled { background-color: #94a3b8; }
        """)
        self.btn_review.clicked.connect(self._go_to_review)
        ft_layout.addWidget(self.btn_review)

        layout.addWidget(footer)
        return widget

    def _build_review_step(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background-color: #ffffff; border: none;")

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 16, 24, 16)
        body_layout.setSpacing(14)

        # Warning / Immutable Notice
        warn_card = QFrame()
        warn_card.setStyleSheet("background-color: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 10px 14px;")
        warn_layout = QHBoxLayout(warn_card)
        warn_icon = QLabel()
        warn_icon.setPixmap(IconManager.get_pixmap("alert", color="#d97706", size=16))
        warn_layout.addWidget(warn_icon)
        warn_text = QLabel("Please review carefully. Completed returns cannot be voided or deleted.")
        warn_text.setStyleSheet("color: #92400e; font-size: 11px; font-weight: 700;")
        warn_layout.addWidget(warn_text, 1)
        body_layout.addWidget(warn_card)

        # Error Banner (on review)
        self.lbl_review_error = QLabel("")
        self.lbl_review_error.setWordWrap(True)
        self.lbl_review_error.setStyleSheet("""
            background-color: #fef2f2;
            color: #b91c1c;
            border: 1px solid #fecaca;
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 11px;
            font-weight: 600;
        """)
        self.lbl_review_error.setVisible(False)
        body_layout.addWidget(self.lbl_review_error)

        # Review Summary Container
        self.review_details_card = QFrame()
        self.review_details_card.setStyleSheet("background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px;")
        self.review_details_layout = QVBoxLayout(self.review_details_card)
        self.review_details_layout.setSpacing(8)
        body_layout.addWidget(self.review_details_card)

        scroll.setWidget(body)
        layout.addWidget(scroll)

        # Footer
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

        btn_back = QPushButton("← Back to Edit")
        btn_back.setFixedHeight(34)
        btn_back.setFixedWidth(110)
        btn_back.setCursor(Qt.PointingHandCursor)
        btn_back.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #f1f5f9; color: #0f172a; }
        """)
        btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        ft_layout.addWidget(btn_back)
        ft_layout.addStretch()

        self.btn_confirm = QPushButton("Confirm & Refund")
        self.btn_confirm.setFixedHeight(34)
        self.btn_confirm.setFixedWidth(140)
        self.btn_confirm.setCursor(Qt.PointingHandCursor)
        self.btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover { background-color: #047857; }
            QPushButton:disabled { background-color: #94a3b8; }
        """)
        self.btn_confirm.clicked.connect(self._on_confirm_refund)
        ft_layout.addWidget(self.btn_confirm)

        layout.addWidget(footer)
        return widget

    # ─── Data Loading & UI Population ───

    def _load_returnable_items(self):
        """Fetch authoritative returnable items from ReturnsService."""
        try:
            self._returnable_lines = self._returns_service.get_returnable_items(
                self.sale.id, actor=self._current_user
            )
            self._render_item_rows()
        except Exception as e:
            self._show_config_error(f"Error loading returnable items: {str(e)}")

    def _render_item_rows(self):
        """Render card rows for each returnable line item."""
        # Clear existing
        while self.items_container.count():
            item = self.items_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._line_controls.clear()

        for line in self._returnable_lines:
            card = QFrame()
            card.setStyleSheet("""
                QFrame {
                    background-color: #f8fafc;
                    border: 1px solid #e2e8f0;
                    border-radius: 8px;
                    padding: 8px 12px;
                }
            """)
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(0, 0, 0, 0)
            c_layout.setSpacing(6)

            # Top Row: Checkbox, Name, Price, Badge
            top_row = QHBoxLayout()
            chk = QCheckBox()
            chk.setCursor(Qt.PointingHandCursor)

            name_lbl = QLabel(line.product_name)
            name_lbl.setStyleSheet("color: #0f172a; font-size: 13px; font-weight: 700;")
            price_lbl = QLabel(f"₱{line.unit_price:,.2f}")
            price_lbl.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 600; font-family: 'Consolas', monospace;")

            top_row.addWidget(chk)
            top_row.addWidget(name_lbl)
            top_row.addWidget(price_lbl)
            top_row.addStretch()

            is_fully_returned = line.remaining_returnable_quantity == 0

            if is_fully_returned:
                chk.setEnabled(False)
                ret_badge = QLabel("FULLY RETURNED")
                ret_badge.setStyleSheet("""
                    color: #b91c1c;
                    background-color: #fef2f2;
                    border: 1px solid #fecaca;
                    border-radius: 4px;
                    padding: 2px 6px;
                    font-size: 9px;
                    font-weight: 800;
                """)
                top_row.addWidget(ret_badge)
            else:
                avail_lbl = QLabel(f"Available: {line.remaining_returnable_quantity}")
                avail_lbl.setStyleSheet("color: #0369a1; background-color: #f0f9ff; border: 1px solid #bae6fd; border-radius: 4px; padding: 2px 6px; font-size: 9px; font-weight: 700;")
                top_row.addWidget(avail_lbl)

            c_layout.addLayout(top_row)

            # Sub-info
            sub_lbl = QLabel(f"Purchased: {line.original_quantity}  ·  Previously Returned: {line.previously_returned_quantity}")
            sub_lbl.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 500;")
            c_layout.addWidget(sub_lbl)

            # Controls row (Qty stepper & Condition)
            ctrl_row = QHBoxLayout()
            ctrl_row.setSpacing(10)

            lbl_qty = QLabel("Return Qty:")
            lbl_qty.setStyleSheet("font-size: 11px; font-weight: 700; color: #475569;")
            ctrl_row.addWidget(lbl_qty)

            spin_qty = QSpinBox()
            spin_qty.setRange(1, max(1, line.remaining_returnable_quantity))
            spin_qty.setValue(1)
            spin_qty.setFixedWidth(65)
            spin_qty.setFixedHeight(28)
            spin_qty.setEnabled(False)
            spin_qty.valueChanged.connect(self._schedule_preview)
            ctrl_row.addWidget(spin_qty)

            lbl_cond = QLabel("Condition:")
            lbl_cond.setStyleSheet("font-size: 11px; font-weight: 700; color: #475569;")
            ctrl_row.addWidget(lbl_cond)

            cmb_disp = QComboBox()
            cmb_disp.setFixedHeight(28)
            cmb_disp.addItem("Return to Stock", ReturnDisposition.RESTOCK.value)
            cmb_disp.addItem("Damaged / Non-Sellable", ReturnDisposition.DAMAGED_WRITE_OFF.value)
            cmb_disp.setEnabled(False)
            cmb_disp.currentIndexChanged.connect(self._schedule_preview)
            ctrl_row.addWidget(cmb_disp, 1)

            c_layout.addLayout(ctrl_row)

            self._line_controls[line.sale_line_item_id] = {
                "line": line,
                "chk": chk,
                "spin_qty": spin_qty,
                "cmb_disp": cmb_disp,
            }

            # Checkbox toggle event
            chk.toggled.connect(lambda checked, s=spin_qty, c=cmb_disp: self._on_item_toggled(checked, s, c))
            self.items_container.addWidget(card)

    def _on_item_toggled(self, checked: bool, spin: QSpinBox, cmb: QComboBox):
        spin.setEnabled(checked)
        cmb.setEnabled(checked)
        self._schedule_preview()

    def _on_reason_changed(self):
        reason_code = self.cmb_reason.currentData()
        if reason_code == ReturnReason.OTHER.value:
            self.txt_notes.setPlaceholderText("Explanation required for 'Other' reason *")
        else:
            self.txt_notes.setPlaceholderText("Optional notes / remarks")
        self._schedule_preview()

    def _on_method_toggled(self):
        if self.rb_orig.isChecked():
            self.ref_row.setVisible(True)
        else:
            self.ref_row.setVisible(False)
        self._schedule_preview()

    def _schedule_preview(self):
        """Debounce preview query."""
        self._preview_timer.start()

    def _fetch_preview(self):
        """Invoke ReturnsService.preview_return() to display authoritative numbers."""
        selected_items = self._get_selected_items()
        if not selected_items:
            self.lbl_prev_subtotal.setText("₱0.00")
            self.lbl_prev_discount.setText("-₱0.00")
            self.lbl_prev_taxable.setText("₱0.00")
            self.lbl_prev_vat.setText("₱0.00")
            self.lbl_prev_total.setText("₱0.00")
            self._latest_preview = None
            return

        try:
            req = ProcessReturnRequestDTO(
                sale_id=self.sale.id,
                items=selected_items,
                reason_code=self.cmb_reason.currentData(),
                reason_notes=self.txt_notes.text().strip() or None,
                refund_payment_method=RefundMethod.ORIGINAL_METHOD.value if self.rb_orig.isChecked() else RefundMethod.CASH.value,
                refund_reference=self.txt_ref.text().strip() or None,
            )
            prev = self._returns_service.preview_return(req, actor=self._current_user)
            self._latest_preview = prev

            self.lbl_prev_subtotal.setText(f"₱{prev.subtotal_returned:,.2f}")
            self.lbl_prev_discount.setText(f"-₱{prev.discount_reversal:,.2f}")
            self.lbl_prev_taxable.setText(f"₱{prev.taxable_reversal:,.2f}")
            self.lbl_prev_vat.setText(f"₱{prev.tax_reversal:,.2f}")
            self.lbl_prev_total.setText(f"₱{prev.total_refund_amount:,.2f}")
            self.lbl_config_error.setVisible(False)
        except Exception as e:
            self._show_config_error(f"Preview warning: {str(e)}")

    def _get_selected_items(self) -> List[ReturnItemRequestDTO]:
        items: List[ReturnItemRequestDTO] = []
        for line_id, ctrl in self._line_controls.items():
            if ctrl["chk"].isChecked():
                items.append(
                    ReturnItemRequestDTO(
                        sale_line_item_id=line_id,
                        quantity=ctrl["spin_qty"].value(),
                        disposition=ctrl["cmb_disp"].currentData(),
                    )
                )
        return items

    # ─── Navigation & Review Step ───

    def _go_to_review(self):
        """Validate input before presenting final review step."""
        selected = self._get_selected_items()
        if not selected:
            self._show_config_error("Please select at least one item to return.")
            return

        reason_code = self.cmb_reason.currentData()
        notes = self.txt_notes.text().strip()
        if reason_code == ReturnReason.OTHER.value and not notes:
            self._show_config_error("Reason notes are required when reason is 'Other'.")
            self.txt_notes.setFocus()
            return

        if self.rb_orig.isChecked() and not self.txt_ref.text().strip():
            self._show_config_error("Refund reference is required for electronic original method refunds.")
            self.txt_ref.setFocus()
            return

        self._populate_review_summary(selected)
        self.stack.setCurrentIndex(1)

    def _populate_review_summary(self, selected_items: List[ReturnItemRequestDTO]):
        """Render selected item breakdown and refund total on review screen."""
        while self.review_details_layout.count():
            item = self.review_details_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Items Table
        tbl = QTableWidget()
        tbl.setColumnCount(4)
        tbl.setHorizontalHeaderLabels(["Item", "Qty", "Condition", "Unit Price"])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        tbl.verticalHeader().setVisible(False)
        tbl.setSelectionMode(QTableWidget.NoSelection)
        tbl.setFocusPolicy(Qt.NoFocus)
        tbl.setStyleSheet("""
            QTableWidget { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; }
            QHeaderView::section { background: #f8fafc; color: #475569; font-size: 10px; font-weight: 700; padding: 4px; }
        """)

        tbl.setRowCount(len(selected_items))
        for r, it in enumerate(selected_items):
            line_ctrl = self._line_controls[it.sale_line_item_id]
            line = line_ctrl["line"]

            tbl.setItem(r, 0, QTableWidgetItem(line.product_name))
            q_it = QTableWidgetItem(str(it.quantity))
            q_it.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            tbl.setItem(r, 1, q_it)

            disp_str = "Restock" if it.disposition == ReturnDisposition.RESTOCK.value else "Damaged"
            tbl.setItem(r, 2, QTableWidgetItem(disp_str))

            p_it = QTableWidgetItem(f"₱{line.unit_price:,.2f}")
            p_it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tbl.setItem(r, 3, p_it)

        tbl.setFixedHeight(min(180, 32 + len(selected_items) * 30))
        self.review_details_layout.addWidget(tbl)

        # Meta rows
        def add_rev_meta(lbl: str, val: str):
            r = QHBoxLayout()
            l = QLabel(lbl)
            l.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 600;")
            v = QLabel(val)
            v.setStyleSheet("color: #0f172a; font-size: 11px; font-weight: 700;")
            r.addWidget(l)
            r.addStretch()
            r.addWidget(v)
            self.review_details_layout.addLayout(r)

        add_rev_meta("Return Reason:", self.cmb_reason.currentText())
        if self.txt_notes.text().strip():
            add_rev_meta("Notes:", self.txt_notes.text().strip())

        method_str = "Cash" if self.rb_cash.isChecked() else f"Original Method ({self.sale.payment_method.upper()})"
        add_rev_meta("Refund Method:", method_str)
        if self.rb_orig.isChecked():
            add_rev_meta("Refund Ref #:", self.txt_ref.text().strip())

        # Total Refund Highlight
        refund_str = f"₱{self._latest_preview.total_refund_amount:,.2f}" if self._latest_preview else "₱0.00"
        tot_row = QHBoxLayout()
        tot_lbl = QLabel("TOTAL REFUND TO CUSTOMER:")
        tot_lbl.setStyleSheet("color: #0f172a; font-size: 13px; font-weight: 800;")
        tot_val = QLabel(refund_str)
        tot_val.setStyleSheet("color: #dc2626; font-size: 16px; font-weight: 800; font-family: 'Consolas', monospace;")
        tot_row.addWidget(tot_lbl)
        tot_row.addStretch()
        tot_row.addWidget(tot_val)
        self.review_details_layout.addLayout(tot_row)

    # ─── Execution & Manager Approval ───

    def _on_confirm_refund(self):
        """Execute atomic return processing with manager approval when needed."""
        self.btn_confirm.setEnabled(False)
        self.lbl_review_error.setVisible(False)

        # 1. Deterministic Approval Resolution
        approver: Optional[User] = None
        is_self_approver = self._current_user.is_admin() or self._current_user.has_permission("refund_approve")

        if is_self_approver:
            approver = self._current_user
        else:
            # Cashier requires Manager authorization
            override_dlg = ManagerOverrideDialog(
                auth_service=self._auth_service,
                action_title=f"Authorize Return for Sale #{self.sale.transaction_number}",
                parent=self,
            )
            if override_dlg.exec() != QDialog.Accepted or not override_dlg.authenticated_approver:
                self.btn_confirm.setEnabled(True)
                return
            approver = override_dlg.authenticated_approver

        # 2. Build Request Command
        req = ProcessReturnRequestDTO(
            sale_id=self.sale.id,
            items=self._get_selected_items(),
            reason_code=self.cmb_reason.currentData(),
            reason_notes=self.txt_notes.text().strip() or None,
            refund_payment_method=RefundMethod.ORIGINAL_METHOD.value if self.rb_orig.isChecked() else RefundMethod.CASH.value,
            refund_reference=self.txt_ref.text().strip() or None,
        )

        # 3. Process Return via Service
        try:
            ret_dto = self._returns_service.process_return(
                request=req,
                actor=self._current_user,
                approver=approver,
                idempotency_key=self.idempotency_key,
            )
            self.final_return_dto = ret_dto
            self.accept()

        except ValidationError as ve:
            msg = str(ve)
            if "exceeds remaining" in msg.lower() or "fully returned" in msg.lower():
                self._show_review_error("Return availability changed. The transaction has been refreshed.")
                self._load_returnable_items()
                self.stack.setCurrentIndex(0)
            else:
                self._show_review_error(f"Validation Error: {msg}")
            self.btn_confirm.setEnabled(True)

        except AuthorizationError as ae:
            self._show_review_error(f"Authorization Error: {str(ae)}")
            self.btn_confirm.setEnabled(True)

        except Exception as e:
            self._show_review_error(f"System Error: {str(e)}")
            self.btn_confirm.setEnabled(True)

    def _show_config_error(self, message: str):
        self.lbl_config_error.setText(message)
        self.lbl_config_error.setVisible(True)

    def _show_review_error(self, message: str):
        self.lbl_review_error.setText(message)
        self.lbl_review_error.setVisible(True)

    def _on_header_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _on_header_mouse_move(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
