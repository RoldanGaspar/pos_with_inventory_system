"""
RetailFlow POS - Products Catalog Management Page
Full product catalog workstation: live KPI metrics, multi-filter search toolbar,
quick status filter chips, high-DPI stock & action delegates, and pagination controls.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from application.dto.product_dto import ProductFilterDTO
from application.services.product_service import ProductService
from domain.exceptions import RetailFlowError
from infrastructure.database.models.auth import User
from presentation.dialogs.product_form_dialog import ProductFormDialog
from presentation.styles.icons import IconManager
from presentation.widgets.action_buttons_delegate import ActionButtonsDelegate
from presentation.widgets.metric_card import MetricCardWidget
from presentation.widgets.product_table_model import (
    COL_ACTIONS,
    COL_STOCK,
    ProductTableModel,
)
from presentation.widgets.stock_badge_delegate import StockBadgeDelegate


class ProductsPage(QWidget):
    """Product catalog page embedded in the main window."""

    def __init__(self, current_user: User, service: ProductService, parent=None):
        super().__init__(parent)
        self._user = current_user
        self._service = service

        self._page = 1
        self._page_size = 20
        self._total = 0
        self._keyword = ""
        self._category_id = None
        self._status = None
        self._active_filter_chip = "all"

        self._can_view = self._has_permission("view_products")
        self._can_create = self._has_permission("create_products")
        self._can_edit = self._has_permission("edit_products")
        self._can_delete = self._has_permission("delete_products")

        self._init_ui()
        self._init_shortcuts()
        if self._can_view:
            self._load_options()
            self.reload()
        else:
            self._show_access_denied()

    # ─── Permissions ───

    def _has_permission(self, code: str) -> bool:
        return bool(self._user and self._user.has_permission(code))

    # ─── UI Initialization ───

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        layout.addLayout(self._build_header())
        layout.addLayout(self._build_metrics())
        layout.addWidget(self._build_toolbar())

        self._error_banner = QFrame()
        self._error_banner.setObjectName("errorBanner")
        self._error_banner.setStyleSheet("""
            QFrame#errorBanner {
                background-color: #fef2f2;
                border: 1px solid #fca5a5;
                border-radius: 8px;
                padding: 6px 12px;
            }
        """)
        error_layout = QHBoxLayout(self._error_banner)
        error_layout.setContentsMargins(0, 0, 0, 0)
        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: #dc2626; font-size: 12px; font-weight: 600;")
        self._error_label.setWordWrap(True)
        error_layout.addWidget(self._error_label)
        retry_btn = QPushButton("Retry")
        retry_btn.setObjectName("secondaryButton")
        retry_btn.setCursor(Qt.PointingHandCursor)
        retry_btn.clicked.connect(self.reload)
        error_layout.addWidget(retry_btn)
        self._error_banner.setVisible(False)
        layout.addWidget(self._error_banner)

        layout.addWidget(self._build_table_stack(), 1)
        layout.addLayout(self._build_footer())

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        title_group = QVBoxLayout()
        title_group.setSpacing(2)
        title = QLabel("Product Catalog")
        title.setObjectName("pageHeaderTitle")
        title.setStyleSheet("font-size: 22px; font-weight: 800; color: #0f172a; letter-spacing: -0.4px;")
        subtitle = QLabel("Manage products, pricing margins, inventory stock, and barcodes")
        subtitle.setObjectName("pageHeaderSubtitle")
        subtitle.setStyleSheet("font-size: 13px; font-weight: 500; color: #64748b;")
        title_group.addWidget(title)
        title_group.addWidget(subtitle)
        header.addLayout(title_group)
        header.addStretch()

        self._add_btn = QPushButton(" + Add Product")
        self._add_btn.setIcon(IconManager.get_pixmap("plus", color="#ffffff", size=14))
        self._add_btn.setObjectName("primaryButton")
        self._add_btn.setFixedHeight(38)
        self._add_btn.setCursor(Qt.PointingHandCursor)
        self._add_btn.setStyleSheet("""
            QPushButton#primaryButton {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 800;
                padding: 0 16px;
            }
            QPushButton#primaryButton:hover {
                background-color: #1d4ed8;
            }
        """)
        self._add_btn.setVisible(self._can_create)
        self._add_btn.clicked.connect(self._open_add)
        header.addWidget(self._add_btn)
        return header

    def _build_metrics(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        self._total_card = MetricCardWidget("Total Products", icon_name="products", accent_color="#2563eb", badge_bg="#eff6ff")
        self._total_card.set_caption("● Active catalog items")

        self._low_card = MetricCardWidget("Low Stock", icon_name="alert_triangle", accent_color="#d97706", badge_bg="#fffbeb")
        self._low_card.set_caption("● Reorder recommended")

        self._out_card = MetricCardWidget("Out of Stock", icon_name="alert_circle", accent_color="#dc2626", badge_bg="#fef2f2")
        self._out_card.set_caption("● Stock levels normal")

        self._cat_card = MetricCardWidget("Categories", icon_name="grid_category", accent_color="#059669", badge_bg="#ecfdf5")
        self._cat_card.set_caption("● Product classifications")

        for card in (self._total_card, self._low_card, self._out_card, self._cat_card):
            row.addWidget(card)
        return row

    def _build_toolbar(self) -> QFrame:
        toolbar = QFrame()
        toolbar.setObjectName("filterToolbar")
        toolbar.setStyleSheet("""
            QFrame#filterToolbar {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 10px 14px;
            }
        """)
        v_layout = QVBoxLayout(toolbar)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.setSpacing(8)

        # Top search row
        layout = QHBoxLayout()
        layout.setSpacing(10)

        self._search = QLineEdit()
        self._search.addAction(IconManager.get_icon("search", color="#64748b", size=16), QLineEdit.LeadingPosition)
        self._search.setObjectName("searchInput")
        self._search.setPlaceholderText("Search barcode, SKU, or product name... · F3")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedHeight(36)
        self._search.setStyleSheet("""
            QLineEdit#searchInput {
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background-color: #ffffff;
                font-size: 13px;
                color: #0f172a;
            }
            QLineEdit#searchInput:focus { border-color: #2563eb; }
        """)
        layout.addWidget(self._search, 3)

        self._category_combo = QComboBox()
        self._category_combo.setObjectName("categoryFilter")
        self._category_combo.setFixedHeight(36)
        self._category_combo.setStyleSheet("""
            QComboBox {
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background-color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                color: #0f172a;
            }
            QComboBox:focus { border-color: #2563eb; }
        """)
        layout.addWidget(self._category_combo, 2)

        self._status_combo = QComboBox()
        self._status_combo.setFixedHeight(36)
        self._status_combo.setStyleSheet("""
            QComboBox {
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background-color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                color: #0f172a;
            }
            QComboBox:focus { border-color: #2563eb; }
        """)
        self._status_combo.addItem("All Statuses", None)
        self._status_combo.addItem("Active", "active")
        self._status_combo.addItem("Inactive", "inactive")
        self._status_combo.addItem("Archived", "archived")
        layout.addWidget(self._status_combo, 1)

        self._reset_btn = QPushButton("Reset")
        self._reset_btn.setObjectName("secondaryButton")
        self._reset_btn.setFixedHeight(36)
        self._reset_btn.setCursor(Qt.PointingHandCursor)
        self._reset_btn.setStyleSheet("""
            QPushButton#secondaryButton {
                background-color: #f1f5f9;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 700;
                padding: 0 14px;
            }
            QPushButton#secondaryButton:hover { background-color: #e2e8f0; color: #0f172a; }
        """)
        layout.addWidget(self._reset_btn)
        v_layout.addLayout(layout)

        # Quick Status Filter Chips Row
        chips_layout = QHBoxLayout()
        chips_layout.setSpacing(6)

        self.chip_all = QPushButton("All Items")
        self.chip_active = QPushButton("Active")
        self.chip_archived = QPushButton("Archived")

        self.filter_chips = [
            (self.chip_all, "all", None),
            (self.chip_active, "active", "active"),
            (self.chip_archived, "archived", "archived"),
        ]

        for chip_btn, mode, status_val in self.filter_chips:
            chip_btn.setFixedHeight(26)
            chip_btn.setCursor(Qt.PointingHandCursor)
            chip_btn.clicked.connect(lambda chk, m=mode, s=status_val: self._on_chip_clicked(m, s))
            chips_layout.addWidget(chip_btn)

        chips_layout.addStretch()
        v_layout.addLayout(chips_layout)
        self._update_chip_styles()

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._apply_search)

        self._search.textChanged.connect(lambda _: self._debounce.start())
        self._search.returnPressed.connect(self._on_search_submit)
        self._category_combo.currentIndexChanged.connect(self._on_category_changed)
        self._status_combo.currentIndexChanged.connect(self._on_status_changed)
        self._reset_btn.clicked.connect(self._reset_filters)

        return toolbar

    def _on_chip_clicked(self, mode: str, status_val: str | None):
        self._active_filter_chip = mode
        self._update_chip_styles()
        self._set_combo_by_data(self._status_combo, status_val)
        self._status = status_val
        self._page = 1
        self._load_products()

    def _update_chip_styles(self):
        for chip_btn, mode, _ in self.filter_chips:
            is_active = self._active_filter_chip == mode
            if is_active:
                chip_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2563eb;
                        color: #ffffff;
                        border: none;
                        border-radius: 13px;
                        font-size: 11px;
                        font-weight: 700;
                        padding: 0 12px;
                    }
                """)
            else:
                chip_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f1f5f9;
                        color: #475569;
                        border: 1px solid #e2e8f0;
                        border-radius: 13px;
                        font-size: 11px;
                        font-weight: 600;
                        padding: 0 12px;
                    }
                    QPushButton:hover { background-color: #e2e8f0; color: #0f172a; }
                """)

    def _set_combo_by_data(self, combo: QComboBox, val):
        combo.blockSignals(True)
        if val is None:
            combo.setCurrentIndex(0)
        else:
            for i in range(combo.count()):
                if combo.itemData(i) == val:
                    combo.setCurrentIndex(i)
                    break
        combo.blockSignals(False)

    def _build_table_stack(self) -> QStackedWidget:
        self._stack = QStackedWidget()

        # Empty State Card
        empty_card = QFrame()
        empty_card.setStyleSheet("background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px;")
        empty_layout = QVBoxLayout(empty_card)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_layout.setSpacing(8)

        empty_icon = QLabel()
        empty_icon.setPixmap(IconManager.get_pixmap("products", color="#cbd5e1", size=44))
        empty_icon.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_icon)

        self._empty_label = QLabel("No products found.")
        self._empty_label.setObjectName("stateLabel")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet("color: #0f172a; font-size: 14px; font-weight: 700; border: none; background: transparent;")
        empty_layout.addWidget(self._empty_label)

        empty_sub = QLabel("Try adjusting your search filters or add a new product.")
        empty_sub.setAlignment(Qt.AlignCenter)
        empty_sub.setStyleSheet("color: #64748b; font-size: 12px; border: none; background: transparent;")
        empty_layout.addWidget(empty_sub)

        self._stack.addWidget(empty_card)

        self._table = QTableView()
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(46)
        self._table.setAlternatingRowColors(False)
        self._table.setStyleSheet("""
            QTableView {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                font-size: 13px;
                color: #0f172a;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #64748b;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.8px;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                padding: 8px 12px;
            }
            QTableView::item {
                padding: 4px 8px;
                border-bottom: 1px solid #f1f5f9;
            }
            QTableView::item:selected {
                background-color: #eff6ff;
                color: #0f172a;
            }
        """)

        self._model = ProductTableModel(self._table)
        self._table.setModel(self._model)

        self._stock_delegate = StockBadgeDelegate(self._table)
        self._table.setItemDelegateForColumn(COL_STOCK, self._stock_delegate)

        self._action_delegate = ActionButtonsDelegate(
            can_edit=self._can_edit, can_delete=self._can_delete, parent=self._table
        )
        self._table.setItemDelegateForColumn(COL_ACTIONS, self._action_delegate)
        self._action_delegate.edit_requested.connect(self._open_edit)
        self._action_delegate.delete_requested.connect(self._archive_product)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col, width in ((0, 140), (2, 120), (3, 100), (4, 100), (5, 130), (6, 140)):
            self._table.setColumnWidth(col, width)

        self._stack.addWidget(self._table)
        return self._stack

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        self._range_label = QLabel("")
        self._range_label.setObjectName("paginationInfo")
        self._range_label.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 600;")
        footer.addWidget(self._range_label)
        footer.addStretch()

        lbl_rows = QLabel("Rows per page:")
        lbl_rows.setObjectName("rowsPerPageLabel")
        lbl_rows.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 600;")
        footer.addWidget(lbl_rows)

        self._rows_combo = QComboBox()
        self._rows_combo.setFixedHeight(30)
        self._rows_combo.setStyleSheet("""
            QComboBox {
                padding: 2px 8px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background-color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                color: #0f172a;
            }
        """)
        for n in (10, 20, 50, 100):
            self._rows_combo.addItem(str(n), n)
        self._rows_combo.setCurrentText(str(self._page_size))
        footer.addWidget(self._rows_combo)

        self._prev_btn = QPushButton("‹ Previous")
        self._prev_btn.setObjectName("secondaryButton")
        self._prev_btn.setFixedHeight(30)
        self._prev_btn.setCursor(Qt.PointingHandCursor)
        self._prev_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                padding: 0 12px;
            }
            QPushButton:hover { background-color: #f1f5f9; color: #0f172a; }
            QPushButton:disabled { color: #cbd5e1; border-color: #e2e8f0; }
        """)
        footer.addWidget(self._prev_btn)

        self._next_btn = QPushButton("Next ›")
        self._next_btn.setObjectName("secondaryButton")
        self._next_btn.setFixedHeight(30)
        self._next_btn.setCursor(Qt.PointingHandCursor)
        self._next_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                padding: 0 12px;
            }
            QPushButton:hover { background-color: #f1f5f9; color: #0f172a; }
            QPushButton:disabled { color: #cbd5e1; border-color: #e2e8f0; }
        """)
        footer.addWidget(self._next_btn)

        self._rows_combo.currentIndexChanged.connect(self._on_rows_changed)
        self._prev_btn.clicked.connect(self._prev_page)
        self._next_btn.clicked.connect(self._next_page)
        return footer

    def _init_shortcuts(self) -> None:
        focus = QShortcut(QKeySequence("F3"), self)
        focus.activated.connect(self._focus_search)
        focus_ctrl = QShortcut(QKeySequence("Ctrl+F"), self)
        focus_ctrl.activated.connect(self._focus_search)
        if self._can_create:
            add = QShortcut(QKeySequence("Ctrl+N"), self)
            add.activated.connect(self._open_add)
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.setContext(Qt.ShortcutContext.WidgetShortcut)
        esc.activated.connect(self._clear_search)

    # ─── Data loading ───

    def _load_options(self) -> None:
        options = self._service.get_form_options(self._user)
        self._category_combo.blockSignals(True)
        self._category_combo.clear()
        self._category_combo.addItem("All Categories", None)
        for c in options.categories:
            self._category_combo.addItem(c.name, c.id)
        self._category_combo.blockSignals(False)

    def reload(self) -> None:
        self._show_error(None)
        self._load_metrics()
        self._load_products()

    def _load_metrics(self) -> None:
        try:
            metrics = self._service.get_metrics(self._user)
            self._total_card.set_value(str(metrics.total_products))
            self._total_card.set_caption("● Active catalog items")

            self._low_card.set_value(str(metrics.low_stock))
            if metrics.low_stock > 0:
                self._low_card.set_caption(f"● {metrics.low_stock} items need reorder")
            else:
                self._low_card.set_caption("● Stock levels healthy")

            self._out_card.set_value(str(metrics.out_of_stock))
            if metrics.out_of_stock > 0:
                self._out_card.set_caption(f"● {metrics.out_of_stock} out of stock")
            else:
                self._out_card.set_caption("● No out of stock items")

            self._cat_card.set_value(str(metrics.categories))
            self._cat_card.set_caption("● Product classifications")
        except RetailFlowError as e:
            self._show_error(str(e))

    def _load_products(self) -> None:
        try:
            filters = ProductFilterDTO(
                keyword=self._keyword or None,
                category_id=self._category_id,
                status=self._status,
                page=self._page,
                page_size=self._page_size,
            )
            result = self._service.search(filters, self._user)
            self._total = result.total
            self._model.set_items(result.items)

            if result.total == 0:
                self._empty_label.setText("No products found.")
                self._stack.setCurrentIndex(0)
            else:
                self._stack.setCurrentIndex(1)

            self._update_footer(result)
        except RetailFlowError as e:
            self._show_error(str(e))
            self._model.set_items([])
            self._stack.setCurrentIndex(1)

    def _update_footer(self, result) -> None:
        start = (result.page - 1) * result.page_size + 1 if result.total else 0
        end = min(result.page * result.page_size, result.total)
        self._range_label.setText(f"Showing {start}–{end} of {result.total} products")
        self._prev_btn.setEnabled(result.has_previous)
        self._next_btn.setEnabled(result.has_next)

    # ─── Filter handling ───

    def _apply_search(self) -> None:
        self._debounce.stop()
        self._keyword = self._search.text().strip()
        self._page = 1
        self._load_products()

    def _on_search_submit(self) -> None:
        self._apply_search()

    def _on_category_changed(self) -> None:
        self._category_id = self._category_combo.currentData()
        self._page = 1
        self._load_products()

    def _on_status_changed(self) -> None:
        self._status = self._status_combo.currentData()
        # Sync chip state
        if self._status == "active":
            self._active_filter_chip = "active"
        elif self._status == "archived":
            self._active_filter_chip = "archived"
        else:
            self._active_filter_chip = "all"
        self._update_chip_styles()

        self._page = 1
        self._load_products()

    def _reset_filters(self) -> None:
        self._search.blockSignals(True)
        self._search.clear()
        self._search.blockSignals(False)
        self._keyword = ""
        self._category_combo.setCurrentIndex(0)
        self._status_combo.setCurrentIndex(0)
        self._active_filter_chip = "all"
        self._update_chip_styles()
        self._page = 1
        self._load_products()

    def _on_rows_changed(self) -> None:
        self._page_size = self._rows_combo.currentData()
        self._page = 1
        self._load_products()

    # ─── Pagination ───

    def _prev_page(self) -> None:
        if self._page > 1:
            self._page -= 1
            self._load_products()

    def _next_page(self) -> None:
        if self._page * self._page_size < self._total:
            self._page += 1
            self._load_products()

    # ─── Shortcut targets ───

    def _focus_search(self) -> None:
        self._search.setFocus()
        self._search.selectAll()

    def _clear_search(self) -> None:
        if self._search.hasFocus():
            self._search.clear()

    # ─── Actions ───

    def _show_access_denied(self) -> None:
        self._empty_label.setText("You do not have permission to view products.")
        self._stack.setCurrentIndex(0)

    def _open_add(self) -> None:
        dialog = ProductFormDialog(self._service, self._user, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def _open_edit(self, product_id: int) -> None:
        try:
            product = self._service.get_product(product_id, self._user)
        except RetailFlowError as e:
            self._show_error(str(e))
            return
        dialog = ProductFormDialog(self._service, self._user, product=product, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def _archive_product(self, product_id: int) -> None:
        product = self._model.item_at(self._row_for_id(product_id))
        name = product.name if product else "this product"
        answer = QMessageBox.question(
            self,
            "Archive Product",
            f"Archive '{name}'? It will be hidden from the catalog but preserved for history.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service.archive(product_id, self._user)
            self.reload()
        except RetailFlowError as e:
            self._show_error(str(e))

    def _row_for_id(self, product_id: int) -> int:
        for row in range(self._model.rowCount()):
            item = self._model.item_at(row)
            if item is not None and item.id == product_id:
                return row
        return -1

    def _show_error(self, message: str | None) -> None:
        if message:
            self._error_label.setText(message)
            self._error_banner.setVisible(True)
        else:
            self._error_banner.setVisible(False)
