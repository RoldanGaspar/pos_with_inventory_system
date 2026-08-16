"""
RetailFlow POS - Main Application Window
Shell with native PySide6 animated collapsible sidebar navigation (240px ↔ 72px), user profile card, and stacked content area.
Configured with screen-aware geometry sizing so windowed mode fits 100% inside screen bounds.
"""

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from application.services.audit_service import AuditService
from application.services.auth_service import AuthenticationService
from application.services.customer_service import CustomerService
from application.services.expense_service import ExpenseService
from application.services.product_service import ProductService
from application.services.purchasing_service import PurchasingService
from application.services.report_export_service import ReportExportService
from application.services.report_service import ReportService
from application.services.returns_service import ReturnsService
from application.services.sales_service import SalesService
from application.services.settings_service import SettingsService
from application.services.supplier_service import SupplierService
from application.services.user_service import UserService
from infrastructure.database.models.auth import User
from infrastructure.database.session import create_session
from presentation.styles.icons import IconManager
from presentation.widgets.audit_page import AuditPage
from presentation.widgets.customers_page import CustomersPage
from presentation.widgets.dashboard_page import DashboardPage
from presentation.widgets.expenses_page import ExpensesPage
from presentation.widgets.inventory_page import InventoryPage
from presentation.widgets.pos_page import POSPage
from presentation.widgets.products_page import ProductsPage
from presentation.widgets.purchasing_page import PurchasingPage
from presentation.widgets.reports_page import ReportsPage
from presentation.widgets.sales_page import SalesPage
from presentation.widgets.settings_page import SettingsPage
from presentation.widgets.suppliers_page import SuppliersPage
from presentation.widgets.users_page import UsersPage

NAV_ITEMS = [
    ("Dashboard", "dashboard", "Dashboard"),
    ("Point of Sale", "pos", "POS"),
    ("Sales", "sales", "Sales"),
    ("Products", "products", "Products"),
    ("Inventory", "inventory", "Inventory"),
    ("Purchasing", "purchasing", "Purchasing"),
    ("Suppliers", "suppliers", "Suppliers"),
    ("Customers", "customers", "Customers"),
    ("Expenses", "expenses", "Expenses"),
    ("Reports", "reports", "Reports"),
    ("Users", "users", "Users"),
    ("Audit Logs", "audit", "Audit"),
    ("Settings", "settings", "Settings"),
]

SIDEBAR_GROUPS = [
    ("SALES", ["dashboard", "pos", "sales"]),
    ("CATALOG", ["products", "inventory"]),
    ("OPERATIONS", ["purchasing", "suppliers", "customers", "expenses"]),
    ("SYSTEM", ["reports", "users", "audit", "settings"]),
]


class NavItemWidget(QFrame):
    """Reusable sidebar navigation item supporting smooth collapse/expand, active state, and label opacity fade."""

    clicked = Signal()

    def __init__(self, key: str, label: str, icon_name: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.label_text = label
        self.icon_name = icon_name
        self.is_active = False
        self.is_disabled = False

        self.setProperty("class", "navItemWidget")
        self.setFixedHeight(44)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 3.5px Left Active Bar Indicator
        self.active_bar = QFrame()
        self.active_bar.setProperty("class", "navActiveIndicator")
        self.active_bar.setFixedWidth(4)
        self.active_bar.setFixedHeight(24)
        layout.addWidget(self.active_bar)

        layout.addSpacing(12)

        # 20x20 Icon Label
        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(20, 20)
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.icon_lbl)

        layout.addSpacing(12)

        # Nav Text Label with Opacity Effect
        self.text_lbl = QLabel(label)
        self.text_lbl.setProperty("class", "navItemText")
        self.text_lbl.setStyleSheet("background: transparent; border: none;")

        self.opacity_effect = QGraphicsOpacityEffect(self.text_lbl)
        self.text_lbl.setGraphicsEffect(self.opacity_effect)
        layout.addWidget(self.text_lbl, stretch=1)

        self.update_icon()

    def update_icon(self):
        color = "#38bdf8" if self.is_active else ("#334155" if self.is_disabled else "#94a3b8")
        pixmap = IconManager.get_icon(self.key, color=color, size=20).pixmap(QSize(20, 20))
        self.icon_lbl.setPixmap(pixmap)

    def set_active(self, active: bool):
        self.is_active = active
        self.setProperty("active", active)
        self.active_bar.setProperty("active", active)
        self.text_lbl.setProperty("active", active)

        self.style().unpolish(self)
        self.style().polish(self)
        self.active_bar.style().unpolish(self.active_bar)
        self.active_bar.style().polish(self.active_bar)
        self.text_lbl.style().unpolish(self.text_lbl)
        self.text_lbl.style().polish(self.text_lbl)

        self.update_icon()

    def set_disabled_state(self, disabled: bool):
        self.is_disabled = disabled
        self.setEnabled(not disabled)
        if disabled:
            self.setCursor(Qt.ForbiddenCursor)
        self.update_icon()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.is_disabled:
            self.clicked.emit()
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    """Main application window with native PySide6 animated collapsible sidebar navigation and stacked content."""

    def __init__(self, current_user=None, session_token="", session=None, settings_service=None):
        super().__init__()
        self._session = session or create_session()
        self._owns_session = session is None
        if current_user is not None:
            current_user = self._session.get(User, current_user.id)
        self._current_user = current_user
        self._session_token = session_token
        self._product_service = ProductService(self._session)
        self._sales_service = SalesService(self._session)
        self._user_service = UserService(self._session)
        self._audit_service = AuditService(self._session)
        self._customer_service = CustomerService(self._session)
        self._supplier_service = SupplierService(self._session)
        self._purchasing_service = PurchasingService(self._session)
        self._expense_service = ExpenseService(self._session)
        self._report_service = ReportService(self._session, expense_service=self._expense_service)
        self._report_export_service = ReportExportService(self._report_service)
        self._returns_service = ReturnsService(self._session)
        self._auth_service = AuthenticationService(self._session)
        self._settings_service = settings_service or SettingsService(self._session)
        self._settings_page = None
        self.setWindowTitle("RetailFlow POS")

        # Responsive minimum size for laptop and desktop monitors
        self.setMinimumSize(1024, 580)

        # Screen-aware default window sizing
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            w = min(1280, avail.width() - 20)
            h = min(700, avail.height() - 20)
            self.resize(w, h)
        else:
            self.resize(1280, 680)

        self._current_page = ""
        self._sidebar_collapsed = False
        self._anim_group = None
        self._opacity_effects = []
        self.nav_buttons = {}
        self.nav_labels = {}
        self._group_labels = []

        self._init_ui()
        self._update_user_display()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ─── Sidebar ───
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setMinimumWidth(240)
        self.sidebar.setMaximumWidth(240)
        self.sidebar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # Sidebar Header with App Title & Collapse Toggle Button
        sidebar_hdr = QFrame()
        sidebar_hdr.setObjectName("sidebarHeader")
        sidebar_hdr.setFixedHeight(52)
        self.sidebar_hdr_l = QHBoxLayout(sidebar_hdr)
        self.sidebar_hdr_l.setContentsMargins(14, 0, 8, 0)
        self.sidebar_hdr_l.setSpacing(6)

        self.sidebar_logo_lbl = QLabel()
        self.sidebar_logo_lbl.setFixedSize(22, 22)
        self.sidebar_logo_lbl.setPixmap(IconManager.get_icon("pos", color="#38bdf8", size=22).pixmap(QSize(22, 22)))
        self.sidebar_hdr_l.addWidget(self.sidebar_logo_lbl)

        self.sidebar_title_lbl = QLabel("RetailFlow POS")
        self.sidebar_title_lbl.setObjectName("sidebarTitle")
        
        # Opacity effect for title label
        title_op = QGraphicsOpacityEffect(self.sidebar_title_lbl)
        self.sidebar_title_lbl.setGraphicsEffect(title_op)
        self._opacity_effects.append(title_op)
        
        self.sidebar_hdr_l.addWidget(self.sidebar_title_lbl, stretch=1)

        self.sidebar_toggle_btn = QPushButton()
        self.sidebar_toggle_btn.setObjectName("sidebarToggleBtn")
        self.sidebar_toggle_btn.setFixedSize(30, 30)
        self.sidebar_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.sidebar_toggle_btn.setToolTip("Collapse Sidebar")
        self.sidebar_toggle_btn.setIcon(IconManager.get_icon("chevron_left", color="#94a3b8", size=16))
        self.sidebar_toggle_btn.clicked.connect(self.toggle_sidebar)
        self.sidebar_hdr_l.addWidget(self.sidebar_toggle_btn)

        sidebar_layout.addWidget(sidebar_hdr)

        # Scrollable Navigation Container
        sidebar_scroll = QScrollArea()
        sidebar_scroll.setObjectName("sidebarScrollArea")
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setFrameShape(QFrame.NoFrame)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sidebar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        nav_container = QWidget()
        nav_container.setStyleSheet("background: transparent;")
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 4, 0, 4)
        nav_layout.setSpacing(0)

        # Navigation Groups with Vertical Spacing
        for i, (group_title, group_keys) in enumerate(SIDEBAR_GROUPS):
            if i > 0:
                nav_layout.addSpacing(14)

            group_lbl = QLabel(group_title)
            group_lbl.setProperty("class", "sidebarGroupLabel")
            group_lbl.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 700; letter-spacing: 1.5px; padding: 10px 16px 2px 16px;")

            group_op = QGraphicsOpacityEffect(group_lbl)
            group_lbl.setGraphicsEffect(group_op)
            self._opacity_effects.append(group_op)

            nav_layout.addWidget(group_lbl)
            self._group_labels.append(group_lbl)

            for key in group_keys:
                item_tuple = next((item for item in NAV_ITEMS if item[1] == key), None)
                if item_tuple:
                    label, _, _icon_name = item_tuple
                    nav_item = NavItemWidget(key, label, _icon_name)

                    if key == "products" and not self._has_permission("view_products"):
                        nav_item.set_disabled_state(True)
                    elif key == "expenses" and not self._has_permission("view_expenses"):
                        nav_item.set_disabled_state(True)
                    elif key == "reports" and not self._has_permission("view_reports"):
                        nav_item.setVisible(False)
                    elif key == "users" and not self._has_permission("manage_users"):
                        nav_item.set_disabled_state(True)
                    elif key == "audit" and not self._has_permission("view_audit_logs"):
                        nav_item.set_disabled_state(True)
                    elif key == "settings" and not self._has_permission("view_settings"):
                        nav_item.set_disabled_state(True)
                        nav_item.setVisible(False)

                    nav_item.clicked.connect(lambda k=key: self.navigate_to(k))
                    nav_layout.addWidget(nav_item)
                    self.nav_buttons[key] = nav_item
                    self.nav_labels[key] = label

        nav_layout.addStretch()
        sidebar_scroll.setWidget(nav_container)
        sidebar_layout.addWidget(sidebar_scroll, stretch=1)

        # Sidebar Bottom User Profile Card
        self.sidebar_profile_card = QFrame()
        self.sidebar_profile_card.setObjectName("sidebarProfileCard")
        self.sidebar_profile_card.setCursor(Qt.PointingHandCursor)
        self.sidebar_profile_card.setFixedHeight(56)
        self.sidebar_profile_card.mousePressEvent = self._show_user_menu

        self.card_l = QHBoxLayout(self.sidebar_profile_card)
        self.card_l.setContentsMargins(12, 6, 12, 6)
        self.card_l.setSpacing(10)

        self.sb_avatar_lbl = QLabel("SA")
        self.sb_avatar_lbl.setObjectName("sidebarAvatar")
        self.sb_avatar_lbl.setFixedSize(32, 32)
        self.sb_avatar_lbl.setAlignment(Qt.AlignCenter)

        self.sb_info_widget = QWidget()
        self.sb_info_widget.setStyleSheet("background: transparent; border: none;")
        info_l = QVBoxLayout(self.sb_info_widget)
        info_l.setContentsMargins(0, 0, 0, 0)
        info_l.setSpacing(0)

        self.sb_name_lbl = QLabel("System Admin")
        self.sb_name_lbl.setObjectName("sidebarProfileName")
        self.sb_role_lbl = QLabel("Administrator")
        self.sb_role_lbl.setObjectName("sidebarProfileRole")

        info_l.addWidget(self.sb_name_lbl)
        info_l.addWidget(self.sb_role_lbl)

        # Opacity effect for profile text info widget
        info_op = QGraphicsOpacityEffect(self.sb_info_widget)
        self.sb_info_widget.setGraphicsEffect(info_op)
        self._opacity_effects.append(info_op)

        self.card_l.addWidget(self.sb_avatar_lbl)
        self.card_l.addWidget(self.sb_info_widget, stretch=1)

        sidebar_layout.addWidget(self.sidebar_profile_card)

        # Footer version label
        self.sb_version_lbl = QLabel("v1.0.0")
        self.sb_version_lbl.setObjectName("sidebarFooterVersion")
        self.sb_version_lbl.setAlignment(Qt.AlignCenter)
        self.sb_version_lbl.setFixedHeight(22)

        ver_op = QGraphicsOpacityEffect(self.sb_version_lbl)
        self.sb_version_lbl.setGraphicsEffect(ver_op)
        self._opacity_effects.append(ver_op)

        sidebar_layout.addWidget(self.sb_version_lbl)

        main_layout.addWidget(self.sidebar)

        # ─── Content Area ───
        content_frame = QFrame()
        content_frame.setObjectName("contentArea")
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Top bar
        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(44)
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(16, 0, 16, 0)
        topbar_layout.setSpacing(12)

        self.page_title = QLabel("Dashboard")
        self.page_title.setObjectName("pageTitle")
        topbar_layout.addWidget(self.page_title)

        topbar_layout.addStretch()

        # Topbar User Profile Pill Container
        self.user_btn = QFrame()
        self.user_btn.setObjectName("topbarUserPill")
        self.user_btn.setCursor(Qt.PointingHandCursor)
        self.user_btn.setFixedHeight(32)
        self.user_btn.setStyleSheet("""
            QFrame#topbarUserPill {
                background-color: #f8fafc;
                border: 1px solid #cbd5e1;
                border-radius: 16px;
            }
            QFrame#topbarUserPill:hover {
                background-color: #f1f5f9;
                border-color: #94a3b8;
            }
        """)
        user_layout = QHBoxLayout(self.user_btn)
        user_layout.setContentsMargins(3, 2, 10, 2)
        user_layout.setSpacing(6)

        self.avatar_lbl = QLabel("S")
        self.avatar_lbl.setFixedSize(26, 26)
        self.avatar_lbl.setAlignment(Qt.AlignCenter)
        self.avatar_lbl.setStyleSheet("""
            background-color: #2563eb;
            color: #ffffff;
            border-radius: 13px;
            font-weight: 800;
            font-size: 11px;
            border: none;
        """)

        self.name_lbl = QLabel("User")
        self.name_lbl.setStyleSheet("color: #0f172a; font-size: 12px; font-weight: 700; border: none; background: transparent;")

        arrow_lbl = QLabel("▾")
        arrow_lbl.setStyleSheet("color: #64748b; font-size: 11px; border: none; background: transparent;")

        user_layout.addWidget(self.avatar_lbl)
        user_layout.addWidget(self.name_lbl)
        user_layout.addWidget(arrow_lbl)

        self.user_btn.mousePressEvent = self._show_user_menu

        topbar_layout.addWidget(self.user_btn)
        content_layout.addWidget(topbar)

        # Stacked pages
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)

        main_layout.addWidget(content_frame)

        # Create pages
        for label, key, _ in NAV_ITEMS:
            if key == "dashboard":
                page = DashboardPage(
                    self._current_user,
                    self._product_service,
                    self._sales_service,
                    navigate_callback=self.navigate_to,
                )
            elif key == "products":
                page = ProductsPage(self._current_user, self._product_service)
            elif key == "pos":
                page = POSPage(
                    self._current_user, self._product_service, self._sales_service
                )
            elif key == "sales":
                page = SalesPage(
                    self._current_user,
                    self._sales_service,
                    returns_service=self._returns_service,
                    auth_service=self._auth_service,
                )
            elif key == "inventory":
                page = InventoryPage(self._current_user, self._product_service)
            elif key == "users":
                page = UsersPage(self._current_user, self._user_service)
            elif key == "audit":
                page = AuditPage(self._current_user, self._audit_service)
            elif key == "customers":
                page = CustomersPage(self._current_user, self._customer_service)
            elif key == "suppliers":
                page = SuppliersPage(self._current_user, self._supplier_service)
            elif key == "purchasing":
                page = PurchasingPage(
                    self._current_user,
                    self._purchasing_service,
                    self._supplier_service,
                    self._product_service,
                )
            elif key == "expenses":
                page = ExpensesPage(self._current_user, self._expense_service)
            elif key == "reports":
                page = ReportsPage(
                    current_user=self._current_user,
                    report_service=self._report_service,
                    report_export_service=self._report_export_service,
                )
            elif key == "settings":
                page = SettingsPage(
                    current_user=self._current_user,
                    settings_service=self._settings_service,
                )
                self._settings_page = page
            else:
                page = QWidget()
                page_layout = QVBoxLayout(page)
                page_layout.setAlignment(Qt.AlignCenter)
                placeholder = QLabel(f"{label} Module")
                placeholder.setObjectName("placeholderLabel")
                placeholder.setAlignment(Qt.AlignCenter)
                page_layout.addWidget(placeholder)
            self.stack.addWidget(page)

        self.navigate_to("dashboard")

    def toggle_sidebar(self):
        """Toggle the sidebar between expanded (240px) and collapsed (72px) states."""
        self.set_sidebar_collapsed(not self._sidebar_collapsed, animated=True)

    def set_sidebar_collapsed(self, collapsed: bool, animated: bool = True):
        """Set the sidebar collapsed state using PySide6 QPropertyAnimation."""
        if self._sidebar_collapsed == collapsed and animated:
            return

        self._sidebar_collapsed = collapsed
        target_width = 72 if collapsed else 240
        start_width = self.sidebar.width()

        # Stop existing animation if running
        if self._anim_group and self._anim_group.state() == QParallelAnimationGroup.Running:
            self._anim_group.stop()

        self._anim_group = QParallelAnimationGroup(self)

        # Width Animation for minimumWidth
        min_anim = QPropertyAnimation(self.sidebar, b"minimumWidth", self)
        min_anim.setDuration(200)
        min_anim.setStartValue(start_width)
        min_anim.setEndValue(target_width)
        min_anim.setEasingCurve(QEasingCurve.InOutCubic)

        # Width Animation for maximumWidth
        max_anim = QPropertyAnimation(self.sidebar, b"maximumWidth", self)
        max_anim.setDuration(200)
        max_anim.setStartValue(start_width)
        max_anim.setEndValue(target_width)
        max_anim.setEasingCurve(QEasingCurve.InOutCubic)

        self._anim_group.addAnimation(min_anim)
        self._anim_group.addAnimation(max_anim)

        # Opacity animation for text labels & elements
        opacity_end = 0.0 if collapsed else 1.0

        for effect in self._opacity_effects:
            op_anim = QPropertyAnimation(effect, b"opacity", self)
            op_anim.setDuration(180)
            op_anim.setStartValue(effect.opacity())
            op_anim.setEndValue(opacity_end)
            op_anim.setEasingCurve(QEasingCurve.InOutCubic)
            self._anim_group.addAnimation(op_anim)

        for nav_item in self.nav_buttons.values():
            op_anim = QPropertyAnimation(nav_item.opacity_effect, b"opacity", self)
            op_anim.setDuration(180)
            op_anim.setStartValue(nav_item.opacity_effect.opacity())
            op_anim.setEndValue(opacity_end)
            op_anim.setEasingCurve(QEasingCurve.InOutCubic)
            self._anim_group.addAnimation(op_anim)

        # Update layout margins and widget visibility for header and avatar card
        if collapsed:
            self.sidebar_logo_lbl.setVisible(False)
            self.sidebar_hdr_l.setContentsMargins(21, 0, 21, 0)
            self.card_l.setContentsMargins(20, 6, 20, 6)
        else:
            self.sidebar_logo_lbl.setVisible(True)
            self.sidebar_hdr_l.setContentsMargins(14, 0, 8, 0)
            self.card_l.setContentsMargins(12, 6, 12, 6)

        # Button icon & tooltip updates
        icon_name = "chevron_right" if collapsed else "chevron_left"
        self.sidebar_toggle_btn.setIcon(IconManager.get_icon(icon_name, color="#94a3b8", size=16))
        self.sidebar_toggle_btn.setToolTip("Expand Sidebar" if collapsed else "Collapse Sidebar")
        self.sidebar_title_lbl.setText("" if collapsed else "RetailFlow POS")

        self.update_sidebar_tooltips()

        if animated:
            self._anim_group.start()
        else:
            self.sidebar.setMinimumWidth(target_width)
            self.sidebar.setMaximumWidth(target_width)
            for effect in self._opacity_effects:
                effect.setOpacity(opacity_end)
            for nav_item in self.nav_buttons.values():
                nav_item.opacity_effect.setOpacity(opacity_end)

    def update_sidebar_tooltips(self):
        """Update tooltips depending on sidebar collapse state."""
        collapsed = self._sidebar_collapsed
        for key, nav_item in self.nav_buttons.items():
            if collapsed:
                nav_item.setToolTip(nav_item.label_text)
            else:
                nav_item.setToolTip("")

        if collapsed:
            name = self._current_user.full_name if self._current_user else "System Admin"
            role = self._current_user.role.name.capitalize() if (self._current_user and hasattr(self._current_user, "role") and self._current_user.role) else "Administrator"
            self.sidebar_profile_card.setToolTip(f"{name} ({role})")
        else:
            self.sidebar_profile_card.setToolTip("")

    def update_navigation_state(self):
        """Refresh active page indicators and styling."""
        for key, nav_item in self.nav_buttons.items():
            nav_item.set_active(key == self._current_page)

    def _show_user_menu(self, event=None):
        """Display interactive user profile popup menu."""
        menu = QMenu(self)
        menu.setObjectName("userProfileMenu")
        menu.setStyleSheet("""
            QMenu#userProfileMenu {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu#userProfileMenu::item {
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                color: #0f172a;
            }
            QMenu#userProfileMenu::item:selected {
                background-color: #f1f5f9;
                color: #2563eb;
            }
        """)

        full_name = self._current_user.full_name if self._current_user else "System Administrator"
        role_name = "ADMIN"
        if self._current_user and hasattr(self._current_user, "role") and self._current_user.role:
            role_name = self._current_user.role.name.upper()

        hdr_action = QAction(f"{full_name}  ·  [{role_name}]", self)
        hdr_action.setIcon(IconManager.get_icon("users", color="#2563eb", size=16))
        hdr_action.setEnabled(False)
        menu.addAction(hdr_action)
        menu.addSeparator()

        if self._has_permission("view_settings"):
            settings_action = QAction("Settings", self)
            settings_action.setIcon(IconManager.get_icon("settings", color="#475569", size=16))
            settings_action.triggered.connect(lambda: self.navigate_to("settings"))
            menu.addAction(settings_action)

        logout_action = QAction("Log Out", self)
        logout_action.setIcon(IconManager.get_icon("log_out", color="#dc2626", size=16))
        logout_action.triggered.connect(self.close)
        menu.addAction(logout_action)

        target_widget = self.sidebar_profile_card if hasattr(self, "sidebar_profile_card") else self.user_btn
        pos = target_widget.mapToGlobal(target_widget.rect().topRight())
        menu.exec(pos)

    def navigate_to(self, page_key: str):
        """Navigate to a page by its key."""
        if page_key == self._current_page:
            return

        # 1. Navigation leave guard for unsaved settings changes
        if self._current_page == "settings" and getattr(self, "_settings_page", None) is not None:
            if self._settings_page.has_unsaved_changes():
                reply = QMessageBox.warning(
                    self,
                    "Unsaved Settings Changes",
                    "You have unsaved Settings changes.\n\nDo you want to discard your changes and continue?",
                    QMessageBox.Discard | QMessageBox.Cancel,
                    QMessageBox.Cancel,
                )
                if reply == QMessageBox.Cancel:
                    return
                self._settings_page.discard_changes()

        # 2. Permission check for target page
        if page_key == "settings" and not self._has_permission("view_settings"):
            return

        self._current_page = page_key
        self.update_navigation_state()

        # Find and show the matching page
        for i, (_, key, _) in enumerate(NAV_ITEMS):
            if key == page_key:
                self.stack.setCurrentIndex(i)
                self.page_title.setText(NAV_ITEMS[i][0])
                break

    def _update_user_display(self):
        """Update user profile displays in top bar and sidebar card."""
        if self._current_user:
            name = self._current_user.full_name or "User"
            initials = "".join([w[0].upper() for w in name.split()[:2]]) if name else "U"
            role = "Cashier"
            if hasattr(self._current_user, "role") and self._current_user.role:
                role = self._current_user.role.name.capitalize()

            self.avatar_lbl.setText(initials[0])
            self.name_lbl.setText(name.split()[0])

            self.sb_avatar_lbl.setText(initials)
            self.sb_name_lbl.setText(name)
            self.sb_role_lbl.setText(role)
        else:
            self.avatar_lbl.setText("S")
            self.name_lbl.setText("System")
            self.sb_avatar_lbl.setText("SA")
            self.sb_name_lbl.setText("System Admin")
            self.sb_role_lbl.setText("Administrator")

    def _has_permission(self, code: str) -> bool:
        """Check the current user's permission."""
        if not self._current_user:
            return False
        if hasattr(self._current_user, "is_admin") and self._current_user.is_admin():
            return True
        return bool(self._current_user.has_permission(code))

    def closeEvent(self, event):  # noqa: N802
        """Close the window-owned database session on exit after prompting for unsaved settings."""
        if getattr(self, "_settings_page", None) is not None and self._settings_page.has_unsaved_changes():
            reply = QMessageBox.warning(
                self,
                "Unsaved Settings Changes",
                "You have unsaved Settings changes.\n\nDo you want to discard your changes and exit?",
                QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if reply == QMessageBox.Cancel:
                event.ignore()
                return

        if getattr(self, "_owns_session", True):
            self._session.close()
        super().closeEvent(event)

    def get_current_user_display(self) -> str:
        """Returns the current user display name."""
        if self._current_user:
            return self._current_user.full_name
        return "Unknown"
