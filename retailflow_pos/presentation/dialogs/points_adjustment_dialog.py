"""
RetailFlow POS - Loyalty Points Adjustment Dialog
Frameless modal for adding bonus reward points or redeeming customer loyalty points
with live tier recalculation preview.
"""

from typing import Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
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

from application.dto.customer_dto import CustomerResponseDTO
from application.services.customer_service import CustomerService
from domain.exceptions import RetailFlowError
from infrastructure.database.models.auth import User
from presentation.styles.icons import IconManager


class PointsAdjustmentDialog(QDialog):
    """Modal for adjusting customer loyalty points."""

    def __init__(
        self,
        customer_service: CustomerService,
        customer: CustomerResponseDTO,
        current_actor: User,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._customer_service = customer_service
        self._customer = customer
        self._actor = current_actor
        self._mode = "add"  # 'add' or 'deduct'
        self._drag_pos = QPoint()

        self.setWindowTitle(f"Loyalty Points — {customer.name}")
        self.setFixedSize(500, 500)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self._init_ui()

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

        hdr_title = QLabel(f"Loyalty Points: {self._customer.name}")
        hdr_title.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: 800;")
        hdr_text_layout.addWidget(hdr_title)

        hdr_sub = QLabel(f"Manage rewards & points balance for {self._customer.phone}")
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

        # Current Balance Card
        bal_card = QFrame()
        bal_card.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 10px 14px;
            }
        """)
        bal_layout = QHBoxLayout(bal_card)
        bal_layout.setContentsMargins(0, 0, 0, 0)

        ico = QLabel()
        ico.setFixedSize(36, 36)
        ico.setAlignment(Qt.AlignCenter)
        ico.setStyleSheet("background-color: #fffbeb; border: 1px solid #fde68a; border-radius: 8px;")
        ico.setText("⭐")
        bal_layout.addWidget(ico)

        info_l = QVBoxLayout()
        info_l.setSpacing(2)
        c_lbl = QLabel(f"CURRENT BALANCE: {self._customer.loyalty_points} Points")
        c_lbl.setStyleSheet("font-size: 13px; font-weight: 800; color: #0f172a;")
        tier_lbl = QLabel(f"Current Tier: {self._customer.tier.upper()} Member")
        tier_lbl.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 600;")
        info_l.addWidget(c_lbl)
        info_l.addWidget(tier_lbl)
        bal_layout.addLayout(info_l, 1)

        body_layout.addWidget(bal_card)

        # Mode Buttons
        lbl_mode = QLabel("ADJUSTMENT TYPE")
        lbl_mode.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        body_layout.addWidget(lbl_mode)

        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(8)

        self.btn_mode_add = QPushButton(" 🎁 Add Bonus Points (+)")
        self.btn_mode_deduct = QPushButton(" 🛍️ Redeem Points (-)")

        for btn in (self.btn_mode_add, self.btn_mode_deduct):
            btn.setFixedHeight(34)
            btn.setCursor(Qt.PointingHandCursor)

        self.btn_mode_add.clicked.connect(lambda: self._set_mode("add"))
        self.btn_mode_deduct.clicked.connect(lambda: self._set_mode("deduct"))

        mode_layout.addWidget(self.btn_mode_add)
        mode_layout.addWidget(self.btn_mode_deduct)
        body_layout.addLayout(mode_layout)

        # Points Input Card
        qty_card = QFrame()
        qty_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 10px 14px;
            }
        """)
        qty_layout = QVBoxLayout(qty_card)
        qty_layout.setContentsMargins(0, 0, 0, 0)
        qty_layout.setSpacing(8)

        qty_input_row = QHBoxLayout()
        self.lbl_target = QLabel("Points to Add (+):")
        self.lbl_target.setStyleSheet("color: #0f172a; font-size: 12px; font-weight: 700;")
        qty_input_row.addWidget(self.lbl_target)

        self.spn_points = QSpinBox()
        self.spn_points.setRange(1, 99999)
        self.spn_points.setValue(100)
        self.spn_points.setFixedWidth(130)
        self.spn_points.setFixedHeight(34)
        self.spn_points.setStyleSheet("""
            QSpinBox {
                padding: 4px 8px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 700;
                color: #0f172a;
            }
            QSpinBox:focus { border-color: #2563eb; }
        """)
        self.spn_points.valueChanged.connect(self._update_preview)
        qty_input_row.addWidget(self.spn_points, alignment=Qt.AlignRight)
        qty_layout.addLayout(qty_input_row)

        # Live Preview Badge
        self.lbl_preview = QLabel("Current: 250 pts  ➔  New Total: 350 pts (+100) · Tier: Silver")
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setStyleSheet("""
            font-size: 12px;
            font-weight: 800;
            color: #047857;
            background-color: #ecfdf5;
            border: 1px solid #a7f3d0;
            border-radius: 6px;
            padding: 8px;
        """)
        qty_layout.addWidget(self.lbl_preview)
        body_layout.addWidget(qty_card)

        # Reason Input
        lbl_reason = QLabel("REASON / REFERENCE NOTE")
        lbl_reason.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        body_layout.addWidget(lbl_reason)

        self.txt_reason = QLineEdit()
        self.txt_reason.setPlaceholderText("e.g. Store anniversary bonus promo, loyalty redemption reward...")
        self.txt_reason.setFixedHeight(36)
        self.txt_reason.setStyleSheet("""
            QLineEdit {
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 13px;
                color: #0f172a;
            }
            QLineEdit:focus { border-color: #2563eb; }
        """)
        body_layout.addWidget(self.txt_reason)

        # Quick Preset Chips
        chips_l = QHBoxLayout()
        chips_l.setSpacing(6)
        for preset in ["Anniversary Promo", "Birthday Reward", "Points Redemption"]:
            p_btn = QPushButton(preset)
            p_btn.setFixedHeight(24)
            p_btn.setCursor(Qt.PointingHandCursor)
            p_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f1f5f9;
                    color: #475569;
                    border: 1px solid #e2e8f0;
                    border-radius: 12px;
                    font-size: 10px;
                    font-weight: 700;
                    padding: 0 10px;
                }
                QPushButton:hover { background-color: #e2e8f0; color: #0f172a; }
            """)
            p_btn.clicked.connect(lambda chk, t=preset: self.txt_reason.setText(t))
            chips_l.addWidget(p_btn)
        chips_l.addStretch()
        body_layout.addLayout(chips_l)

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

        btn_save = QPushButton("Save Points Adjustment")
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

        self._set_mode("add")

    def _set_mode(self, mode: str):
        self._mode = mode
        if mode == "add":
            self.lbl_target.setText("Points to Add (+):")
            self.btn_mode_add.setStyleSheet("""
                QPushButton {
                    background-color: #2563eb;
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: 800;
                }
            """)
            self.btn_mode_deduct.setStyleSheet("""
                QPushButton {
                    background-color: #ffffff;
                    color: #475569;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: 600;
                }
            """)
        else:
            self.lbl_target.setText("Points to Deduct (-):")
            self.btn_mode_deduct.setStyleSheet("""
                QPushButton {
                    background-color: #2563eb;
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: 800;
                }
            """)
            self.btn_mode_add.setStyleSheet("""
                QPushButton {
                    background-color: #ffffff;
                    color: #475569;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: 600;
                }
            """)
        self._update_preview()

    def _update_preview(self):
        val = self.spn_points.value()
        curr = self._customer.loyalty_points
        if self._mode == "add":
            target = curr + val
            delta_str = f"+{val}"
        else:
            target = max(0, curr - val)
            delta_str = f"-{val}"

        # Tier calculation
        if target >= 1000:
            tier = "Platinum"
        elif target >= 500:
            tier = "Gold"
        elif target >= 100:
            tier = "Silver"
        else:
            tier = "Bronze"

        self.lbl_preview.setText(f"Current: {curr} pts  ➔  New Total: {target} pts ({delta_str}) · Tier: {tier}")

    def _on_header_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _on_header_mouse_move(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def _on_save(self):
        val = self.spn_points.value()
        delta = val if self._mode == "add" else -val
        reason = self.txt_reason.text().strip() or ("Bonus Points" if delta > 0 else "Points Redemption")

        try:
            self._customer_service.adjust_points(
                self._customer.id,
                delta,
                reason=reason,
                actor=self._actor,
            )
            self.accept()
        except RetailFlowError as e:
            self.reject()
        except Exception:
            self.reject()
