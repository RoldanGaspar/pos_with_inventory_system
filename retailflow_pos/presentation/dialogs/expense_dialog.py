"""
RetailFlow POS - Store Operating Expense Dialog
Frameless modal dialog supporting Create Mode, Edit Metadata Mode, and View/Read-Only Mode.
Enforces financial field immutability, date boundaries, and validation feedback.
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from PySide6.QtCore import QDate, QPoint, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.constants import (
    EXPENSE_CATEGORY_LABELS,
    ExpenseCategory,
    ExpenseStatus,
    PaymentMethod,
)
from application.dto.expense_dto import (
    CreateExpenseDTO,
    ExpenseResponseDTO,
    UpdateExpenseMetadataDTO,
)
from application.services.expense_service import (
    MAX_EXPENSE_AMOUNT,
    MIN_EXPENSE_AMOUNT,
    ExpenseService,
)
from domain.exceptions import RetailFlowError
from infrastructure.database.models.auth import User
from presentation.styles.icons import IconManager


class ExpenseDialog(QDialog):
    """
    Modal dialog for recording a new operating expense or editing non-financial metadata.
    Enforces that financial fields (amount, category, payment method, date) are immutable after creation.
    """

    def __init__(
        self,
        expense_service: ExpenseService,
        current_actor: User,
        expense_data: Optional[ExpenseResponseDTO] = None,
        view_only: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._expense_service = expense_service
        self._actor = current_actor
        self._expense_data = expense_data
        self._view_only = view_only or (expense_data is not None and expense_data.status.lower() == ExpenseStatus.VOID.value)
        self._is_edit = expense_data is not None and not self._view_only
        self._drag_pos = QPoint()
        self.result_dto: Optional[ExpenseResponseDTO] = None

        if self._view_only:
            self.setWindowTitle("View Expense Voucher")
        elif self._is_edit:
            self.setWindowTitle("Edit Expense Metadata")
        else:
            self.setWindowTitle("Record Operating Expense")

        self.setFixedSize(580, 680)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self._init_ui()
        if self._expense_data:
            self._populate_data()

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

        hdr_icon = QLabel()
        hdr_icon.setPixmap(IconManager.get_pixmap("expenses", color="#2563eb", size=22))
        header_layout.addWidget(hdr_icon)

        hdr_text_layout = QVBoxLayout()
        hdr_text_layout.setSpacing(1)

        if self._view_only:
            title_text = f"Expense Voucher: {self._expense_data.voucher_number if self._expense_data else ''}"
            sub_text = "Read-only inspection of store disbursement record."
        elif self._is_edit:
            title_text = f"Edit Voucher: {self._expense_data.voucher_number if self._expense_data else ''}"
            sub_text = "Modify non-financial metadata. Financial fields are locked."
        else:
            title_text = "Record Operating Expense"
            sub_text = "Issue an official petty cash or store operating expense voucher."

        self.lbl_hdr_title = QLabel(title_text)
        self.lbl_hdr_title.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: 800;")
        hdr_text_layout.addWidget(self.lbl_hdr_title)

        hdr_sub = QLabel(sub_text)
        hdr_sub.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 500;")
        hdr_text_layout.addWidget(hdr_sub)

        header_layout.addLayout(hdr_text_layout, 1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #64748b;
                font-size: 14px;
                font-weight: bold;
                border-radius: 14px;
            }
            QPushButton:hover {
                background-color: #fee2e2;
                color: #dc2626;
            }
        """)
        close_btn.clicked.connect(self.reject)
        header_layout.addWidget(close_btn)

        container_layout.addWidget(header_card)

        # ── 2. Content Body ──
        body_widget = QWidget()
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(20, 14, 20, 14)
        body_layout.setSpacing(10)

        # Immutability / Void Informational Banner
        if self._view_only and self._expense_data and self._expense_data.status == ExpenseStatus.VOID:
            void_banner = QFrame()
            void_banner.setStyleSheet("""
                QFrame {
                    background-color: #fef2f2;
                    border: 1px solid #fecaca;
                    border-radius: 8px;
                    padding: 8px 12px;
                }
            """)
            v_layout = QVBoxLayout(void_banner)
            v_layout.setContentsMargins(0, 0, 0, 0)
            v_layout.setSpacing(2)

            v_title = QLabel("🚫 THIS EXPENSE VOUCHER HAS BEEN VOIDED")
            v_title.setStyleSheet("color: #991b1b; font-size: 11px; font-weight: 800;")
            v_layout.addWidget(v_title)

            v_desc = QLabel(f"Void Reason: {self._expense_data.void_reason or 'No reason specified'} ({self._expense_data.voided_at or ''})")
            v_desc.setStyleSheet("color: #b91c1c; font-size: 11px; font-weight: 500;")
            v_desc.setWordWrap(True)
            v_layout.addWidget(v_desc)

            body_layout.addWidget(void_banner)

        elif self._is_edit:
            info_banner = QFrame()
            info_banner.setStyleSheet("""
                QFrame {
                    background-color: #f0fdf4;
                    border: 1px solid #bbf7d0;
                    border-radius: 8px;
                    padding: 8px 12px;
                }
            """)
            i_layout = QHBoxLayout(info_banner)
            i_layout.setContentsMargins(0, 0, 0, 0)
            i_layout.setSpacing(8)

            lock_icon = QLabel("🔒")
            lock_icon.setStyleSheet("font-size: 14px;")
            i_layout.addWidget(lock_icon)

            info_lbl = QLabel(
                "Financial fields (Amount, Category, Date, Method) are locked to maintain ledger integrity. "
                "To correct monetary amounts, void this voucher and issue a replacement."
            )
            info_lbl.setStyleSheet("color: #166534; font-size: 11px; font-weight: 600; line-height: 1.3;")
            info_lbl.setWordWrap(True)
            i_layout.addWidget(info_lbl, 1)

            body_layout.addWidget(info_banner)

        # Validation Error Banner
        self.error_banner = QFrame()
        self.error_banner.setStyleSheet("""
            QFrame {
                background-color: #fee2e2;
                border: 1px solid #fca5a5;
                border-radius: 8px;
                padding: 8px 12px;
            }
        """)
        err_layout = QHBoxLayout(self.error_banner)
        err_layout.setContentsMargins(0, 0, 0, 0)
        err_layout.setSpacing(8)

        err_icon = QLabel()
        err_icon.setPixmap(IconManager.get_pixmap("alert", color="#dc2626", size=16))
        err_layout.addWidget(err_icon)

        self.error_lbl = QLabel("")
        self.error_lbl.setStyleSheet("color: #991b1b; font-size: 11px; font-weight: 600;")
        self.error_lbl.setWordWrap(True)
        err_layout.addWidget(self.error_lbl, 1)

        self.error_banner.setVisible(False)
        body_layout.addWidget(self.error_banner)

        # Form Grid
        form_grid = QGridLayout()
        form_grid.setHorizontalSpacing(14)
        form_grid.setVerticalSpacing(8)

        # Row 0: Category & Expense Date
        lbl_cat = QLabel("Category *")
        lbl_cat.setStyleSheet("font-size: 11px; font-weight: 700; color: #334155;")
        form_grid.addWidget(lbl_cat, 0, 0)

        lbl_date = QLabel("Disbursement Date *")
        lbl_date.setStyleSheet("font-size: 11px; font-weight: 700; color: #334155;")
        form_grid.addWidget(lbl_date, 0, 1)

        self.cmb_category = QComboBox()
        for cat_key, cat_label in EXPENSE_CATEGORY_LABELS.items():
            self.cmb_category.addItem(cat_label, cat_key.value)
        self.cmb_category.setFixedHeight(34)
        self.cmb_category.currentIndexChanged.connect(self._on_category_changed)
        form_grid.addWidget(self.cmb_category, 1, 0)

        self.dt_expense_date = QDateEdit()
        self.dt_expense_date.setCalendarPopup(True)
        self.dt_expense_date.setDate(QDate.currentDate())
        self.dt_expense_date.setMaximumDate(QDate.currentDate())  # Enforce expense_date <= today
        self.dt_expense_date.setFixedHeight(34)
        form_grid.addWidget(self.dt_expense_date, 1, 1)

        # Row 1: Title & Payee
        lbl_title = QLabel("Expense Title *")
        lbl_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #334155;")
        form_grid.addWidget(lbl_title, 2, 0)

        lbl_payee = QLabel("Payee / Vendor / Recipient *")
        lbl_payee.setStyleSheet("font-size: 11px; font-weight: 700; color: #334155;")
        form_grid.addWidget(lbl_payee, 2, 1)

        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("e.g. Meralco Electric Bill")
        self.txt_title.setFixedHeight(34)
        form_grid.addWidget(self.txt_title, 3, 0)

        self.txt_payee = QLineEdit()
        self.txt_payee.setPlaceholderText("e.g. Manila Electric Company")
        self.txt_payee.setFixedHeight(34)
        form_grid.addWidget(self.txt_payee, 3, 1)

        # Row 2: Amount & Payment Method
        lbl_amount = QLabel("Amount (₱) *")
        lbl_amount.setStyleSheet("font-size: 11px; font-weight: 700; color: #334155;")
        form_grid.addWidget(lbl_amount, 4, 0)

        lbl_payment = QLabel("Payment Method *")
        lbl_payment.setStyleSheet("font-size: 11px; font-weight: 700; color: #334155;")
        form_grid.addWidget(lbl_payment, 4, 1)

        self.spn_amount = QDoubleSpinBox()
        self.spn_amount.setRange(float(MIN_EXPENSE_AMOUNT), float(MAX_EXPENSE_AMOUNT))
        self.spn_amount.setDecimals(2)
        self.spn_amount.setPrefix("₱ ")
        self.spn_amount.setGroupSeparatorShown(True)
        self.spn_amount.setValue(0.01)
        self.spn_amount.setFixedHeight(34)
        form_grid.addWidget(self.spn_amount, 5, 0)

        self.cmb_payment_method = QComboBox()
        expense_payment_methods = [
            (PaymentMethod.CASH, "Cash (Petty Cash Drawer)"),
            (PaymentMethod.BANK_TRANSFER, "Bank Wire Transfer"),
            (PaymentMethod.GCASH, "GCash (E-Wallet)"),
            (PaymentMethod.MAYA, "Maya (E-Wallet)"),
            (PaymentMethod.CREDIT_CARD, "Credit Card"),
            (PaymentMethod.DEBIT_CARD, "Debit Card"),
            (PaymentMethod.CHECK, "Commercial Bank Check"),
        ]
        for method_enum, method_label in expense_payment_methods:
            self.cmb_payment_method.addItem(method_label, method_enum.value)
        self.cmb_payment_method.setFixedHeight(34)
        form_grid.addWidget(self.cmb_payment_method, 5, 1)

        # Row 3: Reference / OR # & Internal Notes
        lbl_ref = QLabel("Official Receipt / Reference #")
        lbl_ref.setStyleSheet("font-size: 11px; font-weight: 700; color: #334155;")
        form_grid.addWidget(lbl_ref, 6, 0)

        lbl_notes = QLabel("Internal Remarks / Notes")
        lbl_notes.setStyleSheet("font-size: 11px; font-weight: 700; color: #334155;")
        form_grid.addWidget(lbl_notes, 6, 1)

        self.txt_reference = QLineEdit()
        self.txt_reference.setPlaceholderText("e.g. OR-88192 or Check #")
        self.txt_reference.setFixedHeight(34)
        form_grid.addWidget(self.txt_reference, 7, 0)

        self.txt_notes = QLineEdit()
        self.txt_notes.setPlaceholderText("e.g. Approved by Store Manager")
        self.txt_notes.setFixedHeight(34)
        form_grid.addWidget(self.txt_notes, 7, 1)

        # Row 4: Description (Full Width)
        self.lbl_desc = QLabel("Itemized Description / Breakdown")
        self.lbl_desc.setStyleSheet("font-size: 11px; font-weight: 700; color: #334155;")
        form_grid.addWidget(self.lbl_desc, 8, 0, 1, 2)

        self.txt_description = QTextEdit()
        self.txt_description.setPlaceholderText("Enter detailed breakdown or billing breakdown notes...")
        self.txt_description.setFixedHeight(68)
        form_grid.addWidget(self.txt_description, 9, 0, 1, 2)

        body_layout.addLayout(form_grid)
        container_layout.addWidget(body_widget, 1)

        # ── 3. Footer Actions ──
        footer_card = QFrame()
        footer_card.setObjectName("dialogFooterCard")
        footer_card.setStyleSheet("""
            QFrame#dialogFooterCard {
                background-color: #f8fafc;
                border-top: 1px solid #e2e8f0;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
                padding: 12px 18px;
            }
        """)

        footer_layout = QHBoxLayout(footer_card)
        footer_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_cancel = QPushButton("Close" if self._view_only else "Cancel")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                color: #475569;
                font-size: 12px;
                font-weight: 600;
                padding: 0 16px;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                color: #1e293b;
            }
        """)
        self.btn_cancel.clicked.connect(self.reject)
        footer_layout.addWidget(self.btn_cancel)

        footer_layout.addStretch()

        if not self._view_only:
            btn_save_text = "Save Changes" if self._is_edit else "Save Expense Voucher"
            self.btn_save = QPushButton(btn_save_text)
            self.btn_save.setCursor(Qt.PointingHandCursor)
            self.btn_save.setFixedHeight(36)
            self.btn_save.setStyleSheet("""
                QPushButton {
                    background-color: #2563eb;
                    border: none;
                    border-radius: 6px;
                    color: #ffffff;
                    font-size: 12px;
                    font-weight: 700;
                    padding: 0 20px;
                }
                QPushButton:hover {
                    background-color: #1d4ed8;
                }
                QPushButton:disabled {
                    background-color: #94a3b8;
                }
            """)
            self.btn_save.clicked.connect(self._on_save_clicked)
            footer_layout.addWidget(self.btn_save)

        container_layout.addWidget(footer_card)

        # Apply locking for edit/view modes
        if self._is_edit:
            self._lock_financial_fields()
        elif self._view_only:
            self._lock_all_fields()

    def _lock_financial_fields(self):
        """Lock financial fields to preserve ledger immutability."""
        self.cmb_category.setEnabled(False)
        self.cmb_payment_method.setEnabled(False)
        self.dt_expense_date.setEnabled(False)
        self.spn_amount.setEnabled(False)
        self.txt_title.setEnabled(False)  # Title is locked in metadata update

        locked_style = "background-color: #f1f5f9; color: #64748b;"
        self.cmb_category.setStyleSheet(locked_style)
        self.cmb_payment_method.setStyleSheet(locked_style)
        self.dt_expense_date.setStyleSheet(locked_style)
        self.spn_amount.setStyleSheet(locked_style)
        self.txt_title.setStyleSheet(locked_style)

    def _lock_all_fields(self):
        """Make all form controls read-only in View Mode."""
        self._lock_financial_fields()
        self.txt_payee.setEnabled(False)
        self.txt_reference.setEnabled(False)
        self.txt_notes.setEnabled(False)
        self.txt_description.setReadOnly(True)

        locked_style = "background-color: #f1f5f9; color: #64748b;"
        self.txt_payee.setStyleSheet(locked_style)
        self.txt_reference.setStyleSheet(locked_style)
        self.txt_notes.setStyleSheet(locked_style)
        self.txt_description.setStyleSheet(locked_style)

    def _on_category_changed(self):
        """Update description requirement hint when category is OTHER."""
        current_cat = self.cmb_category.currentData()
        if current_cat == ExpenseCategory.OTHER.value:
            self.lbl_desc.setText("Itemized Description * (Required for 'Other' category)")
            self.lbl_desc.setStyleSheet("font-size: 11px; font-weight: 700; color: #b91c1c;")
            self.txt_description.setPlaceholderText("Detailed description is required for other miscellaneous expenses...")
        else:
            self.lbl_desc.setText("Itemized Description / Breakdown")
            self.lbl_desc.setStyleSheet("font-size: 11px; font-weight: 700; color: #334155;")
            self.txt_description.setPlaceholderText("Enter detailed breakdown or billing breakdown notes...")

    def _populate_data(self):
        """Populate form with existing expense record data."""
        if not self._expense_data:
            return

        # Category
        idx = self.cmb_category.findData(self._expense_data.category)
        if idx >= 0:
            self.cmb_category.setCurrentIndex(idx)

        # Payment Method
        p_idx = self.cmb_payment_method.findData(self._expense_data.payment_method.lower())
        if p_idx >= 0:
            self.cmb_payment_method.setCurrentIndex(p_idx)

        # Title & Payee
        self.txt_title.setText(self._expense_data.title)
        self.txt_payee.setText(self._expense_data.payee)

        # Amount
        self.spn_amount.setValue(float(self._expense_data.amount))

        # Reference & Notes & Description
        if self._expense_data.reference_number:
            self.txt_reference.setText(self._expense_data.reference_number)
        if self._expense_data.notes:
            self.txt_notes.setText(self._expense_data.notes)
        if self._expense_data.description:
            self.txt_description.setText(self._expense_data.description)

        # Date
        # expense_date in response DTO is formatted string (e.g. "Aug 15, 2026")
        try:
            q_date = QDate.fromString(self._expense_data.expense_date, "MMM dd, yyyy")
            if q_date.isValid():
                self.dt_expense_date.setDate(q_date)
        except Exception:
            pass

    def _on_save_clicked(self):
        """Handle expense creation or metadata update submission."""
        self._clear_error()

        # UI Pre-validation
        payee = self.txt_payee.text().strip()
        if not payee:
            self._show_error("Payee / Vendor name is required.")
            self.txt_payee.setFocus()
            return

        if not self._is_edit:
            title = self.txt_title.text().strip()
            if not title:
                self._show_error("Expense title is required.")
                self.txt_title.setFocus()
                return

            category = self.cmb_category.currentData()
            description = self.txt_description.toPlainText().strip()
            if category == ExpenseCategory.OTHER.value and not description:
                self._show_error("Description is required when category is 'Other Miscellaneous'.")
                self.txt_description.setFocus()
                return

            amount_val = Decimal(f"{self.spn_amount.value():.2f}").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if amount_val < MIN_EXPENSE_AMOUNT:
                self._show_error("Expense amount must be greater than ₱0.00.")
                self.spn_amount.setFocus()
                return

            q_date = self.dt_expense_date.date()
            exp_date = date(q_date.year(), q_date.month(), q_date.day())
            if exp_date > date.today():
                self._show_error("Expense date cannot be in the future.")
                return

            payment_method = self.cmb_payment_method.currentData()

            dto = CreateExpenseDTO(
                category=category,
                title=title,
                payee=payee,
                amount=amount_val,
                payment_method=payment_method,
                expense_date=exp_date,
                reference_number=self.txt_reference.text().strip() or None,
                notes=self.txt_notes.text().strip() or None,
                description=description or None,
            )

            self.btn_save.setEnabled(False)
            try:
                self.result_dto = self._expense_service.create_expense(dto, actor=self._actor)
                self.accept()
            except RetailFlowError as e:
                self._show_error(str(e))
                self.btn_save.setEnabled(True)
            except Exception as e:
                self._show_error(f"Failed to record expense: {e}")
                self.btn_save.setEnabled(True)

        else:
            # Edit Metadata Mode
            description = self.txt_description.toPlainText().strip() or None
            reference_number = self.txt_reference.text().strip() or None
            notes = self.txt_notes.text().strip() or None

            update_dto = UpdateExpenseMetadataDTO(
                payee=payee,
                description=description,
                reference_number=reference_number,
                notes=notes,
            )

            self.btn_save.setEnabled(False)
            try:
                self.result_dto = self._expense_service.update_expense_metadata(
                    self._expense_data.id, update_dto, actor=self._actor
                )
                self.accept()
            except RetailFlowError as e:
                self._show_error(str(e))
                self.btn_save.setEnabled(True)
            except Exception as e:
                self._show_error(f"Failed to update metadata: {e}")
                self.btn_save.setEnabled(True)

    def _show_error(self, message: str):
        self.error_lbl.setText(message)
        self.error_banner.setVisible(True)

    def _clear_error(self):
        self.error_lbl.setText("")
        self.error_banner.setVisible(False)

    # ── Header Mouse Drag for Frameless Window ──
    def _on_header_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _on_header_mouse_move(self, event):
        if event.buttons() == Qt.LeftButton and not self._drag_pos.isNull():
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
