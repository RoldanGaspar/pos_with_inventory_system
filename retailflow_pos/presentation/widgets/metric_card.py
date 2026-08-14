"""
RetailFlow POS - Metric Card Widget
Minimalist stat card with soft vector icon badge, clear title, large value count, and status caption.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout
from presentation.styles.icons import IconManager


class MetricCardWidget(QFrame):
    """A clean, minimalist stat card with soft icon badge, title, large value, and status caption."""

    def __init__(
        self,
        title: str,
        icon_name: str = "products",
        accent_color: str = "#2563eb",
        badge_bg: str = "#eff6ff",
        parent=None,
    ):
        super().__init__(parent)
        self._title = title
        self._accent_color = accent_color
        self._badge_bg = badge_bg

        self.setObjectName("metricCard")
        self.setStyleSheet("""
            QFrame#metricCard {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
            QFrame#metricCard:hover {
                border-color: #cbd5e1;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        # ── Top Row: Title Label (Left) + Soft Icon Badge (Right) ──
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("metricCardTitle")
        self._title_label.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 700; letter-spacing: 0.5px;")
        top_row.addWidget(self._title_label, stretch=1)

        # Soft Icon Badge Container (36x36px rounded 10px)
        self._icon_badge = QLabel()
        self._icon_badge.setFixedSize(36, 36)
        self._icon_badge.setAlignment(Qt.AlignCenter)
        self._icon_badge.setStyleSheet(f"""
            QLabel {{
                background-color: {badge_bg};
                border-radius: 10px;
                border: none;
            }}
        """)
        icon_pixmap = IconManager.get_icon(icon_name, color=accent_color, size=18).pixmap(QSize(18, 18))
        self._icon_badge.setPixmap(icon_pixmap)
        top_row.addWidget(self._icon_badge)

        layout.addLayout(top_row)

        # ── Middle Row: Value Label (26px Bold Count) ──
        self._value_label = QLabel("0")
        self._value_label.setObjectName("metricCardValue")
        self._value_label.setStyleSheet(f"color: {accent_color}; font-size: 26px; font-weight: 800; letter-spacing: -0.5px;")
        layout.addWidget(self._value_label)

        # ── Bottom Row: Caption / Status Sub-indicator ──
        self._caption_label = QLabel("")
        self._caption_label.setObjectName("metricCardCaption")
        self._caption_label.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 500;")
        self._caption_label.setVisible(False)
        layout.addWidget(self._caption_label)

    def set_value(self, value: str) -> None:
        self._value_label.setText(value)

    def update_value(self, value: str) -> None:
        self._value_label.setText(value)

    def set_caption(self, caption: str) -> None:
        self._caption_label.setText(caption)
        self._caption_label.setVisible(bool(caption))
