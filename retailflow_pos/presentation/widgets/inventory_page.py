"""
RetailFlow POS - Inventory Management Page
Real-time stock level monitoring, low stock alert filtering, category search,
quick status filter chips, and interactive stock adjustment workflows.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from application.dto.product_dto import ProductFilterDTO
from application.services.product_service import ProductService
from domain.rules.stock_rules import stock_status
from infrastructure.database.models.auth import User
from infrastructure.database.models.product import Product
from presentation.dialogs.stock_adjustment_dialog import StockAdjustmentDialog
from presentation.styles.icons import IconManager
from presentation.widgets.metric_card import MetricCardWidget
from presentation.widgets.toast_notification import ToastNotification


class InventoryPage(QWidget):
    """Inventory Management & Stock Level Monitoring Page."""

    def __init__(
        self,
        current_user: User,
        product_service: ProductService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._user = current_user
        self._product_service = product_service
        self._products_list: list[Product] = []
        self._active_filter_chip = "all"

        self._init_ui()
        self.load_inventory()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Toast notification overlay
        self._toast = ToastNotification(self)

        # 1. Header Title & Actions
        hdr_row = QHBoxLayout()
        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)
        title_lbl = QLabel("Inventory & Stock Level Management")
        title_lbl.setStyleSheet("font-size: 22px; font-weight: 800; color: #0f172a; letter-spacing: -0.4px;")
        header_layout.addWidget(title_lbl)

        subtitle_lbl = QLabel("Monitor real-time stock levels, filter low stock alerts, and execute stock adjustments.")
        subtitle_lbl.setStyleSheet("font-size: 13px; color: #64748b; font-weight: 500;")
        header_layout.addWidget(subtitle_lbl)
        hdr_row.addLayout(header_layout)
        hdr_row.addStretch()

        btn_refresh = QPushButton(" Refresh Data")
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
        btn_refresh.clicked.connect(self.load_inventory)
        hdr_row.addWidget(btn_refresh)
        main_layout.addLayout(hdr_row)

        # 2. Summary Metric Stat Cards
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(12)

        self.card_total = MetricCardWidget(
            title="TOTAL ITEMS",
            icon_name="products",
            accent_color="#2563eb",
            badge_bg="#eff6ff",
        )
        self.card_in_stock = MetricCardWidget(
            title="IN STOCK ITEMS",
            icon_name="check",
            accent_color="#059669",
            badge_bg="#ecfdf5",
        )
        self.card_low_stock = MetricCardWidget(
            title="LOW STOCK ALERTS",
            icon_name="alert_triangle",
            accent_color="#d97706",
            badge_bg="#fffbeb",
        )
        self.card_out_of_stock = MetricCardWidget(
            title="OUT OF STOCK",
            icon_name="alert_circle",
            accent_color="#dc2626",
            badge_bg="#fef2f2",
        )

        for card in [self.card_total, self.card_in_stock, self.card_low_stock, self.card_out_of_stock]:
            metrics_layout.addWidget(card)

        main_layout.addLayout(metrics_layout)

        # 3. Search & Stock Status Filter Toolbar
        toolbar_card = QFrame()
        toolbar_card.setObjectName("filterToolbar")
        toolbar_card.setStyleSheet("""
            QFrame#filterToolbar {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 10px 14px;
            }
        """)
        v_toolbar = QVBoxLayout(toolbar_card)
        v_toolbar.setContentsMargins(0, 0, 0, 0)
        v_toolbar.setSpacing(8)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(10)

        self.txt_search = QLineEdit()
        self.txt_search.addAction(IconManager.get_icon("search", color="#64748b", size=16), QLineEdit.LeadingPosition)
        self.txt_search.setPlaceholderText("Search inventory by product name or SKU...")
        self.txt_search.setFixedHeight(36)
        self.txt_search.setStyleSheet("""
            QLineEdit {
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background-color: #ffffff;
                font-size: 13px;
                color: #0f172a;
            }
            QLineEdit:focus { border-color: #2563eb; }
        """)
        self.txt_search.textChanged.connect(self.load_inventory)
        toolbar_layout.addWidget(self.txt_search, stretch=3)

        self.cmb_stock_filter = QComboBox()
        self.cmb_stock_filter.addItems([
            "All Inventory",
            "Low Stock Alert",
            "Out of Stock",
            "In Stock",
        ])
        self.cmb_stock_filter.setFixedHeight(36)
        self.cmb_stock_filter.setStyleSheet("""
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
        self.cmb_stock_filter.currentIndexChanged.connect(self._on_stock_combo_changed)
        toolbar_layout.addWidget(self.cmb_stock_filter, stretch=1)

        self.cmb_category = QComboBox()
        self.cmb_category.addItem("All Categories", None)
        self.cmb_category.setFixedHeight(36)
        self.cmb_category.setStyleSheet("""
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
        self.cmb_category.currentIndexChanged.connect(self.load_inventory)
        toolbar_layout.addWidget(self.cmb_category, stretch=1)

        v_toolbar.addLayout(toolbar_layout)

        # Fast Filter Chips
        chips_layout = QHBoxLayout()
        chips_layout.setSpacing(6)

        self.chip_all = QPushButton("All Inventory")
        self.chip_in_stock = QPushButton("In Stock")
        self.chip_low = QPushButton("Low Stock Alert")
        self.chip_out = QPushButton("Out of Stock")

        self.stock_chips = [
            (self.chip_all, "all", "All Inventory"),
            (self.chip_in_stock, "in_stock", "In Stock"),
            (self.chip_low, "low_stock", "Low Stock Alert"),
            (self.chip_out, "out_of_stock", "Out of Stock"),
        ]

        for chip_btn, mode, combo_text in self.stock_chips:
            chip_btn.setFixedHeight(26)
            chip_btn.setCursor(Qt.PointingHandCursor)
            chip_btn.clicked.connect(lambda chk, m=mode, t=combo_text: self._on_chip_clicked(m, t))
            chips_layout.addWidget(chip_btn)

        chips_layout.addStretch()
        v_toolbar.addLayout(chips_layout)
        self._update_chip_styles()

        main_layout.addWidget(toolbar_card)

        # 4. Inventory Table Grid
        self.tbl_inventory = QTableWidget()
        self.tbl_inventory.setColumnCount(7)
        self.tbl_inventory.setHorizontalHeaderLabels([
            "SKU",
            "PRODUCT NAME",
            "CATEGORY",
            "REORDER LEVEL",
            "STOCK ON HAND",
            "STOCK STATUS",
            "ACTIONS",
        ])

        self.tbl_inventory.verticalHeader().setVisible(False)
        self.tbl_inventory.setAlternatingRowColors(True)
        self.tbl_inventory.setShowGrid(False)
        self.tbl_inventory.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                font-size: 12px;
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
                padding: 8px 10px;
            }
            QTableWidget::item {
                padding: 4px 8px;
                border-bottom: 1px solid #f1f5f9;
            }
        """)

        header = self.tbl_inventory.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.setSectionResizeMode(6, QHeaderView.Fixed)

        self.tbl_inventory.setColumnWidth(5, 130)
        self.tbl_inventory.setColumnWidth(6, 120)

        self.tbl_inventory.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_inventory.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_inventory.doubleClicked.connect(self._on_row_double_clicked)
        main_layout.addWidget(self.tbl_inventory, stretch=1)

        self._populate_categories()

    def _on_chip_clicked(self, mode: str, combo_text: str):
        self._active_filter_chip = mode
        self._update_chip_styles()
        self.cmb_stock_filter.blockSignals(True)
        idx = self.cmb_stock_filter.findText(combo_text)
        if idx >= 0:
            self.cmb_stock_filter.setCurrentIndex(idx)
        self.cmb_stock_filter.blockSignals(False)
        self.load_inventory()

    def _on_stock_combo_changed(self):
        txt = self.cmb_stock_filter.currentText()
        if txt == "In Stock":
            self._active_filter_chip = "in_stock"
        elif txt == "Low Stock Alert":
            self._active_filter_chip = "low_stock"
        elif txt == "Out of Stock":
            self._active_filter_chip = "out_of_stock"
        else:
            self._active_filter_chip = "all"
        self._update_chip_styles()
        self.load_inventory()

    def _update_chip_styles(self):
        for chip_btn, mode, _ in self.stock_chips:
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

    def _populate_categories(self):
        try:
            options = self._product_service.get_form_options(self._user)
            for cat in options.categories:
                self.cmb_category.addItem(cat.name, cat.id)
        except Exception:
            pass

    def load_inventory(self):
        """Fetch and render products with stock metrics and status badges."""
        try:
            keyword = self.txt_search.text().strip() or None
            category_id = self.cmb_category.currentData()
            stock_filter = self.cmb_stock_filter.currentText()

            filters = ProductFilterDTO(keyword=keyword, category_id=category_id, page_size=100)
            result = self._product_service.search(filters, self._user)
            products = result.items

            # Update Stat Cards
            metrics = self._product_service.get_metrics(self._user)
            self.card_total.update_value(str(metrics.total_products))
            self.card_total.set_caption("● Total active items")

            self.card_low_stock.update_value(str(metrics.low_stock))
            self.card_low_stock.set_caption("● Below threshold" if metrics.low_stock > 0 else "● Healthy")

            self.card_out_of_stock.update_value(str(metrics.out_of_stock))
            self.card_out_of_stock.set_caption("● Depleted items" if metrics.out_of_stock > 0 else "● All in stock")

            in_stock_count = max(0, metrics.total_products - metrics.low_stock - metrics.out_of_stock)
            self.card_in_stock.update_value(str(in_stock_count))
            self.card_in_stock.set_caption("● Optimal stock")

            # Apply Stock Filter
            filtered_products = []
            for p in products:
                status = p.stock_status
                if stock_filter == "Low Stock Alert" and status != "low_stock":
                    continue
                if stock_filter == "Out of Stock" and status != "out_of_stock":
                    continue
                if stock_filter == "In Stock" and status != "in_stock":
                    continue
                filtered_products.append(p)

            self._products_list = filtered_products
            self.tbl_inventory.setRowCount(len(filtered_products))

            dark_color = QColor("#0f172a")

            for row, p in enumerate(filtered_products):
                self.tbl_inventory.setRowHeight(row, 44)

                # SKU
                sku_item = QTableWidgetItem(p.sku)
                sku_item.setFont(QFont("Consolas", 10))
                sku_item.setForeground(QColor("#64748b"))
                sku_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                sku_item.setData(Qt.UserRole, p)
                self.tbl_inventory.setItem(row, 0, sku_item)

                # Product Name
                name_item = QTableWidgetItem(p.name)
                name_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                name_item.setForeground(dark_color)
                name_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.tbl_inventory.setItem(row, 1, name_item)

                # Category
                cat_item = QTableWidgetItem(p.category_name if p.category_name else "Uncategorized")
                cat_item.setForeground(QColor("#475569"))
                cat_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.tbl_inventory.setItem(row, 2, cat_item)

                # Reorder Level
                reorder_item = QTableWidgetItem(f"{p.reorder_level} Units")
                reorder_item.setForeground(QColor("#64748b"))
                reorder_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                self.tbl_inventory.setItem(row, 3, reorder_item)

                # Stock on Hand
                stock_item = QTableWidgetItem(f"{p.stock_quantity} Units")
                stock_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                stock_item.setForeground(dark_color)
                stock_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                self.tbl_inventory.setItem(row, 4, stock_item)

                # Stock Status Badge
                status_code = p.stock_status
                status_lbl = QLabel()
                status_lbl.setAlignment(Qt.AlignCenter)
                if status_code == "out_of_stock":
                    status_lbl.setText("● Out of Stock")
                    status_lbl.setStyleSheet("color: #dc2626; font-size: 10px; font-weight: 800; background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 2px 8px;")
                elif status_code == "low_stock":
                    status_lbl.setText(f"● Low ({p.stock_quantity})")
                    status_lbl.setStyleSheet("color: #d97706; font-size: 10px; font-weight: 800; background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 2px 8px;")
                else:
                    status_lbl.setText("● In Stock")
                    status_lbl.setStyleSheet("color: #047857; font-size: 10px; font-weight: 800; background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px; padding: 2px 8px;")

                self.tbl_inventory.setCellWidget(row, 5, status_lbl)

                # Action Button (Adjust Stock)
                btn_adjust = QPushButton("Adjust Stock")
                btn_adjust.setIcon(IconManager.get_pixmap("edit", color="#2563eb", size=12))
                btn_adjust.setCursor(Qt.PointingHandCursor)
                btn_adjust.setStyleSheet("""
                    QPushButton {
                        background-color: #eff6ff;
                        color: #2563eb;
                        border: 1px solid #bfdbfe;
                        border-radius: 6px;
                        font-size: 11px;
                        font-weight: 700;
                        padding: 4px 8px;
                    }
                    QPushButton:hover {
                        background-color: #2563eb;
                        color: #ffffff;
                    }
                """)
                btn_adjust.clicked.connect(lambda checked, prod=p: self._open_adjustment_dialog(prod))
                self.tbl_inventory.setCellWidget(row, 6, btn_adjust)

        except Exception as e:
            import logging
            logging.getLogger("retailflow.products").exception("Failed to load inventory", exc_info=e)

    def _on_row_double_clicked(self, index):
        row = index.row()
        item = self.tbl_inventory.item(row, 0)
        if item:
            prod = item.data(Qt.UserRole)
            if prod:
                self._open_adjustment_dialog(prod)

    def _open_adjustment_dialog(self, product: Product):
        dlg = StockAdjustmentDialog(product, self)
        if dlg.exec() == StockAdjustmentDialog.Accepted:
            try:
                self._product_service.adjust_inventory(
                    product_id=product.id,
                    new_quantity=dlg.new_quantity,
                    reason=dlg.adjustment_reason,
                    actor=self._user,
                )
                self._toast.show_toast(f"Stock adjusted for '{product.name}' ({dlg.new_quantity} units)")
                self.load_inventory()
            except Exception as e:
                self._toast.show_toast(str(e), is_error=True)
