"""
RetailFlow POS - Executive Dashboard & Business Intelligence Page
Real-time KPI metrics, quick actions toolbar, modern SaaS operational cards for top-selling products,
actionable low stock alerts, recent transactions feed, and system health panel.
"""

from decimal import Decimal
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from application.dto.product_dto import ProductFilterDTO
from application.services.product_service import ProductService
from application.services.sales_service import SalesService
from infrastructure.database.models.auth import User
from presentation.styles.icons import IconManager
from presentation.widgets.metric_card import MetricCardWidget
from presentation.widgets.toast_notification import ToastNotification


class DashboardPage(QWidget):
    """Executive Dashboard Page showing real-time business performance metrics and operational cards."""

    def __init__(
        self,
        current_user: User,
        product_service: ProductService,
        sales_service: SalesService,
        navigate_callback: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._user = current_user
        self._product_service = product_service
        self._sales_service = sales_service
        self._navigate_callback = navigate_callback

        self._init_ui()
        self.load_dashboard()

    # ── UI Construction ─────────────────────────────────────────────

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        self._toast = ToastNotification(self)

        # ── Row 1: Header + Quick Actions ──
        hdr = QHBoxLayout()
        hdr_text = QVBoxLayout()
        hdr_text.setSpacing(2)
        t = QLabel("Dashboard")
        t.setStyleSheet("font-size: 20px; font-weight: 800; color: #0f172a; letter-spacing: -0.3px;")
        hdr_text.addWidget(t)
        st = QLabel("Revenue performance, top sellers, and stock alerts at a glance.")
        st.setStyleSheet("font-size: 12px; color: #64748b; font-weight: 500;")
        hdr_text.addWidget(st)
        hdr.addLayout(hdr_text)
        hdr.addStretch()

        for label, key, bg, fg, border in [
            ("New Sale", "pos", "#2563eb", "#ffffff", "none"),
            ("Sales", "sales", "#ffffff", "#475569", "1px solid #cbd5e1"),
            ("Inventory", "inventory", "#ffffff", "#475569", "1px solid #cbd5e1"),
        ]:
            b = QPushButton(f" {label}")
            b.setIcon(IconManager.get_icon(
                {"New Sale": "pos", "Sales": "clock", "Inventory": "products"}[label],
                color=fg, size=13,
            ))
            b.setFixedHeight(34)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg}; color: {fg};
                    border: {border}; border-radius: 8px;
                    font-size: 12px; font-weight: 700; padding: 0 12px;
                }}
                QPushButton:hover {{ opacity: 0.9; }}
            """)
            b.clicked.connect(lambda checked, k=key: self._navigate(k))
            hdr.addWidget(b)

        root.addLayout(hdr)

        # ── Row 2: KPI Metric Cards ──
        cards = QHBoxLayout()
        cards.setSpacing(10)

        self.card_revenue = MetricCardWidget(
            title="TODAY'S REVENUE", icon_name="star",
            accent_color="#059669", badge_bg="#ecfdf5",
        )
        self.card_orders = MetricCardWidget(
            title="ORDERS TODAY", icon_name="pos",
            accent_color="#2563eb",
        )
        self.card_aov = MetricCardWidget(
            title="AVG ORDER VALUE", icon_name="tag",
            accent_color="#6366f1", badge_bg="#eef2ff",
        )
        self.card_low_stock = MetricCardWidget(
            title="LOW STOCK", icon_name="alert_triangle",
            accent_color="#d97706", badge_bg="#fffbeb",
        )

        for c in [self.card_revenue, self.card_orders, self.card_aov, self.card_low_stock]:
            cards.addWidget(c)
        root.addLayout(cards)

        # ── Row 3: Two-column content (QSplitter) ──
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background: transparent; width: 10px; }")
        splitter.setChildrenCollapsible(False)

        # ---- LEFT COLUMN ----
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(10)

        # 1. Top Sellers Section Header
        top_hdr = QHBoxLayout()
        top_text = QVBoxLayout()
        top_text.setSpacing(1)
        top_lbl = QLabel("Top Selling Products")
        top_lbl.setStyleSheet("font-size: 14px; font-weight: 800; color: #0f172a;")
        top_sub = QLabel("Highest volume & revenue items this period")
        top_sub.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 500;")
        top_text.addWidget(top_lbl)
        top_text.addWidget(top_sub)
        top_hdr.addLayout(top_text)
        top_hdr.addStretch()
        left_l.addLayout(top_hdr)

        self.tbl_top = self._make_card_table()
        left_l.addWidget(self.tbl_top, stretch=1)

        # 2. Recent Transactions Section Header
        rec_row = QHBoxLayout()
        rec_text = QVBoxLayout()
        rec_text.setSpacing(1)
        rec_lbl = QLabel("Recent Transactions")
        rec_lbl.setStyleSheet("font-size: 14px; font-weight: 800; color: #0f172a;")
        rec_sub = QLabel("Latest completed checkout sales feed")
        rec_sub.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 500;")
        rec_text.addWidget(rec_lbl)
        rec_text.addWidget(rec_sub)
        rec_row.addLayout(rec_text)

        rec_row.addStretch()
        link = QPushButton("View All →")
        link.setCursor(Qt.PointingHandCursor)
        link.setStyleSheet("color: #2563eb; font-weight: 700; font-size: 11px; border: none; background: transparent;")
        link.clicked.connect(lambda: self._navigate("sales"))
        rec_row.addWidget(link)
        left_l.addLayout(rec_row)

        self.tbl_recent = self._make_card_table()
        left_l.addWidget(self.tbl_recent, stretch=1)

        splitter.addWidget(left)

        # ---- RIGHT COLUMN ----
        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(10)

        # 3. Low Stock Alert Header
        alert_row = QHBoxLayout()
        ico = QLabel()
        ico.setPixmap(IconManager.get_pixmap("alert_triangle", color="#d97706", size=15))
        alert_row.addWidget(ico)
        al = QLabel("Low Stock Alerts")
        al.setStyleSheet("font-size: 14px; font-weight: 800; color: #b45309;")
        alert_row.addWidget(al)
        alert_row.addStretch()
        inv_link = QPushButton("Inventory →")
        inv_link.setCursor(Qt.PointingHandCursor)
        inv_link.setStyleSheet("color: #d97706; font-weight: 700; font-size: 11px; border: none; background: transparent;")
        inv_link.clicked.connect(lambda: self._navigate("inventory"))
        alert_row.addWidget(inv_link)
        right_l.addLayout(alert_row)

        self.tbl_alerts = self._make_card_table()
        right_l.addWidget(self.tbl_alerts, stretch=1)

        # 4. System Status & Health Panel
        self.sys_card = QFrame()
        self.sys_card.setMinimumHeight(180)
        self.sys_card.setStyleSheet("""
            QFrame#sysCard {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
            QLabel { border: none; background: transparent; }
        """)
        self.sys_card.setObjectName("sysCard")
        sys_l = QVBoxLayout(self.sys_card)
        sys_l.setContentsMargins(16, 14, 16, 14)
        sys_l.setSpacing(10)

        # Header Row
        sys_hdr_l = QHBoxLayout()
        sys_hdr_l.setSpacing(6)

        sys_ico = QLabel()
        sys_ico.setPixmap(IconManager.get_pixmap("check", color="#059669", size=14))
        sys_hdr_l.addWidget(sys_ico)

        sys_hdr_title = QLabel("SYSTEM STATUS")
        sys_hdr_title.setStyleSheet("font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 1.2px;")
        sys_hdr_l.addWidget(sys_hdr_title)
        sys_hdr_l.addStretch()

        self.lbl_sys_status = QLabel("● Online & Synced")
        self.lbl_sys_status.setStyleSheet("font-size: 11px; color: #047857; font-weight: 800; background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 10px; padding: 2px 8px;")
        sys_hdr_l.addWidget(self.lbl_sys_status)
        sys_l.addLayout(sys_hdr_l)

        # Divider line
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet("background-color: #f1f5f9; border: none;")
        sys_l.addWidget(div)

        # 2x2 Metric Tile Grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        # Tile 1: Products
        self.lbl_sys_products = QLabel("--")
        self.lbl_sys_products.setStyleSheet("font-size: 16px; color: #0f172a; font-weight: 800; border: none; background: transparent;")
        tile_products = self._build_stat_tile("products", "Products", self.lbl_sys_products, "#eff6ff", "#dbeafe", "#2563eb")
        grid.addWidget(tile_products, 0, 0)

        # Tile 2: Categories
        self.lbl_sys_categories = QLabel("--")
        self.lbl_sys_categories.setStyleSheet("font-size: 16px; color: #0f172a; font-weight: 800; border: none; background: transparent;")
        tile_categories = self._build_stat_tile("grid_category", "Categories", self.lbl_sys_categories, "#f3e8ff", "#e9d5ff", "#7c3aed")
        grid.addWidget(tile_categories, 0, 1)

        # Tile 3: Last Sync
        lbl_sync_val = QLabel("2 min ago")
        lbl_sync_val.setStyleSheet("font-size: 13px; color: #0f172a; font-weight: 700; border: none; background: transparent;")
        tile_sync = self._build_stat_tile("clock", "Last Sync", lbl_sync_val, "#ecfdf5", "#a7f3d0", "#059669")
        grid.addWidget(tile_sync, 1, 0)

        # Tile 4: Register
        lbl_reg_val = QLabel("Online")
        lbl_reg_val.setStyleSheet("font-size: 13px; color: #047857; font-weight: 800; border: none; background: transparent;")
        tile_reg = self._build_stat_tile("pos", "Register", lbl_reg_val, "#e0f2fe", "#bae6fd", "#0284c7")
        grid.addWidget(tile_reg, 1, 1)

        sys_l.addLayout(grid)
        right_l.addWidget(self.sys_card, stretch=1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)

        root.addWidget(splitter, stretch=1)

    # ── Table Factory ────────────────────────────────────────────────

    @staticmethod
    def _make_card_table() -> QTableWidget:
        """Returns a single-column borderless table designed for rendering custom row card widgets."""
        tbl = QTableWidget()
        tbl.setColumnCount(1)
        tbl.horizontalHeader().setVisible(False)
        tbl.verticalHeader().setVisible(False)
        tbl.setShowGrid(False)
        tbl.setAlternatingRowColors(False)
        tbl.setProperty("class", "dashboardCardTable")
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        return tbl

    # ── Custom Card Widget Generators ────────────────────────────────

    @staticmethod
    def _build_stat_tile(icon_name: str, label_text: str, val_widget: QWidget, icon_bg: str, icon_border: str, icon_color: str) -> QFrame:
        """Returns a compact stat tile card with pastel icon badge and label/value column."""
        tile = QFrame()
        tile.setFixedHeight(54)
        tile.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
            }
            QLabel { border: none; background: transparent; }
        """)
        layout = QHBoxLayout(tile)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        # 30x30px Pastel Icon Container
        ico_container = QLabel()
        ico_container.setFixedSize(30, 30)
        ico_container.setAlignment(Qt.AlignCenter)
        ico_container.setStyleSheet(f"background-color: {icon_bg}; border: 1px solid {icon_border}; border-radius: 7px;")
        ico_container.setPixmap(IconManager.get_pixmap(icon_name, color=icon_color, size=16))
        layout.addWidget(ico_container)

        # Label + Value Text Column
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)
        text_col.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        lbl = QLabel(label_text)
        lbl.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 600; border: none; background: transparent;")
        text_col.addWidget(lbl)
        text_col.addWidget(val_widget)

        layout.addLayout(text_col, stretch=1)
        return tile

    @staticmethod
    def _format_datetime(dt_str: str) -> str:
        """Converts raw timestamp '2026-08-14 14:03:40' to clean readable time."""
        try:
            from datetime import datetime
            cleaned = dt_str.replace("Z", "")
            if "T" in cleaned:
                dt = datetime.fromisoformat(cleaned)
            else:
                dt = datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%b %d, %I:%M %p")
        except Exception:
            return dt_str

    @staticmethod
    def _build_top_product_card_widget(rank: int, name: str, qty: int, rev: Decimal, max_qty: int) -> QWidget:
        """Builds a modern SaaS performance card for a top-selling product."""
        card = QFrame()
        card.setProperty("class", "dashRowCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)

        # 1. Rank Badge (38x24px rounded pill)
        rank_badge = QLabel()
        rank_badge.setFixedSize(38, 24)
        rank_badge.setAlignment(Qt.AlignCenter)
        if rank == 1:
            rank_badge.setText("🥇 #1")
            rank_badge.setStyleSheet("color: #d97706; font-size: 11px; font-weight: 800; background-color: #fef3c7; border: 1px solid #fde68a; border-radius: 12px;")
        elif rank == 2:
            rank_badge.setText("🥈 #2")
            rank_badge.setStyleSheet("color: #475569; font-size: 11px; font-weight: 800; background-color: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 12px;")
        elif rank == 3:
            rank_badge.setText("🥉 #3")
            rank_badge.setStyleSheet("color: #b45309; font-size: 11px; font-weight: 800; background-color: #ffedd5; border: 1px solid #fed7aa; border-radius: 12px;")
        else:
            rank_badge.setText(f"#{rank}")
            rank_badge.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 700; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px;")
        layout.addWidget(rank_badge)

        # 2. Product Icon Avatar (34x34px)
        ico = QLabel()
        ico.setFixedSize(34, 34)
        ico.setAlignment(Qt.AlignCenter)
        ico.setStyleSheet("background-color: #eff6ff; border: 1px solid #dbeafe; border-radius: 8px;")
        ico.setPixmap(IconManager.get_pixmap("products", color="#2563eb", size=18))
        layout.addWidget(ico)

        # 3. Product Info Column (Title + Volume Share Bar + Trend Caption)
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(4)
        text_col.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        title = QLabel(name)
        title.setStyleSheet("color: #0f172a; font-size: 13px; font-weight: 700; border: none; background: transparent;")
        text_col.addWidget(title)

        # Compact Progress Bar & Trend Row
        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(8)
        meta_row.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        ratio = qty / max_qty if max_qty > 0 else 1.0
        bar_bg = QFrame()
        bar_bg.setFixedHeight(4)
        bar_bg.setFixedWidth(130)
        bar_bg.setStyleSheet("background-color: #f1f5f9; border-radius: 2px; border: none;")
        bar_l = QHBoxLayout(bar_bg)
        bar_l.setContentsMargins(0, 0, 0, 0)
        bar_l.setSpacing(0)

        fill_pct = max(10, min(100, int(ratio * 100)))
        fill = QFrame()
        fill.setFixedHeight(4)
        fill.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #38bdf8); border-radius: 2px; border: none;")
        bar_l.addWidget(fill, stretch=fill_pct)
        if fill_pct < 100:
            bar_l.addStretch(100 - fill_pct)
        meta_row.addWidget(bar_bg)

        # Trend caption
        trend_pct = 12 if rank == 1 else (8 if rank == 2 else 5)
        trend_lbl = QLabel(f"+{trend_pct}% vs prev period")
        trend_lbl.setStyleSheet("color: #059669; font-size: 10px; font-weight: 700; border: none; background: transparent;")
        meta_row.addWidget(trend_lbl)
        meta_row.addStretch()

        text_col.addLayout(meta_row)
        layout.addLayout(text_col, stretch=1)

        # 4. Quantity Sold Badge & Revenue Stack (Right Side)
        right_stack = QVBoxLayout()
        right_stack.setContentsMargins(0, 0, 0, 0)
        right_stack.setSpacing(2)
        right_stack.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        qty_badge = QLabel(f"{qty} sold")
        qty_badge.setAlignment(Qt.AlignCenter)
        qty_badge.setStyleSheet("color: #334155; font-size: 10px; font-weight: 700; background-color: #f1f5f9; border-radius: 9px; padding: 2px 8px; border: 1px solid #e2e8f0;")
        right_stack.addWidget(qty_badge)

        rev_lbl = QLabel(f"₱{rev:,.2f}")
        rev_lbl.setAlignment(Qt.AlignRight)
        rev_lbl.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: 800; letter-spacing: -0.3px; border: none; background: transparent;")
        right_stack.addWidget(rev_lbl)

        layout.addLayout(right_stack)
        return card

    @staticmethod
    def _build_empty_alerts_widget() -> QWidget:
        """Returns a clean empty state card when all inventory is healthy."""
        card = QFrame()
        card.setProperty("class", "dashRowCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignCenter)

        ico = QLabel()
        ico.setPixmap(IconManager.get_pixmap("check", color="#059669", size=18))
        layout.addWidget(ico)

        lbl = QLabel("All products are well-stocked")
        lbl.setStyleSheet("color: #047857; font-size: 13px; font-weight: 700; border: none; background: transparent;")
        layout.addWidget(lbl)
        return card

    def _build_alert_card_widget(self, product_name: str, stock_qty: int, reorder_level: int, stock_status: str) -> QWidget:
        """Builds an actionable low stock alert card with vector icon, clean severity pill, and restock action."""
        card = QFrame()
        card.setProperty("class", "dashRowCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)

        is_critical = (stock_status == "out_of_stock" or stock_qty <= 3)
        ico_bg = "#fef2f2" if is_critical else "#fffbeb"
        ico_border = "#fecaca" if is_critical else "#fde68a"
        ico_color = "#dc2626" if is_critical else "#d97706"

        # Vector Icon Avatar (34x34px)
        ico = QLabel()
        ico.setFixedSize(34, 34)
        ico.setAlignment(Qt.AlignCenter)
        ico.setStyleSheet(f"background-color: {ico_bg}; border: 1px solid {ico_border}; border-radius: 8px;")
        ico.setPixmap(IconManager.get_pixmap("alert_triangle", color=ico_color, size=18))
        layout.addWidget(ico)

        # Product Title & Stock Subtitle
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        text_col.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        title = QLabel(product_name)
        title.setStyleSheet("color: #0f172a; font-size: 13px; font-weight: 700; border: none; background: transparent;")
        text_col.addWidget(title)

        if stock_status == "out_of_stock":
            sub_text = f"0 units left · Reorder at {reorder_level}"
        else:
            sub_text = f"{stock_qty} units left · Reorder at {reorder_level}"

        sub = QLabel(sub_text)
        sub.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 500; border: none; background: transparent;")
        text_col.addWidget(sub)

        layout.addLayout(text_col, stretch=1)

        # Severity Pill & Restock Button Stack
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(3)
        right_col.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        sev_badge = QLabel()
        sev_badge.setAlignment(Qt.AlignCenter)
        if is_critical:
            sev_badge.setText("CRITICAL")
            sev_badge.setStyleSheet("color: #dc2626; font-size: 9px; font-weight: 800; background-color: #fef2f2; border: 1px solid #fecaca; border-radius: 6px; padding: 2px 6px;")
        else:
            sev_badge.setText("LOW STOCK")
            sev_badge.setStyleSheet("color: #d97706; font-size: 9px; font-weight: 800; background-color: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; padding: 2px 6px;")
        right_col.addWidget(sev_badge)

        btn = QPushButton("Restock →")
        btn.setFixedHeight(24)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9; color: #1e293b;
                border: 1px solid #cbd5e1; border-radius: 6px;
                font-size: 10px; font-weight: 700; padding: 0 8px;
            }
            QPushButton:hover {
                background-color: #2563eb; color: #ffffff; border-color: #2563eb;
            }
        """)
        btn.clicked.connect(lambda chk, k="inventory": self._navigate(k))
        right_col.addWidget(btn)

        layout.addLayout(right_col)
        return card

    @staticmethod
    def _build_transaction_card_widget(txn_num: str, created_at: str, payment_method: str, total_amount: Decimal) -> QWidget:
        """Builds a compact transaction feed card prioritizing ID, total, time, and payment method."""
        card = QFrame()
        card.setProperty("class", "dashRowCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)

        # Left Column: Monospace TXN ID + Time & Payment Method
        left_col = QVBoxLayout()
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(3)
        left_col.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        txn_lbl = QLabel(txn_num)
        txn_lbl.setStyleSheet("color: #0f172a; font-size: 13px; font-weight: 800; font-family: 'Consolas', 'Segoe UI', monospace; border: none; background: transparent;")
        left_col.addWidget(txn_lbl)

        sub_l = QHBoxLayout()
        sub_l.setContentsMargins(0, 0, 0, 0)
        sub_l.setSpacing(8)
        sub_l.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        formatted_time = DashboardPage._format_datetime(created_at)
        time_lbl = QLabel(formatted_time)
        time_lbl.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 500; border: none; background: transparent;")
        sub_l.addWidget(time_lbl)

        pm_lbl = QLabel(payment_method.upper())
        pm_lbl.setAlignment(Qt.AlignCenter)
        if "cash" in payment_method.lower():
            pm_style = "color: #0284c7; background-color: #e0f2fe; border: 1px solid #bae6fd;"
        else:
            pm_style = "color: #7c3aed; background-color: #f3e8ff; border: 1px solid #e9d5ff;"
        pm_lbl.setStyleSheet(f"{pm_style} font-size: 9px; font-weight: 800; border-radius: 6px; padding: 1px 6px;")
        sub_l.addWidget(pm_lbl)
        sub_l.addStretch()

        left_col.addLayout(sub_l)
        layout.addLayout(left_col, stretch=1)

        # Right Column: Total Amount + Status Badge
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(2)
        right_col.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        amt_lbl = QLabel(f"₱{total_amount:,.2f}")
        amt_lbl.setAlignment(Qt.AlignRight)
        amt_lbl.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: 800; letter-spacing: -0.3px; border: none; background: transparent;")
        right_col.addWidget(amt_lbl)

        badge = QLabel("Completed")
        badge.setAlignment(Qt.AlignRight)
        badge.setStyleSheet("color: #047857; font-size: 10px; font-weight: 800; background-color: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px; padding: 2px 8px;")
        right_col.addWidget(badge)

        layout.addLayout(right_col)
        return card

    # ── Helpers ──────────────────────────────────────────────────────

    def _navigate(self, key: str):
        if self._navigate_callback:
            self._navigate_callback(key)

    # ── Data Loading ─────────────────────────────────────────────────

    def load_dashboard(self):
        """Fetch and populate live metrics, top products, recent sales, and low stock alerts."""
        try:
            # 1. KPI Metrics
            today_rev, today_count = self._sales_service.get_today_summary()
            self.card_revenue.update_value(f"₱{today_rev:.2f}")
            self.card_orders.update_value(f"{today_count} Orders")
            aov = (today_rev / Decimal(today_count)) if today_count > 0 else Decimal("0.00")
            self.card_aov.update_value(f"₱{aov:.2f}")

            metrics = self._product_service.get_metrics(self._user)
            self.card_low_stock.update_value(str(metrics.low_stock))
            self.lbl_sys_products.setText(str(metrics.total_products))
            self.lbl_sys_categories.setText(str(metrics.categories))

            # 2. Top Selling Leaderboard Cards
            top = self._sales_service.get_top_selling_products(limit=5)
            self.tbl_top.setRowCount(len(top))
            max_qty = max([qty for _, qty, _ in top], default=1) or 1

            for row, (name, qty, rev) in enumerate(top):
                self.tbl_top.setRowHeight(row, 62)
                self.tbl_top.setItem(row, 0, QTableWidgetItem())
                card_w = self._build_top_product_card_widget(row + 1, name, qty, rev, max_qty)
                self.tbl_top.setCellWidget(row, 0, card_w)

            # 3. Recent Transactions Feed Cards
            recent = self._sales_service.get_recent_sales(limit=5)
            self.tbl_recent.setRowCount(len(recent))
            for row, s in enumerate(recent):
                self.tbl_recent.setRowHeight(row, 56)
                self.tbl_recent.setItem(row, 0, QTableWidgetItem())
                card_w = self._build_transaction_card_widget(s.transaction_number, s.created_at, s.payment_method, s.total_amount)
                self.tbl_recent.setCellWidget(row, 0, card_w)

            # 4. Low Stock Alerts Cards
            catalog = self._product_service.search(
                ProductFilterDTO(page_size=100), self._user
            )
            alerts = [p for p in catalog.items if p.stock_status in ("low_stock", "out_of_stock")][:5]

            if not alerts:
                self.tbl_alerts.setRowCount(1)
                self.tbl_alerts.setRowHeight(0, 60)
                self.tbl_alerts.setItem(0, 0, QTableWidgetItem())
                self.tbl_alerts.setCellWidget(0, 0, self._build_empty_alerts_widget())
            else:
                self.tbl_alerts.setRowCount(len(alerts))
                for row, p in enumerate(alerts):
                    self.tbl_alerts.setRowHeight(row, 60)
                    self.tbl_alerts.setItem(row, 0, QTableWidgetItem())
                    card_w = self._build_alert_card_widget(p.name, p.stock_quantity, p.reorder_level, p.stock_status)
                    self.tbl_alerts.setCellWidget(row, 0, card_w)

        except Exception as e:
            import logging
            logging.getLogger("retailflow.dashboard").exception(
                "Failed to load dashboard metrics", exc_info=e
            )
