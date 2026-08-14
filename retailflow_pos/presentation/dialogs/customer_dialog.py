"""
RetailFlow POS - Customer Profile Dialog
Frameless modal for registering new customer profiles and editing contact details.
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from application.dto.customer_dto import (
    CreateCustomerDTO,
    CustomerResponseDTO,
    UpdateCustomerDTO,
)
from application.services.customer_service import CustomerService
from domain.exceptions import RetailFlowError
from infrastructure.database.models.auth import User
from presentation.styles.icons import IconManager


class CustomerDialog(QDialog):
    """Modal dialog for creating or updating customer profiles."""

    def __init__(
        self,
        customer_service: CustomerService,
        current_actor: User,
        customer_data: Optional[CustomerResponseDTO] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._customer_service = customer_service
        self._actor = current_actor
        self._customer_data = customer_data
        self._is_edit = customer_data is not None
        self._drag_pos = QPoint()

        self.setWindowTitle("Edit Customer Profile" if self._is_edit else "Register New Customer")
        self.setFixedSize(520, 560 if self._is_edit else 600)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self._init_ui()
        if self._is_edit:
            self._prefill_data()

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

        title_text = f"Edit Customer: {self._customer_data.name}" if self._is_edit else "Register New Customer"
        hdr_title = QLabel(title_text)
        hdr_title.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: 800;")
        hdr_text_layout.addWidget(hdr_title)

        hdr_sub = QLabel("Record customer contact info, loyalty reward points, and preferences.")
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

        # Row 1: Full Name & Phone Number
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        f_name_col = QVBoxLayout()
        f_name_col.setSpacing(4)
        lbl_name = QLabel("FULL NAME *")
        lbl_name.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_name_col.addWidget(lbl_name)
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("e.g. Maria Santos")
        self.txt_name.setFixedHeight(36)
        self.txt_name.setStyleSheet(self._input_style())
        f_name_col.addWidget(self.txt_name)
        row1.addLayout(f_name_col, 1)

        f_phone_col = QVBoxLayout()
        f_phone_col.setSpacing(4)
        lbl_phone = QLabel("MOBILE PHONE *")
        lbl_phone.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_phone_col.addWidget(lbl_phone)
        self.txt_phone = QLineEdit()
        self.txt_phone.setPlaceholderText("e.g. +63 917 123 4567")
        self.txt_phone.setFixedHeight(36)
        self.txt_phone.setStyleSheet(self._input_style())
        f_phone_col.addWidget(self.txt_phone)
        row1.addLayout(f_phone_col, 1)
        body_layout.addLayout(row1)

        # Row 2: Email & Address
        row2 = QHBoxLayout()
        row2.setSpacing(12)

        f_email_col = QVBoxLayout()
        f_email_col.setSpacing(4)
        lbl_email = QLabel("EMAIL ADDRESS")
        lbl_email.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_email_col.addWidget(lbl_email)
        self.txt_email = QLineEdit()
        self.txt_email.setPlaceholderText("e.g. maria@gmail.com")
        self.txt_email.setFixedHeight(36)
        self.txt_email.setStyleSheet(self._input_style())
        f_email_col.addWidget(self.txt_email)
        row2.addLayout(f_email_col, 1)

        f_addr_col = QVBoxLayout()
        f_addr_col.setSpacing(4)
        lbl_addr = QLabel("ADDRESS / CITY")
        lbl_addr.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_addr_col.addWidget(lbl_addr)
        self.txt_address = QLineEdit()
        self.txt_address.setPlaceholderText("e.g. Quezon City, Metro Manila")
        self.txt_address.setFixedHeight(36)
        self.txt_address.setStyleSheet(self._input_style())
        f_addr_col.addWidget(self.txt_address)
        row2.addLayout(f_addr_col, 1)
        body_layout.addLayout(row2)

        # Row 3: Initial Points & Status
        row3 = QHBoxLayout()
        row3.setSpacing(12)

        if not self._is_edit:
            f_pts_col = QVBoxLayout()
            f_pts_col.setSpacing(4)
            lbl_pts = QLabel("INITIAL LOYALTY POINTS")
            lbl_pts.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
            f_pts_col.addWidget(lbl_pts)
            self.spn_points = QSpinBox()
            self.spn_points.setRange(0, 99999)
            self.spn_points.setValue(50)
            self.spn_points.setFixedHeight(36)
            self.spn_points.setStyleSheet("""
                QSpinBox {
                    padding: 4px 8px;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    font-size: 13px;
                    font-weight: 700;
                    color: #0f172a;
                }
                QSpinBox:focus { border-color: #2563eb; }
            """)
            f_pts_col.addWidget(self.spn_points)
            row3.addLayout(f_pts_col, 1)

        f_status_col = QVBoxLayout()
        f_status_col.setSpacing(4)
        lbl_status = QLabel("STATUS")
        lbl_status.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_status_col.addWidget(lbl_status)
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
        f_status_col.addWidget(self.cmb_status)
        row3.addLayout(f_status_col, 1)
        body_layout.addLayout(row3)

        # Notes / Preferences
        f_notes_col = QVBoxLayout()
        f_notes_col.setSpacing(4)
        lbl_notes = QLabel("NOTES & PREFERENCES")
        lbl_notes.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        f_notes_col.addWidget(lbl_notes)
        self.txt_notes = QLineEdit()
        self.txt_notes.setPlaceholderText("e.g. VIP regular shopper, preferred brands, delivery instructions...")
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

        btn_save = QPushButton("Save Customer Profile")
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

    def _prefill_data(self):
        if not self._customer_data:
            return
        self.txt_name.setText(self._customer_data.name)
        self.txt_phone.setText(self._customer_data.phone)
        self.txt_email.setText(self._customer_data.email or "")
        self.txt_address.setText(self._customer_data.address or "")
        self.txt_notes.setText(self._customer_data.notes or "")

        idx = self.cmb_status.findData(self._customer_data.is_active)
        if idx >= 0:
            self.cmb_status.setCurrentIndex(idx)

    def _on_header_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _on_header_mouse_move(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def _on_save(self):
        name = self.txt_name.text().strip()
        phone = self.txt_phone.text().strip()
        email = self.txt_email.text().strip() or None
        address = self.txt_address.text().strip() or None
        notes = self.txt_notes.text().strip() or None
        is_active = self.cmb_status.currentData()

        if not name:
            self._show_error("Customer name is required.")
            return

        if not phone:
            self._show_error("Phone number is required.")
            return

        try:
            if self._is_edit:
                dto = UpdateCustomerDTO(
                    name=name,
                    phone=phone,
                    email=email,
                    address=address,
                    notes=notes,
                    is_active=is_active,
                )
                self._customer_service.update_customer(self._customer_data.id, dto, actor=self._actor)
            else:
                pts = self.spn_points.value()
                dto_c = CreateCustomerDTO(
                    name=name,
                    phone=phone,
                    email=email,
                    address=address,
                    initial_points=pts,
                    notes=notes,
                    is_active=is_active,
                )
                self._customer_service.create_customer(dto_c, actor=self._actor)

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
