"""
RetailFlow POS - Stock Badge Delegate
Renders high-DPI semantic stock status pill badges (In Stock / Low Stock / Out of Stock).
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate

from presentation.widgets.product_table_model import COL_STOCK

_BADGES = {
    "in_stock": (QColor("#047857"), QColor("#ecfdf5"), QColor("#a7f3d0")),
    "low_stock": (QColor("#d97706"), QColor("#fffbeb"), QColor("#fde68a")),
    "out_of_stock": (QColor("#dc2626"), QColor("#fef2f2"), QColor("#fecaca")),
}

_LABELS = {
    "in_stock": "In Stock",
    "low_stock": "Low Stock",
    "out_of_stock": "Out of Stock",
}


class StockBadgeDelegate(QStyledItemDelegate):
    """Paints a rounded pill badge for the stock column."""

    def paint(self, painter, option, index):
        if index.column() != COL_STOCK:
            super().paint(painter, option, index)
            return

        item = index.model().item_at(index.row())
        status = item.stock_status if item else "in_stock"
        quantity = item.stock_quantity if item else 0
        text_color, bg_color, border_color = _BADGES.get(status, _BADGES["in_stock"])
        label = _LABELS.get(status, "In Stock")

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        if status == "out_of_stock":
            text = "● Out of Stock"
        else:
            text = f"● {quantity} {label}"

        font = QFont(option.font)
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)

        fm = painter.fontMetrics()
        text_width = fm.horizontalAdvance(text)
        badge_w = text_width + 18
        badge_h = 22

        rect = option.rect
        x = rect.x() + (rect.width() - badge_w) / 2
        y = rect.y() + (rect.height() - badge_h) / 2
        badge_rect = QRectF(x, y, badge_w, badge_h)

        # Background & Border
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(bg_color)
        painter.drawRoundedRect(badge_rect, 11, 11)

        # Text
        painter.setPen(text_color)
        painter.drawText(badge_rect, Qt.AlignCenter, text)
        painter.restore()

    def sizeHint(self, option, index):  # noqa: N802
        return super().sizeHint(option, index)
