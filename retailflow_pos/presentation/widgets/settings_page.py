"""
RetailFlow POS - Settings & System Configuration Page
Presentation workspace for store profile administration, receipt template preferences,
live layout preview, managed logo lifecycle, and sanitized system diagnostics.
"""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import settings
from app.constants import ReceiptWidth
from application.dto.settings_dto import (
    StoreSettingsDTO,
    SystemInfoDTO,
    UpdateReceiptPreferencesDTO,
    UpdateStoreProfileDTO,
)
from application.services.settings_service import SettingsService
from domain.exceptions import (
    AccountInactiveError,
    AuthorizationError,
    ConfigurationError,
    ValidationError,
)
from infrastructure.database.models.auth import User
from presentation.styles.icons import IconManager
from presentation.widgets.toast_notification import ToastNotification


class _InfoCard(QFrame):
    """Diagnostic info card whose value labels can be updated in place."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.value_labels: list[QLabel] = []


class SettingsPage(QWidget):
    """Store profile, receipt preferences, and system diagnostics administration page."""

    settings_updated = Signal()

    def __init__(
        self,
        current_user: User,
        settings_service: SettingsService,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._user = current_user
        self._service = settings_service
        self._cached_dto: Optional[StoreSettingsDTO] = None
        self._cached_sys_info: Optional[SystemInfoDTO] = None
        self._staged_logo_path: Optional[Path] = None

        self._is_saving_profile = False
        self._is_saving_receipt = False

        self._init_ui()
        self._setup_shortcuts()
        self.load_settings()

    # ─── UI Initialization ───

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Toast notification overlay
        self._toast = ToastNotification(self)

        # ── 1. Page Header & Actions ──
        hdr_row = QHBoxLayout()
        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)

        title_lbl = QLabel("System Settings")
        title_lbl.setStyleSheet(
            "font-size: 22px; font-weight: 800; color: #0f172a; letter-spacing: -0.4px;"
        )
        header_layout.addWidget(title_lbl)

        subtitle_lbl = QLabel(
            "Manage store information, receipt preferences, and system diagnostics."
        )
        subtitle_lbl.setStyleSheet("font-size: 13px; color: #64748b; font-weight: 500;")
        header_layout.addWidget(subtitle_lbl)

        hdr_row.addLayout(header_layout)
        hdr_row.addStretch()

        btn_refresh = QPushButton(" Refresh")
        btn_refresh.setIcon(IconManager.get_pixmap("clock", color="#475569", size=13))
        btn_refresh.setFixedHeight(36)
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 700;
                padding: 0px 14px;
            }
            QPushButton:hover {
                background-color: #f8fafc;
                border-color: #94a3b8;
                color: #2563eb;
            }
        """)
        btn_refresh.clicked.connect(self.load_settings)
        hdr_row.addWidget(btn_refresh)

        main_layout.addLayout(hdr_row)

        # ── 2. Segmented Navigation Bar ──
        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)

        self.btn_tab_profile = QPushButton(" Store Profile")
        self.btn_tab_receipt = QPushButton(" Receipt Preferences")
        self.btn_tab_diagnostics = QPushButton(" System Diagnostics")

        self._nav_tabs = [self.btn_tab_profile, self.btn_tab_receipt, self.btn_tab_diagnostics]

        for idx, btn in enumerate(self._nav_tabs):
            btn.setFixedHeight(36)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, i=idx: self._switch_tab(i))
            nav_row.addWidget(btn)

        nav_row.addStretch()
        main_layout.addLayout(nav_row)

        # ── 3. Content Area with Tab Pages ──
        self._tab_stack = QStackedWidget()

        self._profile_widget = self._build_profile_tab()
        self._receipt_widget = self._build_receipt_tab()
        self._diagnostics_widget = self._build_diagnostics_tab()

        self._tab_stack.addWidget(self._profile_widget)
        self._tab_stack.addWidget(self._receipt_widget)
        self._tab_stack.addWidget(self._diagnostics_widget)

        main_layout.addWidget(self._tab_stack, stretch=1)
        self._switch_tab(0)

    def _setup_shortcuts(self):
        """Keyboard shortcuts for efficient administration."""
        self._save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self._save_shortcut.activated.connect(self._on_shortcut_save)

    def _on_shortcut_save(self):
        """Trigger save on the currently active tab."""
        current_idx = self._tab_stack.currentIndex()
        if current_idx == 0 and self.is_profile_dirty():
            self._on_save_profile()
        elif current_idx == 1 and self.is_receipt_dirty():
            self._on_save_receipt()

    # ─── Navigation Switcher ───

    def _switch_tab(self, index: int):
        self._tab_stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_tabs):
            if i == index:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2563eb;
                        color: #ffffff;
                        border: 1px solid #2563eb;
                        border-radius: 8px;
                        font-size: 13px;
                        font-weight: 700;
                        padding: 0px 16px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #ffffff;
                        color: #475569;
                        border: 1px solid #e2e8f0;
                        border-radius: 8px;
                        font-size: 13px;
                        font-weight: 600;
                        padding: 0px 16px;
                    }
                    QPushButton:hover {
                        background-color: #f8fafc;
                        border-color: #cbd5e1;
                        color: #0f172a;
                    }
                """)

    # ─── Tab 1: Store Profile ───

    def _build_profile_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(20)

        # Left Column: Profile Form Card
        left_card = QFrame()
        left_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(14)

        sec_title = QLabel("Business Profile")
        sec_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #0f172a; border: none;")
        left_layout.addWidget(sec_title)

        # Store Name
        lbl_name = QLabel("Store Name *")
        lbl_name.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155; border: none;")
        self.txt_store_name = QLineEdit()
        self.txt_store_name.setPlaceholderText("e.g. RetailFlow Flagship Store")
        self.txt_store_name.setMaxLength(100)
        self.txt_store_name.setStyleSheet(self._input_style())
        self.txt_store_name.textChanged.connect(self._on_profile_form_changed)
        left_layout.addWidget(lbl_name)
        left_layout.addWidget(self.txt_store_name)

        # Store Address
        lbl_address = QLabel("Store / Business Address")
        lbl_address.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155; border: none;")
        self.txt_store_address = QPlainTextEdit()
        self.txt_store_address.setPlaceholderText("e.g. Unit 101, Commercial Center, Ayala Ave, Makati City")
        self.txt_store_address.setFixedHeight(68)
        self.txt_store_address.setStyleSheet(self._input_style())
        self.txt_store_address.textChanged.connect(self._on_profile_form_changed)
        left_layout.addWidget(lbl_address)
        left_layout.addWidget(self.txt_store_address)

        # Contact Number
        lbl_contact = QLabel("Contact Number")
        lbl_contact.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155; border: none;")
        self.txt_contact = QLineEdit()
        self.txt_contact.setPlaceholderText("e.g. +63 2 8123 4567 / +63 917 123 4567")
        self.txt_contact.setMaxLength(50)
        self.txt_contact.setStyleSheet(self._input_style())
        self.txt_contact.textChanged.connect(self._on_profile_form_changed)
        left_layout.addWidget(lbl_contact)
        left_layout.addWidget(self.txt_contact)

        # Email
        lbl_email = QLabel("Business Email")
        lbl_email.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155; border: none;")
        self.txt_email = QLineEdit()
        self.txt_email.setPlaceholderText("e.g. contact@retailflow.ph")
        self.txt_email.setMaxLength(100)
        self.txt_email.setStyleSheet(self._input_style())
        self.txt_email.textChanged.connect(self._on_profile_form_changed)
        left_layout.addWidget(lbl_email)
        left_layout.addWidget(self.txt_email)

        # TIN
        lbl_tin = QLabel("Tax Identification Number (TIN)")
        lbl_tin.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155; border: none;")
        self.txt_tin = QLineEdit()
        self.txt_tin.setPlaceholderText("e.g. 123-456-789-000")
        self.txt_tin.setMaxLength(50)
        self.txt_tin.setStyleSheet(self._input_style())
        self.txt_tin.textChanged.connect(self._on_profile_form_changed)
        left_layout.addWidget(lbl_tin)
        left_layout.addWidget(self.txt_tin)

        left_layout.addSpacing(10)

        # Save Button
        self.btn_save_profile = QPushButton("Save Profile Changes")
        self.btn_save_profile.setFixedHeight(40)
        self.btn_save_profile.setCursor(Qt.PointingHandCursor)
        self.btn_save_profile.setStyleSheet(self._primary_button_style())
        self.btn_save_profile.clicked.connect(self._on_save_profile)
        left_layout.addWidget(self.btn_save_profile)

        left_layout.addStretch()
        layout.addWidget(left_card, stretch=6)

        # Right Column: Store Logo Management Card
        right_card = QFrame()
        right_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(14)

        logo_title = QLabel("Store Branding / Logo")
        logo_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #0f172a; border: none;")
        right_layout.addWidget(logo_title)

        logo_desc = QLabel(
            "Upload a PNG or JPEG logo (max 2 MB). The logo is rendered on thermal receipts and system templates."
        )
        logo_desc.setWordWrap(True)
        logo_desc.setStyleSheet("font-size: 12px; color: #64748b; border: none;")
        right_layout.addWidget(logo_desc)

        # Logo Preview Box
        self.logo_preview_frame = QFrame()
        self.logo_preview_frame.setFixedHeight(180)
        self.logo_preview_frame.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 2px dashed #cbd5e1;
                border-radius: 10px;
            }
        """)
        preview_layout = QVBoxLayout(self.logo_preview_frame)
        preview_layout.setAlignment(Qt.AlignCenter)

        self.lbl_logo_image = QLabel()
        self.lbl_logo_image.setAlignment(Qt.AlignCenter)
        self.lbl_logo_image.setStyleSheet("border: none; background: transparent;")
        preview_layout.addWidget(self.lbl_logo_image)

        self.lbl_logo_status = QLabel("No Logo Configured")
        self.lbl_logo_status.setAlignment(Qt.AlignCenter)
        self.lbl_logo_status.setStyleSheet("font-size: 12px; font-weight: 600; color: #94a3b8; border: none;")
        preview_layout.addWidget(self.lbl_logo_status)

        right_layout.addWidget(self.logo_preview_frame)

        # Logo Actions Row
        logo_btn_row = QHBoxLayout()
        logo_btn_row.setSpacing(10)

        self.btn_choose_logo = QPushButton("Choose Logo")
        self.btn_choose_logo.setFixedHeight(36)
        self.btn_choose_logo.setCursor(Qt.PointingHandCursor)
        self.btn_choose_logo.setStyleSheet(self._secondary_button_style())
        self.btn_choose_logo.clicked.connect(self._on_choose_logo)
        logo_btn_row.addWidget(self.btn_choose_logo)

        self.btn_apply_logo = QPushButton("Save Logo")
        self.btn_apply_logo.setFixedHeight(36)
        self.btn_apply_logo.setCursor(Qt.PointingHandCursor)
        self.btn_apply_logo.setStyleSheet(self._primary_button_style())
        self.btn_apply_logo.clicked.connect(self._on_apply_staged_logo)
        self.btn_apply_logo.setVisible(False)
        logo_btn_row.addWidget(self.btn_apply_logo)

        self.btn_remove_logo = QPushButton("Remove")
        self.btn_remove_logo.setFixedHeight(36)
        self.btn_remove_logo.setCursor(Qt.PointingHandCursor)
        self.btn_remove_logo.setStyleSheet(self._danger_button_style())
        self.btn_remove_logo.clicked.connect(self._on_remove_logo)
        self.btn_remove_logo.setVisible(False)
        logo_btn_row.addWidget(self.btn_remove_logo)

        right_layout.addLayout(logo_btn_row)
        right_layout.addStretch()

        layout.addWidget(right_card, stretch=4)
        scroll.setWidget(container)
        return scroll

    # ─── Tab 2: Receipt Preferences ───

    def _build_receipt_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(20)

        # Left Column: Receipt Form
        form_card = QFrame()
        form_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(20, 20, 20, 20)
        form_layout.setSpacing(14)

        pref_title = QLabel("Receipt Formatting & Display")
        pref_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #0f172a; border: none;")
        form_layout.addWidget(pref_title)

        # Receipt Header
        lbl_header = QLabel("Receipt Header")
        lbl_header.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155; border: none;")
        self.txt_receipt_header = QLineEdit()
        self.txt_receipt_header.setPlaceholderText("Official Sales Invoice / Thermal Receipt")
        self.txt_receipt_header.setMaxLength(255)
        self.txt_receipt_header.setStyleSheet(self._input_style())
        self.txt_receipt_header.textChanged.connect(self._on_receipt_form_changed)
        form_layout.addWidget(lbl_header)
        form_layout.addWidget(self.txt_receipt_header)

        # Receipt Footer
        lbl_footer = QLabel("Receipt Footer")
        lbl_footer.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155; border: none;")
        self.txt_receipt_footer = QPlainTextEdit()
        self.txt_receipt_footer.setPlaceholderText("Thank you for shopping with us!")
        self.txt_receipt_footer.setFixedHeight(68)
        self.txt_receipt_footer.setStyleSheet(self._input_style())
        self.txt_receipt_footer.textChanged.connect(self._on_receipt_form_changed)
        form_layout.addWidget(lbl_footer)
        form_layout.addWidget(self.txt_receipt_footer)

        # Paper Width
        lbl_width = QLabel("Thermal Paper Width")
        lbl_width.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155; border: none;")
        self.cmb_paper_width = QComboBox()
        self.cmb_paper_width.addItem("80mm (Standard Desktop Receipt)", ReceiptWidth.MM_80.value)
        self.cmb_paper_width.addItem("58mm (Compact Mobile Receipt)", ReceiptWidth.MM_58.value)
        self.cmb_paper_width.setStyleSheet(self._combo_style())
        self.cmb_paper_width.currentIndexChanged.connect(self._on_receipt_form_changed)
        form_layout.addWidget(lbl_width)
        form_layout.addWidget(self.cmb_paper_width)

        form_layout.addSpacing(6)

        # Toggles Title
        toggles_title = QLabel("Receipt Header/Footer Visibility Elements")
        toggles_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #1e293b; border: none;")
        form_layout.addWidget(toggles_title)

        self.chk_show_address = QCheckBox("Include Store Address on Receipt")
        self.chk_show_contact = QCheckBox("Include Contact Number on Receipt")
        self.chk_show_tin = QCheckBox("Include TIN / Registration Number on Receipt")
        self.chk_show_tax = QCheckBox("Include Tax Breakdown on Receipt (Display Only)")

        for chk in [self.chk_show_address, self.chk_show_contact, self.chk_show_tin, self.chk_show_tax]:
            chk.setStyleSheet("""
                QCheckBox {
                    font-size: 13px;
                    font-weight: 600;
                    color: #334155;
                    spacing: 8px;
                    border: none;
                }
                QCheckBox::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 4px;
                    border: 1px solid #cbd5e1;
                    background-color: #ffffff;
                }
                QCheckBox::indicator:checked {
                    background-color: #2563eb;
                    border-color: #2563eb;
                }
            """)
            chk.toggled.connect(self._on_receipt_form_changed)
            form_layout.addWidget(chk)

        # Tax notice caption
        tax_caption = QLabel(
            "Note: 'Include Tax Breakdown' controls receipt print display only. It does not alter VAT calculation rules."
        )
        tax_caption.setWordWrap(True)
        tax_caption.setStyleSheet("font-size: 11px; color: #64748b; font-style: italic; border: none;")
        form_layout.addWidget(tax_caption)

        form_layout.addSpacing(10)

        # Save Button
        self.btn_save_receipt = QPushButton("Save Receipt Preferences")
        self.btn_save_receipt.setFixedHeight(40)
        self.btn_save_receipt.setCursor(Qt.PointingHandCursor)
        self.btn_save_receipt.setStyleSheet(self._primary_button_style())
        self.btn_save_receipt.clicked.connect(self._on_save_receipt)
        form_layout.addWidget(self.btn_save_receipt)

        form_layout.addStretch()
        layout.addWidget(form_card, stretch=6)

        # Right Column: Live Receipt Preview Card
        preview_container = QFrame()
        preview_container.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        preview_outer_layout = QVBoxLayout(preview_container)
        preview_outer_layout.setContentsMargins(20, 20, 20, 20)
        preview_outer_layout.setSpacing(10)

        prev_title = QLabel("Live Layout Preview")
        prev_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #0f172a; border: none;")
        preview_outer_layout.addWidget(prev_title)

        # Simulated Thermal Paper Card
        self.paper_preview_card = QFrame()
        self.paper_preview_card.setObjectName("thermalPaperPreview")
        self.paper_preview_card.setStyleSheet("""
            QFrame#thermalPaperPreview {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)
        self.paper_layout = QVBoxLayout(self.paper_preview_card)
        self.paper_layout.setContentsMargins(14, 14, 14, 14)
        self.paper_layout.setSpacing(4)

        self.lbl_prev_store = QLabel("RetailFlow Store")
        self.lbl_prev_store.setAlignment(Qt.AlignCenter)
        self.lbl_prev_store.setStyleSheet("font-size: 13px; font-weight: 800; color: #0f172a; border: none;")
        self.paper_layout.addWidget(self.lbl_prev_store)

        self.lbl_prev_address = QLabel("123 Ayala Avenue, Makati City")
        self.lbl_prev_address.setAlignment(Qt.AlignCenter)
        self.lbl_prev_address.setStyleSheet("font-size: 10px; color: #475569; border: none;")
        self.paper_layout.addWidget(self.lbl_prev_address)

        self.lbl_prev_contact = QLabel("Tel: +63 2 8123 4567")
        self.lbl_prev_contact.setAlignment(Qt.AlignCenter)
        self.lbl_prev_contact.setStyleSheet("font-size: 10px; color: #475569; border: none;")
        self.paper_layout.addWidget(self.lbl_prev_contact)

        self.lbl_prev_tin = QLabel("TIN: 123-456-789-000")
        self.lbl_prev_tin.setAlignment(Qt.AlignCenter)
        self.lbl_prev_tin.setStyleSheet("font-size: 10px; color: #475569; border: none;")
        self.paper_layout.addWidget(self.lbl_prev_tin)

        self.lbl_prev_div1 = QLabel("----------------------------------------")
        self.lbl_prev_div1.setAlignment(Qt.AlignCenter)
        self.lbl_prev_div1.setStyleSheet("color: #94a3b8; font-size: 10px; border: none;")
        self.paper_layout.addWidget(self.lbl_prev_div1)

        self.lbl_prev_header = QLabel("Official Sales Invoice / Thermal Receipt")
        self.lbl_prev_header.setAlignment(Qt.AlignCenter)
        self.lbl_prev_header.setStyleSheet("font-size: 10px; font-weight: 700; color: #1e293b; border: none;")
        self.paper_layout.addWidget(self.lbl_prev_header)

        self.lbl_prev_div2 = QLabel("----------------------------------------")
        self.lbl_prev_div2.setAlignment(Qt.AlignCenter)
        self.lbl_prev_div2.setStyleSheet("color: #94a3b8; font-size: 10px; border: none;")
        self.paper_layout.addWidget(self.lbl_prev_div2)

        # Mock items body
        mock_body = QLabel(
            "2x Artisan Coffee Beans         ₱450.00\n"
            "1x Thermal Paper Roll           ₱120.00\n"
            "----------------------------------------\n"
            "Subtotal                        ₱570.00"
        )
        mock_body.setStyleSheet("font-size: 10px; color: #334155; border: none;")
        self.paper_layout.addWidget(mock_body)

        self.lbl_prev_tax_block = QLabel(
            "  12% Output VAT                 ₱61.07\n"
            "  VATable Sales                 ₱508.93"
        )
        self.lbl_prev_tax_block.setStyleSheet("font-size: 10px; color: #64748b; border: none;")
        self.paper_layout.addWidget(self.lbl_prev_tax_block)

        mock_totals = QLabel(
            "TOTAL                           ₱570.00\n"
            "CASH                            ₱600.00\n"
            "CHANGE                           ₱30.00\n"
            "----------------------------------------"
        )
        mock_totals.setStyleSheet("font-size: 10px; font-weight: 700; color: #0f172a; border: none;")
        self.paper_layout.addWidget(mock_totals)

        self.lbl_prev_footer = QLabel("Thank you for shopping with us!")
        self.lbl_prev_footer.setAlignment(Qt.AlignCenter)
        self.lbl_prev_footer.setWordWrap(True)
        self.lbl_prev_footer.setStyleSheet("font-size: 10px; color: #475569; border: none;")
        self.paper_layout.addWidget(self.lbl_prev_footer)

        preview_outer_layout.addWidget(self.paper_preview_card)

        preview_tag = QLabel("RECEIPT PREVIEW (Visual Layout Demonstration Only)")
        preview_tag.setAlignment(Qt.AlignCenter)
        preview_tag.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; border: none;")
        preview_outer_layout.addWidget(preview_tag)

        preview_outer_layout.addStretch()
        layout.addWidget(preview_container, stretch=4)

        scroll.setWidget(container)
        return scroll

    # ─── Tab 3: System Diagnostics ───

    def _build_diagnostics_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(16)

        # Header Row with Copy Action
        top_diag_row = QHBoxLayout()
        diag_sec_title = QLabel("System Environment & Runtime Diagnostics")
        diag_sec_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #0f172a;")
        top_diag_row.addWidget(diag_sec_title)
        top_diag_row.addStretch()

        self.btn_copy_diag = QPushButton(" Copy Diagnostic Summary")
        self.btn_copy_diag.setIcon(IconManager.get_pixmap("users", color="#2563eb", size=13))
        self.btn_copy_diag.setFixedHeight(36)
        self.btn_copy_diag.setCursor(Qt.PointingHandCursor)
        self.btn_copy_diag.setStyleSheet(self._secondary_button_style())
        self.btn_copy_diag.clicked.connect(self._on_copy_diagnostics)
        top_diag_row.addWidget(self.btn_copy_diag)

        layout.addLayout(top_diag_row)

        # Grid of Info Cards
        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)

        # Card 1: Application & OS
        self.card_app = self._build_info_card(
            "Application & Platform",
            [
                ("App Name", "—"),
                ("Version", "—"),
                ("Environment", "—"),
                ("OS Platform", "—"),
            ],
        )
        cards_row.addWidget(self.card_app)

        # Card 2: Runtime & Regional
        self.card_runtime = self._build_info_card(
            "Runtime & Regional Settings",
            [
                ("Python Version", "—"),
                ("PySide6 Runtime", "—"),
                ("Timezone", "—"),
                ("Currency", "—"),
            ],
        )
        cards_row.addWidget(self.card_runtime)

        layout.addLayout(cards_row)

        cards_row2 = QHBoxLayout()
        cards_row2.setSpacing(16)

        # Card 3: Database
        self.card_db = self._build_info_card(
            "Database Engine",
            [
                ("Engine Type", "—"),
                ("Location / Host", "—"),
                ("Connection Status", "Connected / Active"),
                ("Singleton Record", "store_settings (id=1)"),
            ],
        )
        cards_row2.addWidget(self.card_db)

        # Card 4: Storage Directories
        self.card_storage = self._build_info_card(
            "Managed Storage Directories",
            [
                ("Data Directory", "—"),
                ("Logs Directory", "—"),
                ("Backups Directory", "—"),
                ("Exports Directory", "—"),
            ],
        )
        cards_row2.addWidget(self.card_storage)

        layout.addLayout(cards_row2)
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    def _build_info_card(self, title: str, items: list[tuple[str, str]]) -> _InfoCard:
        card = _InfoCard()
        card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        card_title = QLabel(title)
        card_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #0f172a; border: none;")
        layout.addWidget(card_title)

        value_labels: list[QLabel] = []
        for label_text, val_text in items:
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-size: 12px; color: #64748b; font-weight: 600; border: none;")
            val = QLabel(val_text)
            val.setStyleSheet("font-size: 12px; color: #0f172a; font-weight: 700; border: none;")
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            layout.addLayout(row)
            value_labels.append(val)

        card.value_labels = value_labels
        layout.addStretch()
        return card

    # ─── Data Loading & Binding ───

    def load_settings(self):
        """Fetch authoritative StoreSettingsDTO and SystemInfoDTO from service."""
        try:
            dto = self._service.get_settings(actor=self._user)
            self._cached_dto = dto

            # Populate profile form
            self.txt_store_name.setText(dto.store_name)
            self.txt_store_address.setPlainText(dto.store_address or "")
            self.txt_contact.setText(dto.contact_number or "")
            self.txt_email.setText(dto.email or "")
            self.txt_tin.setText(dto.tin or "")

            # Logo display
            self._render_logo_preview(dto.logo_path)
            self._staged_logo_path = None
            self.btn_apply_logo.setVisible(False)
            self.btn_remove_logo.setVisible(bool(dto.logo_path))

            # Populate receipt form
            self.txt_receipt_header.setText(dto.receipt_header or "")
            self.txt_receipt_footer.setPlainText(dto.receipt_footer or "")

            width_idx = self.cmb_paper_width.findData(dto.paper_width)
            if width_idx >= 0:
                self.cmb_paper_width.setCurrentIndex(width_idx)

            self.chk_show_address.setChecked(dto.show_store_address)
            self.chk_show_contact.setChecked(dto.show_contact)
            self.chk_show_tin.setChecked(dto.show_tin)
            self.chk_show_tax.setChecked(dto.show_tax_details)

            # Update live receipt preview
            self._update_live_receipt_preview()

            # Load diagnostics
            sys_info = self._service.get_system_info(actor=self._user)
            self._cached_sys_info = sys_info
            self._update_diagnostics_display(sys_info)

            # Update button enabled states
            self._update_save_button_states()

        except AuthorizationError as e:
            self._toast.show_toast(f"Access Denied: {e}", is_error=True)
        except ConfigurationError as e:
            self._toast.show_toast(f"Configuration Error: {e}", is_error=True)
        except Exception as e:
            self._toast.show_toast(f"Error loading settings: {e}", is_error=True)

    def _render_logo_preview(self, logo_relative_path: Optional[str]):
        """Render active or fallback logo in preview box."""
        if logo_relative_path:
            physical_path = settings.data_dir / logo_relative_path
            if physical_path.exists():
                pixmap = QPixmap(str(physical_path))
                if not pixmap.isNull():
                    scaled = pixmap.scaled(180, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.lbl_logo_image.setPixmap(scaled)
                    self.lbl_logo_image.setVisible(True)
                    self.lbl_logo_status.setText("Active Managed Logo")
                    self.lbl_logo_status.setStyleSheet("font-size: 11px; font-weight: 700; color: #10b981; border: none;")
                    return

        # Fallback / No Logo
        self.lbl_logo_image.clear()
        self.lbl_logo_image.setVisible(False)
        self.lbl_logo_status.setText("No Logo Configured")
        self.lbl_logo_status.setStyleSheet("font-size: 12px; font-weight: 600; color: #94a3b8; border: none;")

    def _update_live_receipt_preview(self):
        """Update live receipt preview card using current form values."""
        name = self.txt_store_name.text().strip() or "RetailFlow Store"
        address = self.txt_store_address.toPlainText().strip()
        contact = self.txt_contact.text().strip()
        tin = self.txt_tin.text().strip()
        header = self.txt_receipt_header.text().strip() or "Official Sales Invoice / Thermal Receipt"
        footer = self.txt_receipt_footer.toPlainText().strip() or "Thank you for shopping with us!"

        paper_width = self.cmb_paper_width.currentData() or "80mm"

        # Width visual adjustment
        if paper_width == "58mm":
            self.paper_preview_card.setFixedWidth(270)
            divider = "------------------------------"
        else:
            self.paper_preview_card.setFixedWidth(350)
            divider = "----------------------------------------"

        self.lbl_prev_store.setText(name)
        self.lbl_prev_div1.setText(divider)
        self.lbl_prev_div2.setText(divider)
        self.lbl_prev_header.setText(header)
        self.lbl_prev_footer.setText(footer)

        self.lbl_prev_address.setText(address if address else "Store Address")
        self.lbl_prev_address.setVisible(self.chk_show_address.isChecked())

        self.lbl_prev_contact.setText(f"Tel: {contact}" if contact else "Tel: Contact Number")
        self.lbl_prev_contact.setVisible(self.chk_show_contact.isChecked())

        self.lbl_prev_tin.setText(f"TIN: {tin}" if tin else "TIN: Registration")
        self.lbl_prev_tin.setVisible(self.chk_show_tin.isChecked())

        self.lbl_prev_tax_block.setVisible(self.chk_show_tax.isChecked())

    def _update_diagnostics_display(self, info: SystemInfoDTO):
        """Update diagnostic cards with authoritative, sanitized values."""
        self.card_app.value_labels[0].setText(info.app_name)
        self.card_app.value_labels[1].setText(info.app_version)
        self.card_app.value_labels[2].setText(info.app_env)
        self.card_app.value_labels[3].setText(info.os_platform)

        self.card_runtime.value_labels[0].setText(info.python_version)
        self.card_runtime.value_labels[1].setText(info.pyside_version)
        self.card_runtime.value_labels[2].setText(info.timezone)
        self.card_runtime.value_labels[3].setText(info.currency)

        self.card_db.value_labels[0].setText(info.database_type)
        self.card_db.value_labels[1].setText(info.database_location)

        self.card_storage.value_labels[0].setText(info.data_dir)
        self.card_storage.value_labels[1].setText(info.log_dir)
        self.card_storage.value_labels[2].setText(info.backup_dir)
        self.card_storage.value_labels[3].setText(info.export_dir)

    # ─── Dirty-State Evaluation ───

    def is_profile_dirty(self) -> bool:
        """Evaluate whether store profile fields differ from persisted baseline."""
        if not self._cached_dto:
            return False

        norm_name = self.txt_store_name.text().strip()
        norm_address = self.txt_store_address.toPlainText().strip() or None
        norm_contact = self.txt_contact.text().strip() or None
        norm_email = self.txt_email.text().strip() or None
        norm_tin = self.txt_tin.text().strip() or None

        return (
            norm_name != self._cached_dto.store_name
            or norm_address != (self._cached_dto.store_address or None)
            or norm_contact != (self._cached_dto.contact_number or None)
            or norm_email != (self._cached_dto.email or None)
            or norm_tin != (self._cached_dto.tin or None)
            or (self._staged_logo_path is not None)
        )

    def is_receipt_dirty(self) -> bool:
        """Evaluate whether receipt preference fields differ from persisted baseline."""
        if not self._cached_dto:
            return False

        norm_header = self.txt_receipt_header.text().strip() or "Official Sales Invoice / Thermal Receipt"
        norm_footer = self.txt_receipt_footer.toPlainText().strip() or "Thank you for shopping with us!"
        norm_width = self.cmb_paper_width.currentData() or "80mm"

        return (
            norm_header != (self._cached_dto.receipt_header or "Official Sales Invoice / Thermal Receipt")
            or norm_footer != (self._cached_dto.receipt_footer or "Thank you for shopping with us!")
            or norm_width != self._cached_dto.paper_width
            or self.chk_show_address.isChecked() != self._cached_dto.show_store_address
            or self.chk_show_contact.isChecked() != self._cached_dto.show_contact
            or self.chk_show_tin.isChecked() != self._cached_dto.show_tin
            or self.chk_show_tax.isChecked() != self._cached_dto.show_tax_details
        )

    def has_unsaved_changes(self) -> bool:
        """Check if any section has unsaved edits."""
        return self.is_profile_dirty() or self.is_receipt_dirty()

    def discard_changes(self):
        """Discard in-memory edits and restore persisted values."""
        self._staged_logo_path = None
        self.load_settings()

    def _on_profile_form_changed(self):
        self._update_save_button_states()
        self._update_live_receipt_preview()

    def _on_receipt_form_changed(self):
        self._update_save_button_states()
        self._update_live_receipt_preview()

    def _update_save_button_states(self):
        profile_dirty = self.is_profile_dirty()
        self.btn_save_profile.setEnabled(profile_dirty and not self._is_saving_profile)

        receipt_dirty = self.is_receipt_dirty()
        self.btn_save_receipt.setEnabled(receipt_dirty and not self._is_saving_receipt)

    # ─── Form Actions & Service Calls ───

    def _on_save_profile(self):
        """Execute authoritative store profile update."""
        if self._is_saving_profile:
            return

        self._is_saving_profile = True
        self.btn_save_profile.setEnabled(False)

        dto = UpdateStoreProfileDTO(
            store_name=self.txt_store_name.text(),
            store_address=self.txt_store_address.toPlainText(),
            contact_number=self.txt_contact.text(),
            email=self.txt_email.text(),
            tin=self.txt_tin.text(),
        )

        try:
            updated_dto = self._service.update_store_profile(dto, actor=self._user)
            self._cached_dto = updated_dto
            self.load_settings()
            self._toast.show_toast("Store profile updated successfully.")
            self.settings_updated.emit()
        except ValidationError as e:
            self._toast.show_toast(f"Validation Error: {e}", is_error=True)
        except AuthorizationError as e:
            self._toast.show_toast(f"Permission Denied: {e}", is_error=True)
        except Exception as e:
            self._toast.show_toast(f"Failed to update profile: {e}", is_error=True)
        finally:
            self._is_saving_profile = False
            self._update_save_button_states()

    def _on_save_receipt(self):
        """Execute authoritative receipt preferences update."""
        if self._is_saving_receipt:
            return

        self._is_saving_receipt = True
        self.btn_save_receipt.setEnabled(False)

        dto = UpdateReceiptPreferencesDTO(
            receipt_header=self.txt_receipt_header.text(),
            receipt_footer=self.txt_receipt_footer.toPlainText(),
            paper_width=self.cmb_paper_width.currentData(),
            show_store_address=self.chk_show_address.isChecked(),
            show_contact=self.chk_show_contact.isChecked(),
            show_tin=self.chk_show_tin.isChecked(),
            show_tax_details=self.chk_show_tax.isChecked(),
        )

        try:
            updated_dto = self._service.update_receipt_preferences(dto, actor=self._user)
            self._cached_dto = updated_dto
            self.load_settings()
            self._toast.show_toast("Receipt preferences updated successfully.")
            self.settings_updated.emit()
        except ValidationError as e:
            self._toast.show_toast(f"Validation Error: {e}", is_error=True)
        except AuthorizationError as e:
            self._toast.show_toast(f"Permission Denied: {e}", is_error=True)
        except Exception as e:
            self._toast.show_toast(f"Failed to update receipt preferences: {e}", is_error=True)
        finally:
            self._is_saving_receipt = False
            self._update_save_button_states()

    def _on_choose_logo(self):
        """Open file dialog for choosing a new logo file to stage."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Store Logo",
            "",
            "Images (*.png *.jpg *.jpeg)",
        )
        if not file_path:
            return

        path = Path(file_path)
        if not path.exists():
            return

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._toast.show_toast("Unable to decode selected image.", is_error=True)
            return

        # Stage logo locally
        self._staged_logo_path = path
        scaled = pixmap.scaled(180, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lbl_logo_image.setPixmap(scaled)
        self.lbl_logo_image.setVisible(True)
        self.lbl_logo_status.setText("Staged Logo (Unsaved)")
        self.lbl_logo_status.setStyleSheet("font-size: 11px; font-weight: 700; color: #2563eb; border: none;")

        self.btn_apply_logo.setVisible(True)
        self.btn_apply_logo.setEnabled(True)
        self._update_save_button_states()

    def _on_apply_staged_logo(self):
        """Execute authoritative store logo upload and persistence."""
        if not self._staged_logo_path:
            return

        try:
            updated_dto = self._service.update_store_logo(self._staged_logo_path, actor=self._user)
            self._cached_dto = updated_dto
            self._staged_logo_path = None
            self.load_settings()
            self._toast.show_toast("Store logo updated successfully.")
            self.settings_updated.emit()
        except ValidationError as e:
            self._toast.show_toast(f"Logo Error: {e}", is_error=True)
        except AuthorizationError as e:
            self._toast.show_toast(f"Permission Denied: {e}", is_error=True)
        except Exception as e:
            self._toast.show_toast(f"Failed to update logo: {e}", is_error=True)

    def _on_remove_logo(self):
        """Confirm and execute store logo removal."""
        reply = QMessageBox.question(
            self,
            "Remove Store Logo",
            "Are you sure you want to remove the current store logo?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            updated_dto = self._service.remove_store_logo(actor=self._user)
            self._cached_dto = updated_dto
            self._staged_logo_path = None
            self.load_settings()
            self._toast.show_toast("Store logo removed.")
            self.settings_updated.emit()
        except AuthorizationError as e:
            self._toast.show_toast(f"Permission Denied: {e}", is_error=True)
        except Exception as e:
            self._toast.show_toast(f"Failed to remove logo: {e}", is_error=True)

    def _on_copy_diagnostics(self):
        """Copy formatted diagnostic summary to clipboard."""
        if not self._cached_sys_info:
            return

        info = self._cached_sys_info
        summary = (
            f"=== RetailFlow POS System Diagnostics ===\n"
            f"\n"
            f"Application\n"
            f"  Name:          {info.app_name}\n"
            f"  Version:       {info.app_version}\n"
            f"  Environment:   {info.app_env}\n"
            f"\n"
            f"Runtime\n"
            f"  Platform:      {info.os_platform}\n"
            f"  Python:        {info.python_version}\n"
            f"  PySide6:       {info.pyside_version}\n"
            f"\n"
            f"Business\n"
            f"  Timezone:      {info.timezone}\n"
            f"  Currency:      {info.currency}\n"
            f"\n"
            f"Database\n"
            f"  Engine:        {info.database_type}\n"
            f"  Location:      {info.database_location}\n"
            f"\n"
            f"Storage\n"
            f"  Data:          {info.data_dir}\n"
            f"  Logs:          {info.log_dir}\n"
            f"  Backups:       {info.backup_dir}\n"
            f"  Exports:       {info.export_dir}\n"
            f"\n"
            f"========================================="
        )

        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(summary)
            self._toast.show_toast("Diagnostic summary copied to clipboard.")

    # ─── Reusable Styles ───

    def _input_style(self) -> str:
        return """
            QLineEdit, QPlainTextEdit {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus, QPlainTextEdit:focus {
                border-color: #2563eb;
                background-color: #ffffff;
            }
        """

    def _combo_style(self) -> str:
        return """
            QComboBox {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QComboBox:focus {
                border-color: #2563eb;
            }
        """

    def _primary_button_style(self) -> str:
        return """
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 700;
                padding: 0px 16px;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton:disabled {
                background-color: #94a3b8;
                color: #f1f5f9;
            }
        """

    def _secondary_button_style(self) -> str:
        return """
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 700;
                padding: 0px 14px;
            }
            QPushButton:hover {
                background-color: #f8fafc;
                border-color: #94a3b8;
                color: #2563eb;
            }
        """

    def _danger_button_style(self) -> str:
        return """
            QPushButton {
                background-color: #ffffff;
                color: #dc2626;
                border: 1px solid #fca5a5;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 700;
                padding: 0px 14px;
            }
            QPushButton:hover {
                background-color: #fef2f2;
                border-color: #ef4444;
                color: #b91c1c;
            }
        """
