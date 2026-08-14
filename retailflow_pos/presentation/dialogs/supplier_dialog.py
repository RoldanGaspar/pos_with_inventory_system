"""
RetailFlow POS - Supplier Profile Dialog
Frameless modal for registering new wholesale distributors and editing supplier details.
"""

from typing import Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from application.dto.supplier_dto import (
    CreateSupplierDTO,
    SupplierResponseDTO,
    UpdateSupplierDTO,
)
from application.services.supplier_service import SupplierService
from domain.exceptions import RetailFlowError
from infrastructure.database.models.auth import User
from presentation.styles.icons import IconManager


class SupplierDialog(QDialog):
    """Modal dialog for creating or updating wholesale suppliers."""

    def __init__(
        self,
        supplier_service: SupplierService,
        current_actor: User,
        supplier_data: Optional[SupplierResponseDTO] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._supplier_service = supplier_service
        self._actor = current_actor
        self._supplier_data = supplier_data
        self._is_edit = supplier_data is not None
        self._drag_pos = QPoint()

        self.setWindowTitle("Edit Supplier" if self._is_edit else "Register Wholesale Supplier")
        self.setFixedSize(540, 580)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self._init_ui()
        if self._is_edit:
            self._prefill_data()
        else:
            self._generate_code()

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

        title_text = f"Edit Supplier: {self._supplier_data.name}" if self._is_edit else "Register Wholesale Supplier"
        hdr_title = QLabel(title_text)
        hdr_title.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: 800;")
        hdr_text_layout.addWidget(hdr_title)

        hdr_sub = QLabel("Record vendor distributor contact, payment terms, and TIN.")
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
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(12)

        # Error Banner
        self.error_banner = QLabel("")
        self.error_banner.setWordWrap(True)
        self.error_banner.setStyleSheet("""
            background-color: #fef2f2;
            color: #dc2626;
            border: 1px solid #fca5a5;
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 11px;
            font-weight: 600;
        """)
        self.error_banner.hide()
        body_layout.addWidget(self.error_banner)

        # Row 1: Company Name & Supplier Code
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        f_name_col = QVBoxLayout()
        f_name_col.setSpacing(4)
        lbl_name = QLabel("COMPANY NAME *")
        lbl_name.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_name_col.addWidget(lbl_name)
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("e.g. Coca-Cola Beverages PH")
        self.txt_name.setFixedHeight(36)
        self.txt_name.setStyleSheet(self._input_style())
        f_name_col.addWidget(self.txt_name)
        row1.addLayout(f_name_col, 2)

        f_code_col = QVBoxLayout()
        f_code_col.setSpacing(4)
        lbl_code = QLabel("SUPPLIER CODE *")
        lbl_code.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_code_col.addWidget(lbl_code)

        code_row = QHBoxLayout()
        code_row.setSpacing(4)
        self.txt_code = QLineEdit()
        self.txt_code.setPlaceholderText("SUP-001")
        self.txt_code.setFixedHeight(36)
        self.txt_code.setStyleSheet(self._input_style())
        code_row.addWidget(self.txt_code)

        if not self._is_edit:
            btn_gen = QPushButton("⚡")
            btn_gen.setToolTip("Auto Generate Code")
            btn_gen.setFixedSize(36, 36)
            btn_gen.setCursor(Qt.PointingHandCursor)
            btn_gen.setStyleSheet("""
                QPushButton {
                    background-color: #f1f5f9;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    font-size: 14px;
                }
                QPushButton:hover { background-color: #e2e8f0; }
            """)
            btn_gen.clicked.connect(self._generate_code)
            code_row.addWidget(btn_gen)

        f_code_col.addLayout(code_row)
        row1.addLayout(f_code_col, 1)
        body_layout.addLayout(row1)

        # Row 2: Contact Person & Phone Number
        row2 = QHBoxLayout()
        row2.setSpacing(12)

        f_cont_col = QVBoxLayout()
        f_cont_col.setSpacing(4)
        lbl_cont = QLabel("CONTACT PERSON")
        lbl_cont.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_cont_col.addWidget(lbl_cont)
        self.txt_contact = QLineEdit()
        self.txt_contact.setPlaceholderText("e.g. Eduardo Rodriguez")
        self.txt_contact.setFixedHeight(36)
        self.txt_contact.setStyleSheet(self._input_style())
        f_cont_col.addWidget(self.txt_contact)
        row2.addLayout(f_cont_col, 1)

        f_phone_col = QVBoxLayout()
        f_phone_col.setSpacing(4)
        lbl_phone = QLabel("OFFICE / MOBILE PHONE *")
        lbl_phone.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_phone_col.addWidget(lbl_phone)
        self.txt_phone = QLineEdit()
        self.txt_phone.setPlaceholderText("e.g. +63 2 8888 1234")
        self.txt_phone.setFixedHeight(36)
        self.txt_phone.setStyleSheet(self._input_style())
        f_phone_col.addWidget(self.txt_phone)
        row2.addLayout(f_phone_col, 1)
        body_layout.addLayout(row2)

        # Row 3: Email & Address
        row3 = QHBoxLayout()
        row3.setSpacing(12)

        f_email_col = QVBoxLayout()
        f_email_col.setSpacing(4)
        lbl_email = QLabel("SALES EMAIL ADDRESS")
        lbl_email.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_email_col.addWidget(lbl_email)
        self.txt_email = QLineEdit()
        self.txt_email.setPlaceholderText("e.g. orders@coca-cola.com.ph")
        self.txt_email.setFixedHeight(36)
        self.txt_email.setStyleSheet(self._input_style())
        f_email_col.addWidget(self.txt_email)
        row3.addLayout(f_email_col, 1)

        f_addr_col = QVBoxLayout()
        f_addr_col.setSpacing(4)
        lbl_addr = QLabel("OFFICE ADDRESS / CITY")
        lbl_addr.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_addr_col.addWidget(lbl_addr)
        self.txt_address = QLineEdit()
        self.txt_address.setPlaceholderText("e.g. Taguig City, Metro Manila")
        self.txt_address.setFixedHeight(36)
        self.txt_address.setStyleSheet(self._input_style())
        f_addr_col.addWidget(self.txt_address)
        row3.addLayout(f_addr_col, 1)
        body_layout.addLayout(row3)

        # Row 4: Payment Terms & Tax ID
        row4 = QHBoxLayout()
        row4.setSpacing(12)

        f_terms_col = QVBoxLayout()
        f_terms_col.setSpacing(4)
        lbl_terms = QLabel("PAYMENT TERMS")
        lbl_terms.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_terms_col.addWidget(lbl_terms)
        self.cmb_terms = QComboBox()
        self.cmb_terms.addItem("Net 30 Days (Credit)", "NET_30")
        self.cmb_terms.addItem("Net 15 Days (Credit)", "NET_15")
        self.cmb_terms.addItem("Net 60 Days (Credit)", "NET_60")
        self.cmb_terms.addItem("Cash on Delivery (COD)", "COD")
        self.cmb_terms.setFixedHeight(36)
        self.cmb_terms.setStyleSheet("""
            QComboBox {
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background-color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                color: #0f172a;
            }
            QComboBox:focus { border-color: #2563eb; }
        """)
        f_terms_col.addWidget(self.cmb_terms)
        row4.addLayout(f_terms_col, 1)

        f_tax_col = QVBoxLayout()
        f_tax_col.setSpacing(4)
        lbl_tax = QLabel("TAX ID / TIN NUMBER")
        lbl_tax.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_tax_col.addWidget(lbl_tax)
        self.txt_tax_id = QLineEdit()
        self.txt_tax_id.setPlaceholderText("e.g. 000-123-456-000")
        self.txt_tax_id.setFixedHeight(36)
        self.txt_tax_id.setStyleSheet(self._input_style())
        f_tax_col.addWidget(self.txt_tax_id)
        row4.addLayout(f_tax_col, 1)

        f_stat_col = QVBoxLayout()
        f_stat_col.setSpacing(4)
        lbl_stat = QLabel("STATUS")
        lbl_stat.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_stat_col.addWidget(lbl_stat)
        self.cmb_status = QComboBox()
        self.cmb_status.addItem("Active", True)
        self.cmb_status.addItem("Inactive", False)
        self.cmb_status.setFixedHeight(36)
        self.cmb_status.setStyleSheet("""
            QComboBox {
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background-color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                color: #0f172a;
            }
            QComboBox:focus { border-color: #2563eb; }
        """)
        f_stat_col.addWidget(self.cmb_status)
        row4.addLayout(f_stat_col, 1)

        body_layout.addLayout(row4)

        # Notes / Agreements
        f_notes_col = QVBoxLayout()
        f_notes_col.setSpacing(4)
        lbl_notes = QLabel("NOTES & SUPPLY AGREEMENTS")
        lbl_notes.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_notes_col.addWidget(lbl_notes)
        self.txt_notes = QLineEdit()
        self.txt_notes.setPlaceholderText("e.g. Weekly delivery schedule, minimum order quantity, wholesale discount...")
        self.txt_notes.setFixedHeight(36)
        self.txt_notes.setStyleSheet(self._input_style())
        f_notes_col.addWidget(self.txt_notes)
        body_layout.addLayout(f_notes_col)

        body_layout.addStretch()
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

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(34)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setStyleSheet("""
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
        btn_cancel.clicked.connect(self.reject)
        footer_layout.addWidget(btn_cancel)

        btn_save = QPushButton("Save Supplier Record")
        btn_save.setIcon(IconManager.get_pixmap("check", color="#ffffff", size=14))
        btn_save.setFixedHeight(34)
        btn_save.setDefault(True)
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 800;
                padding: 0 16px;
            }
            QPushButton:hover { background-color: #1d4ed8; }
        """)
        btn_save.clicked.connect(self._on_save)
        footer_layout.addWidget(btn_save)

        container_layout.addWidget(footer_card)

    def _generate_code(self):
        code = self._supplier_service.generate_next_code()
        self.txt_code.setText(code)

    def _prefill_data(self):
        if not self._supplier_data:
            return
        self.txt_code.setText(self._supplier_data.code)
        self.txt_name.setText(self._supplier_data.name)
        self.txt_contact.setText(self._supplier_data.contact_person or "")
        self.txt_phone.setText(self._supplier_data.phone)
        self.txt_email.setText(self._supplier_data.email or "")
        self.txt_address.setText(self._supplier_data.address or "")
        self.txt_tax_id.setText(self._supplier_data.tax_id or "")
        self.txt_notes.setText(self._supplier_data.notes or "")

        idx = self.cmb_terms.findData(self._supplier_data.payment_terms)
        if idx >= 0:
            self.cmb_terms.setCurrentIndex(idx)

        idx_s = self.cmb_status.findData(self._supplier_data.is_active)
        if idx_s >= 0:
            self.cmb_status.setCurrentIndex(idx_s)

    def _on_header_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _on_header_mouse_move(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def _on_save(self):
        code = self.txt_code.text().strip().upper()
        name = self.txt_name.text().strip()
        phone = self.txt_phone.text().strip()
        contact_person = self.txt_contact.text().strip() or None
        email = self.txt_email.text().strip() or None
        address = self.txt_address.text().strip() or None
        payment_terms = self.cmb_terms.currentData()
        tax_id = self.txt_tax_id.text().strip() or None
        notes = self.txt_notes.text().strip() or None
        is_active = self.cmb_status.currentData()

        if not name:
            self._show_error("Company name is required.")
            return

        if not phone:
            self._show_error("Phone number is required.")
            return

        try:
            if self._is_edit:
                dto = UpdateSupplierDTO(
                    code=code,
                    name=name,
                    contact_person=contact_person,
                    phone=phone,
                    email=email,
                    address=address,
                    payment_terms=payment_terms,
                    tax_id=tax_id,
                    notes=notes,
                    is_active=is_active,
                )
                self._supplier_service.update_supplier(self._supplier_data.id, dto, actor=self._actor)
            else:
                dto_c = CreateSupplierDTO(
                    code=code,
                    name=name,
                    contact_person=contact_person,
                    phone=phone,
                    email=email,
                    address=address,
                    payment_terms=payment_terms,
                    tax_id=tax_id,
                    notes=notes,
                    is_active=is_active,
                )
                self._supplier_service.create_supplier(dto_c, actor=self._actor)

            self.accept()
        except RetailFlowError as e:
            self._show_error(str(e))
        except Exception as e:
            self._show_error(str(e))

    def _show_error(self, msg: str):
        self.error_banner.setText(msg)
        self.error_banner.show()

    def _input_style(self) -> str:
        return """
            QLineEdit {
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background-color: #ffffff;
                font-size: 13px;
                color: #0f172a;
            }
            QLineEdit:focus { border-color: #2563eb; }
        """
