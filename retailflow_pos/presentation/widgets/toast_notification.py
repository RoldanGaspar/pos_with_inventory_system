"""
RetailFlow POS - Toast Notification Widget
Rock-solid auto-dismissing toast notification for cashier interaction feedback.
Eliminates graphics effect conflict bugs with clean QTimer auto-dismissal.
"""

from PySide6.QtCore import QPropertyAnimation, QTimer, Qt
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget


class ToastNotification(QLabel):
    """Auto-dismissing floating toast notification with reliable QTimer lifecycle."""

    def __init__(self, parent: QWidget, duration_ms: int = 1800):
        super().__init__(parent)
        self._duration = duration_ms
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(34)
        self.setStyleSheet("""
            QLabel {
                background-color: #0f172a;
                color: #ffffff;
                border-left: 3px solid #10b981;
                border-top: 1px solid #334155;
                border-right: 1px solid #334155;
                border-bottom: 1px solid #334155;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                padding: 4px 12px;
            }
        """)

        # Permanent opacity effect for smooth fade animations
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)

        # Single-shot timer for guaranteed auto-dismissal
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._start_fade_out)

        self._anim = None
        self.hide()

    def show_toast(self, text: str, is_error: bool = False):
        """Display a toast message with success/error theme."""
        if is_error:
            self.setStyleSheet("""
                QLabel {
                    background-color: #7f1d1d;
                    color: #ffffff;
                    border-left: 3px solid #ef4444;
                    border-top: 1px solid #991b1b;
                    border-right: 1px solid #991b1b;
                    border-bottom: 1px solid #991b1b;
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: 700;
                    padding: 4px 12px;
                }
            """)
        else:
            self.setStyleSheet("""
                QLabel {
                    background-color: #0f172a;
                    color: #ffffff;
                    border-left: 3px solid #10b981;
                    border-top: 1px solid #334155;
                    border-right: 1px solid #334155;
                    border-bottom: 1px solid #334155;
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: 700;
                    padding: 4px 12px;
                }
            """)
        self.show_message(text)

    def show_message(self, text: str):
        """Display a toast message and start single-shot auto-dismiss timer."""
        # Stop existing timers/animations if user clicks rapidly
        self._timer.stop()
        if self._anim:
            self._anim.stop()

        self.setText(text)
        self._opacity.setOpacity(1.0)

        # Position floating cleanly below the cart header bar (y=40)
        if self.parent():
            parent_w = self.parent().width()
            toast_w = min(parent_w - 24, 330)
            self.setFixedWidth(toast_w)
            x = (parent_w - toast_w) // 2
            self.move(x, 40)

        self.raise_()
        self.show()

        # Start timer for auto-dismissal
        self._timer.start(self._duration)

    def _start_fade_out(self):
        """Fade out opacity gracefully then hide."""
        self._anim = QPropertyAnimation(self._opacity, b"opacity")
        self._anim.setDuration(250)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self.hide)
        self._anim.start()
