"""
RetailFlow POS - Action Buttons Delegate
Renders Edit / Archive buttons in the actions column, respecting permissions.
"""

from PySide6.QtCore import QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate

from presentation.widgets.product_table_model import COL_ACTIONS

_EDIT_BG = QColor("#eff6ff")
_EDIT_FG = QColor("#2563eb")
_EDIT_BORDER = QColor("#bfdbfe")

_DELETE_BG = QColor("#fef2f2")
_DELETE_FG = QColor("#dc2626")
_DELETE_BORDER = QColor("#fecaca")

_BUTTON_W = 56.0
_BUTTON_H = 24.0
_GAP = 6.0


class ActionButtonsDelegate(QStyledItemDelegate):
    """Paints edit/delete buttons and forwards clicks via signals."""

    edit_requested = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, can_edit: bool = True, can_delete: bool = True, parent=None):
        super().__init__(parent)
        self.can_edit = can_edit
        self.can_delete = can_delete

    def _rects(self, rect: QRect) -> tuple[QRectF | None, QRectF | None]:
        buttons: list[QRectF] = []
        if self.can_edit:
            buttons.append(QRectF(0, 0, _BUTTON_W, _BUTTON_H))
        if self.can_delete:
            buttons.append(QRectF(0, 0, _BUTTON_W, _BUTTON_H))

        total = sum(b.width() for b in buttons) + _GAP * max(0, len(buttons) - 1)
        x = rect.x() + (rect.width() - total) / 2
        y = rect.y() + (rect.height() - _BUTTON_H) / 2

        edit_rect = None
        delete_rect = None
        for b in buttons:
            b.moveLeft(x)
            b.moveTop(y)
            x += b.width() + _GAP
        if self.can_edit and self.can_delete:
            edit_rect, delete_rect = buttons[0], buttons[1]
        elif self.can_edit:
            edit_rect = buttons[0]
        elif self.can_delete:
            delete_rect = buttons[0]
        return edit_rect, delete_rect

    def paint(self, painter, option, index):
        if index.column() != COL_ACTIONS:
            super().paint(painter, option, index)
            return

        item = index.model().item_at(index.row())
        if item is None:
            return

        edit_rect, delete_rect = self._rects(option.rect)
        if edit_rect is None and delete_rect is None:
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        font = QFont(option.font)
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)

        if edit_rect is not None:
            painter.setPen(QPen(_EDIT_BORDER, 1))
            painter.setBrush(_EDIT_BG)
            painter.drawRoundedRect(edit_rect, 6, 6)
            painter.setPen(_EDIT_FG)
            painter.drawText(edit_rect, Qt.AlignCenter, "Edit")

        if delete_rect is not None:
            painter.setPen(QPen(_DELETE_BORDER, 1))
            painter.setBrush(_DELETE_BG)
            painter.drawRoundedRect(delete_rect, 6, 6)
            painter.setPen(_DELETE_FG)
            painter.drawText(delete_rect, Qt.AlignCenter, "Delete")

        painter.restore()

    def editorEvent(self, event, model, option, index):  # noqa: N802
        if index.column() != COL_ACTIONS:
            return False
        if not isinstance(event, QMouseEvent):
            return False
        if event.type() != event.MouseButtonRelease:
            return False

        item = model.item_at(index.row())
        if item is None:
            return False

        edit_rect, delete_rect = self._rects(option.rect)
        pos = event.pos()
        if edit_rect is not None and edit_rect.contains(pos):
            self.edit_requested.emit(item.id)
            return True
        if delete_rect is not None and delete_rect.contains(pos):
            self.delete_requested.emit(item.id)
            return True
        return False
