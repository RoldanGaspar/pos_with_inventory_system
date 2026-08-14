"""
RetailFlow POS - Product Table Model
QAbstractTableModel for the product catalog table.
"""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from application.dto.product_dto import ProductListItemDTO
from shared.date_time import format_currency

COL_BARCODE = 0
COL_PRODUCT = 1
COL_CATEGORY = 2
COL_COST = 3
COL_PRICE = 4
COL_STOCK = 5
COL_ACTIONS = 6

HEADERS = ["Barcode", "Product", "Category", "Cost", "Price", "Stock", "Actions"]

_ALIGN_RIGHT = (COL_COST, COL_PRICE)
_ALIGN_CENTER = (COL_STOCK, COL_ACTIONS)


class ProductTableModel(QAbstractTableModel):
    """Table model backed by a list of ProductListItemDTO."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[ProductListItemDTO] = []

    def set_items(self, items: list[ProductListItemDTO]) -> None:
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def item_at(self, row: int) -> ProductListItemDTO | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802, B008
        if parent.isValid():
            return 0
        return len(self._items)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802, B008
        if parent.isValid():
            return 0
        return len(HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        item = self.item_at(index.row())
        if item is None:
            return None
        col = index.column()

        if role == Qt.DisplayRole:
            return self._display_text(item, col)
        if role == Qt.ToolTipRole and col == COL_PRODUCT:
            return f"{item.name} ({item.sku})"
        if role == Qt.TextAlignmentRole:
            if col in _ALIGN_RIGHT:
                return int(Qt.AlignRight | Qt.AlignVCenter)
            if col in _ALIGN_CENTER:
                return int(Qt.AlignCenter)
        return None

    def _display_text(self, item: ProductListItemDTO, col: int) -> str:
        if col == COL_BARCODE:
            return item.barcode
        if col == COL_PRODUCT:
            return item.name
        if col == COL_CATEGORY:
            return item.category_name
        if col == COL_COST:
            return format_currency(float(item.cost_price))
        if col == COL_PRICE:
            return format_currency(float(item.selling_price))
        if col == COL_STOCK:
            return str(item.stock_quantity)
        if col == COL_ACTIONS:
            return ""
        return ""
