"""
RetailFlow POS - Void Expense Voucher Dialog
Frameless modal for permanently voiding an active expense disbursement voucher.
Requires a mandatory cancellation reason (>= 5 chars) and displays permanent financial impact warnings.
"""

from typing import Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from application.dto.expense_dto import ExpenseResponseDTO, VoidExpenseDTO
from application.services.expense_service import ExpenseService
from domain.exceptions import RetailFlowError
from infrastructure.database.models.auth import User
from presentation.styles.icons import IconManager


class VoidExpenseDialog(QDialog):
    """
    Dedicated confirmation dialog for soft-cancelling/voiding an active expense voucher.
    Requires an explicit cancellation explanation (min 5 characters).
    """

    def __init__(
        self,
        expense_service: ExpenseService,
        current_actor: User,
        expense_data: ExpenseResponseDTO,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._expense_service = expense_service
        self._actor = current_actor
        self._expense_data = expense_data
        self._drag_pos = QPoint()
        self.result_dto: Optional[ExpenseResponseDTO] = None

        self.setWindowTitle(f"Void Expense Voucher - {expense_data.voucher_number}")
        self.setFixedSize(500, 520)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self._init_ui()

    def _init_ui(self):
        main_container = QFrame(self)
        main_container.setObjectName("dialogContainerCard")
        main_container.setStyleSheet("""
            QFrame#dialogContainerCard {
                background-color: #ffffff;
                border: 1px solid #fca5a5;
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
                background-color: #fef2f2;
                border-bottom: 1px solid #fee2e2;
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
        hdr_icon.setPixmap(IconManager.get_pixmap("alert", color="#dc2626", size=22))
        header_layout.addWidget(hdr_icon)

        hdr_text_layout = QVBoxLayout()
        hdr_text_layout.setSpacing(1)

        hdr_title = QLabel("Void Expense Voucher")
        hdr_title.setStyleSheet("color: #991b1b; font-size: 15px; font-weight: 800;")
        hdr_text_layout.addWidget(hdr_title)

        hdr_sub = QLabel("Permanently cancel and exclude this voucher from financial totals.")
        hdr_sub.setStyleSheet("color: #b91c1c; font-size: 11px; font-weight: 500;")
        hdr_text_layout.addWidget(hdr_sub)

        header_layout.addLayout(hdr_text_layout, 1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #991b1b;
                font-size: 14px;
                font-weight: bold;
                border-radius: 14px;
            }
            QPushButton:hover {
                background-color: #fee2e2;
                color: #7f1d1d;
            }
        """)
        close_btn.clicked.connect(self.reject)
        header_layout.addWidget(close_btn)

        container_layout.addWidget(header_card)

        # ── 2. Content Body ──
        body_widget = QWidget()
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(12)

        # Voucher Summary Card
        summary_card = QFrame()
        summary_card.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 10px 14px;
            }
        """)
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(4)

        v_row = QHBoxLayout()
        v_no = QLabel(self._expense_data.voucher_number)
        v_no.setStyleSheet("font-family: monospace; font-size: 13px; font-weight: 800; color: #1e40af;")
        v_row.addWidget(v_no)

        v_row.addStretch()

        v_amt = QLabel(f"₱{self._expense_data.amount:,.2f}")
        v_amt.setStyleSheet("font-size: 14px; font-weight: 800; color: #dc2626;")
        v_row.addWidget(v_amt)
        summary_layout.addLayout(v_row)

        v_title = QLabel(f"{self._expense_data.title} · Payee: {self._expense_data.payee}")
        v_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #334155;")
        v_title.setWordWrap(True)
        summary_layout.addWidget(v_title)

        v_meta = QLabel(f"Category: {self._expense_data.category_display} · Date: {self._expense_data.expense_date}")
        v_meta.setStyleSheet("font-size: 10px; font-weight: 500; color: #64748b;")
        summary_layout.addWidget(v_meta)

        body_layout.addWidget(summary_card)

        # Warning Alert Box
        warn_box = QFrame()
        warn_box.setStyleSheet("""
            QFrame {
                background-color: #fffbeb;
                border: 1px solid #fde68a;
                border-radius: 8px;
                padding: 8px 12px;
            }
        """)
        w_layout = QHBoxLayout(warn_box)
        w_layout.setContentsMargins(0, 0, 0, 0)
        w_layout.setSpacing(8)

        w_icon = QLabel("⚠️")
        w_icon.setStyleSheet("font-size: 14px;")
        w_layout.addWidget(w_icon)

        w_lbl = QLabel(
            "Voiding is permanent and cannot be undone. This expense will be immediately deducted "
            "from all P&L reports and KPI metrics. The cancellation reason will be recorded in the audit trail."
        )
        w_lbl.setStyleSheet("color: #92400e; font-size: 11px; font-weight: 600; line-height: 1.3;")
        w_lbl.setWordWrap(True)
        w_layout.addWidget(w_lbl, 1)

        body_layout.addWidget(warn_box)

        # Validation Error Banner
        self.error_banner = QFrame()
        self.error_banner.setStyleSheet("""
            QFrame {
                background-color: #fee2e2;
                border: 1px solid #fca5a5;
                border-radius: 8px;
                padding: 6px 10px;
            }
        """)
        err_layout = QHBoxLayout(self.error_banner)
        err_layout.setContentsMargins(0, 0, 0, 0)
        err_layout.setSpacing(6)

        self.error_lbl = QLabel("")
        self.error_lbl.setStyleSheet("color: #991b1b; font-size: 11px; font-weight: 600;")
        self.error_lbl.setWordWrap(True)
        err_layout.addWidget(self.error_lbl, 1)

        self.error_banner.setVisible(False)
        body_layout.addWidget(self.error_banner)

        # Reason Input
        reason_hdr_layout = QHBoxLayout()
        lbl_reason = QLabel("Cancellation Reason *")
        lbl_reason.setStyleSheet("font-size: 11px; font-weight: 700; color: #334155;")
        reason_hdr_layout.addWidget(lbl_reason)

        reason_hdr_layout.addStretch()

        self.lbl_char_count = QLabel("0 / 5 chars minimum")
        self.lbl_char_count.setStyleSheet("font-size: 10px; font-weight: 600; color: #94a3b8;")
        reason_hdr_layout.addWidget(self.lbl_char_count)

        body_layout.addLayout(reason_hdr_layout)

        self.txt_reason = QTextEdit()
        self.txt_reason.setPlaceholderText("Enter specific explanation (e.g. Duplicate bill entered by error, check cancelled)...")
        self.txt_reason.setFixedHeight(75)
        self.txt_reason.textChanged.connect(self._on_reason_changed)
        body_layout.addWidget(self.txt_reason)

        body_layout.addStretch()
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

        self.btn_cancel = QPushButton("Cancel")
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

        self.btn_confirm = QPushButton("🚫 Confirm Void Voucher")
        self.btn_confirm.setCursor(Qt.PointingHandCursor)
        self.btn_confirm.setFixedHeight(36)
        self.btn_confirm.setEnabled(False)  # Disabled until reason >= 5 chars
        self.btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #dc2626;
                border: none;
                border-radius: 6px;
                color: #ffffff;
                font-size: 12px;
                font-weight: 700;
                padding: 0 18px;
            }
            QPushButton:hover {
                background-color: #b91c1c;
            }
            QPushButton:disabled {
                background-color: #fca5a5;
                color: #ffffff;
            }
        """)
        self.btn_confirm.clicked.connect(self._on_confirm_clicked)
        footer_layout.addWidget(self.btn_confirm)

        container_layout.addWidget(footer_card)

    def _on_reason_changed(self):
        """Update character counter and enable Confirm button when >= 5 chars."""
        reason = self.txt_reason.toPlainText().strip()
        length = len(reason)

        if length < 5:
            self.lbl_char_count.setText(f"{length} / 5 chars minimum")
            self.lbl_char_count.setStyleSheet("font-size: 10px; font-weight: 600; color: #dc2626;")
            self.btn_confirm.setEnabled(False)
        else:
            self.lbl_char_count.setText(f"{length} characters")
            self.lbl_char_count.setStyleSheet("font-size: 10px; font-weight: 600; color: #16a34a;")
            self.btn_confirm.setEnabled(True)

    def _on_confirm_clicked(self):
        """Execute void transaction via ExpenseService."""
        self._clear_error()
        reason = self.txt_reason.toPlainText().strip()

        if len(reason) < 5:
            self._show_error("A valid void explanation of at least 5 characters is required.")
            return

        self.btn_confirm.setEnabled(False)
        dto = VoidExpenseDTO(
            expense_id=self._expense_data.id,
            void_reason=reason,
        )

        try:
            self.result_dto = self._expense_service.void_expense(dto, actor=self._actor)
            self.accept()
        except RetailFlowError as e:
            self._show_error(str(e))
            self.btn_confirm.setEnabled(True)
        except Exception as e:
            self._show_error(f"Failed to void voucher: {e}")
            self.btn_confirm.setEnabled(True)

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
