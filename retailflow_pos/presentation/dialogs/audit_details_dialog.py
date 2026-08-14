"""
RetailFlow POS - Audit Details & Diff Inspection Dialog
Frameless modal displaying complete metadata and side-by-side previous vs new state comparisons.
"""

from typing import Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from application.dto.audit_dto import AuditLogResponseDTO
from presentation.styles.icons import IconManager


class AuditDetailsDialog(QDialog):
    """Modal for inspecting detailed audit event record and state diffs."""

    def __init__(
        self,
        audit_log: AuditLogResponseDTO,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._log = audit_log
        self._drag_pos = QPoint()

        self.setWindowTitle(f"Audit Record — #{audit_log.id}")
        self.setFixedSize(540, 580)
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

        hdr_title = QLabel(f"Audit Event #{self._log.id}: {self._log.action}")
        hdr_title.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: 800;")
        hdr_text_layout.addWidget(hdr_title)

        hdr_sub = QLabel(f"Recorded on {self._log.formatted_time}")
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
        body_layout.setContentsMargins(18, 14, 18, 14)
        body_layout.setSpacing(12)

        # Metadata Card
        meta_card = QFrame()
        meta_card.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 12px 14px;
            }
        """)
        meta_layout = QVBoxLayout(meta_card)
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(6)

        def make_meta_row(lbl1, val1, lbl2, val2):
            row = QHBoxLayout()
            col1 = QHBoxLayout()
            l1 = QLabel(lbl1)
            l1.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 600;")
            v1 = QLabel(val1)
            v1.setStyleSheet("color: #0f172a; font-size: 11px; font-weight: 800;")
            col1.addWidget(l1)
            col1.addWidget(v1)
            col1.addStretch()

            col2 = QHBoxLayout()
            l2 = QLabel(lbl2)
            l2.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 600;")
            v2 = QLabel(val2)
            v2.setStyleSheet("color: #0f172a; font-size: 11px; font-weight: 800;")
            col2.addWidget(l2)
            col2.addWidget(v2)
            col2.addStretch()

            row.addLayout(col1, 1)
            row.addLayout(col2, 1)
            return row

        meta_layout.addLayout(make_meta_row("Actor User:", f"@{self._log.username}", "Module:", self._log.module.upper()))
        meta_layout.addLayout(make_meta_row("IP Address:", self._log.ip_address or "127.0.0.1", "Status:", self._log.status.upper()))
        if self._log.record_type:
            meta_layout.addLayout(make_meta_row("Record Type:", str(self._log.record_type), "Record ID:", str(self._log.record_id or "N/A")))

        body_layout.addWidget(meta_card)

        # State Difference Cards (Previous Value vs New Value)
        diff_lbl = QLabel("STATE CHANGE & AUDIT LOG DETAILS")
        diff_lbl.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
        body_layout.addWidget(diff_lbl)

        # Previous Value Box
        prev_box = QFrame()
        prev_box.setStyleSheet("""
            QFrame {
                background-color: #fef2f2;
                border: 1px solid #fecaca;
                border-radius: 8px;
                padding: 8px 12px;
            }
        """)
        prev_layout = QVBoxLayout(prev_box)
        prev_layout.setContentsMargins(0, 0, 0, 0)
        prev_layout.setSpacing(4)
        prev_title = QLabel("PREVIOUS STATE (BEFORE)")
        prev_title.setStyleSheet("font-size: 9px; font-weight: 800; color: #dc2626; letter-spacing: 0.5px;")
        prev_layout.addWidget(prev_title)

        prev_val_txt = QLabel(self._log.previous_value or "No previous record state (Initial creation or event)")
        prev_val_txt.setWordWrap(True)
        prev_val_txt.setStyleSheet("font-size: 11px; color: #991b1b; font-family: 'Consolas', monospace;")
        prev_layout.addWidget(prev_val_txt)
        body_layout.addWidget(prev_box)

        # New Value Box
        new_box = QFrame()
        new_box.setStyleSheet("""
            QFrame {
                background-color: #ecfdf5;
                border: 1px solid #a7f3d0;
                border-radius: 8px;
                padding: 8px 12px;
            }
        """)
        new_layout = QVBoxLayout(new_box)
        new_layout.setContentsMargins(0, 0, 0, 0)
        new_layout.setSpacing(4)
        new_title = QLabel("NEW STATE (AFTER)")
        new_title.setStyleSheet("font-size: 9px; font-weight: 800; color: #047857; letter-spacing: 0.5px;")
        new_layout.addWidget(new_title)

        new_val_txt = QLabel(self._log.new_value or "No state payload recorded")
        new_val_txt.setWordWrap(True)
        new_val_txt.setStyleSheet("font-size: 11px; color: #065f46; font-family: 'Consolas', monospace;")
        new_layout.addWidget(new_val_txt)
        body_layout.addWidget(new_box)

        # Reason / Context Notes
        if self._log.reason:
            r_lbl = QLabel(f"Note / Reason: {self._log.reason}")
            r_lbl.setStyleSheet("font-size: 11px; color: #475569; font-style: italic;")
            body_layout.addWidget(r_lbl)

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
        footer_layout.addStretch()

        btn_close_ft = QPushButton("Close")
        btn_close_ft.setFixedHeight(34)
        btn_close_ft.setFixedWidth(80)
        btn_close_ft.setCursor(Qt.PointingHandCursor)
        btn_close_ft.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover { background-color: #f1f5f9; color: #0f172a; }
        """)
        btn_close_ft.clicked.connect(self.accept)
        footer_layout.addWidget(btn_close_ft)

        container_layout.addWidget(footer_card)

    def _on_header_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _on_header_mouse_move(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
