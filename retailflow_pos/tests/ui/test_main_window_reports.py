"""
RetailFlow POS - MainWindow Reports Integration & E2E Verification Tests (Phase 7)
Tests MainWindow service injection, sidebar routing, role-aware permission enforcement,
page reuse, real database financial flow (Sales COGS, OPEX, Voiding, Purchasing anti-double-counting),
Manila timezone boundary preservation, and CSV export from the integrated UI.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
import os
import tempfile
import time

import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QApplication

from app.constants import ExpenseCategory, ExpenseStatus
from application.dto.expense_dto import CreateExpenseDTO, VoidExpenseDTO
from application.dto.product_dto import ProductFormDTO
from application.dto.purchasing_dto import CreatePOItemDTO, CreatePurchaseOrderDTO
from application.dto.report_dto import FinancialSummaryDTO
from application.dto.sales_dto import CartItemDTO, CheckoutRequestDTO
from application.services.expense_service import ExpenseService
from application.services.product_service import ProductService
from application.services.purchasing_service import PurchasingService
from application.services.report_export_service import ReportExportService
from application.services.report_service import ReportService
from application.services.sales_service import SalesService
from domain.exceptions import AuthorizationError
from infrastructure.database.models.auth import Permission, Role, User
from infrastructure.database.models.inventory import Inventory
from infrastructure.database.models.product import Product
from infrastructure.database.models.supplier import Supplier
from infrastructure.database.seeders.auth_seeder import seed_auth
from infrastructure.database.seeders.expense_seeder import seed_expenses
from presentation.widgets.reports_page import ReportsPage
from presentation.windows.main_window import MainWindow


@pytest.fixture(autouse=True)
def setup_seed_data(db_session):
    """Seed authentication and demo expenses."""
    seed_auth(db_session)
    seed_expenses(db_session)
    db_session.commit()


@pytest.fixture
def admin_user(db_session):
    return db_session.query(User).filter(User.username == "admin").first()


@pytest.fixture
def manager_user(db_session):
    return db_session.query(User).filter(User.username == "manager").first()


@pytest.fixture
def cashier_user(db_session):
    return db_session.query(User).filter(User.username == "cashier").first()


@pytest.fixture
def auditor_user(db_session):
    role_auditor = db_session.query(Role).filter(Role.code == "auditor").first()
    if not role_auditor:
        perm_view = db_session.query(Permission).filter(Permission.code == "view_reports").first()
        perm_export = db_session.query(Permission).filter(Permission.code == "export_reports").first()
        role_auditor = Role(name="Auditor", code="auditor", permissions=[perm_view, perm_export])
        db_session.add(role_auditor)
        db_session.flush()

    auditor = User(
        username="auditor_test",
        password_hash="dummy",
        full_name="Auditor User",
        roles=[role_auditor],
    )
    db_session.add(auditor)
    db_session.commit()
    return auditor


# ── 1. Service Injection & Routing ──────────────────────────────────

def test_main_window_reports_service_injection_and_routing(qtbot, db_session, admin_user):
    """MainWindow instantiates ReportService and ReportExportService and routes to ReportsPage."""
    window = MainWindow(current_user=admin_user, session=db_session)
    qtbot.addWidget(window)
    window.show()

    # 1. Dependency injection checks
    assert hasattr(window, "_report_service")
    assert isinstance(window._report_service, ReportService)
    assert hasattr(window, "_report_export_service")
    assert isinstance(window._report_export_service, ReportExportService)

    # 2. Navigation item checks
    assert "reports" in window.nav_buttons
    nav_item = window.nav_buttons["reports"]
    assert not nav_item.is_disabled

    # 3. Route navigation
    window.navigate_to("reports")
    current_page = window.stack.currentWidget()
    assert isinstance(current_page, ReportsPage)
    assert window.page_title.text() == "Reports"


def test_main_window_reports_page_lifecycle_and_reuse(qtbot, db_session, admin_user):
    """Navigating away and back reuses the exact same page instance in QStackedWidget."""
    window = MainWindow(current_user=admin_user, session=db_session)
    qtbot.addWidget(window)
    window.show()

    window.navigate_to("reports")
    reports_page_1 = window.stack.currentWidget()

    window.navigate_to("dashboard")
    assert window.stack.currentWidget() != reports_page_1

    window.navigate_to("products")
    assert window.stack.currentWidget() != reports_page_1

    window.navigate_to("reports")
    reports_page_2 = window.stack.currentWidget()

    # Exactly same instance preserved
    assert reports_page_1 is reports_page_2


# ── 2. Role Access Matrix ───────────────────────────────────────────

def test_main_window_reports_role_access_matrix(qtbot, db_session, admin_user, manager_user, auditor_user, cashier_user):
    """Admin, Manager, and Auditor can access Reports & Export; Cashier is disabled and denied."""
    # 1. Admin (Visible & Enabled)
    win_admin = MainWindow(current_user=admin_user, session=db_session)
    qtbot.addWidget(win_admin)
    win_admin.show()
    assert win_admin.nav_buttons["reports"].isVisible()
    assert not win_admin.nav_buttons["reports"].is_disabled

    # 2. Manager (Visible & Enabled)
    win_manager = MainWindow(current_user=manager_user, session=db_session)
    qtbot.addWidget(win_manager)
    win_manager.show()
    assert win_manager.nav_buttons["reports"].isVisible()
    assert not win_manager.nav_buttons["reports"].is_disabled

    # 3. Auditor (Visible & Enabled)
    win_auditor = MainWindow(current_user=auditor_user, session=db_session)
    qtbot.addWidget(win_auditor)
    win_auditor.show()
    assert win_auditor.nav_buttons["reports"].isVisible()
    assert not win_auditor.nav_buttons["reports"].is_disabled

    # 4. Cashier (Restricted: Hidden / Not Visible)
    win_cashier = MainWindow(current_user=cashier_user, session=db_session)
    qtbot.addWidget(win_cashier)
    win_cashier.show()
    assert not win_cashier.nav_buttons["reports"].isVisible()

    # Programmatic service access also fails for Cashier
    with pytest.raises(AuthorizationError):
        win_cashier._report_service.get_financial_summary(date.today(), date.today(), actor=cashier_user)


# ── 3. Real Database Financial Pipeline E2E ─────────────────────────

def test_main_window_reports_real_sales_and_expenses_pipeline(qtbot, db_session, admin_user):
    """End-to-End verification of Sales COGS, OPEX, and Net Operating Profit with live database."""
    prod_service = ProductService(db_session)
    sales_service = SalesService(db_session)
    exp_service = ExpenseService(db_session)

    # 1. Create a product: Cost ₱100, Price ₱250
    prod = prod_service.create(
        ProductFormDTO(
            sku="MW-RPT-PROD-1",
            name="E2E Analytics Widget",
            cost_price=Decimal("100.00"),
            selling_price=Decimal("250.00"),
            reorder_level=5,
        ),
        actor=admin_user,
    )
    # Ensure inventory row exists with 50 units
    inv = db_session.query(Inventory).filter(Inventory.product_id == prod.id).first()
    if not inv:
        inv = Inventory(product_id=prod.id, quantity_on_hand=50)
        db_session.add(inv)
    else:
        inv.quantity_on_hand = 50
    db_session.commit()

    # 2. Process a Sale: 2 units @ ₱250 = Gross ₱500, COGS = ₱200, Profit = ₱300
    cart_item = CartItemDTO(
        product_id=prod.id,
        sku="MW-RPT-PROD-1",
        name="E2E Analytics Widget",
        unit_price=Decimal("250.00"),
        quantity=2,
        available_stock=50,
    )
    sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[cart_item],
            payment_method="CASH",
            amount_tendered=Decimal("560.00"),
            discount_amount=Decimal("0.00"),
            cashier_id=admin_user.id,
        ),
        actor=admin_user,
    )

    # 3. Record an Expense: ₱50
    exp = exp_service.create_expense(
        CreateExpenseDTO(
            category=ExpenseCategory.SUPPLIES.value,
            title="Packaging Bags for E2E",
            payee="Supplier Co",
            amount=Decimal("50.00"),
            expense_date=date.today(),
            payment_method="cash",
        ),
        actor=admin_user,
    )

    # Open MainWindow
    window = MainWindow(current_user=admin_user, session=db_session)
    qtbot.addWidget(window)
    window.show()

    window.navigate_to("reports")
    page: ReportsPage = window.stack.currentWidget()

    # Set range to Today
    page._preset_buttons["today"].click()
    QApplication.processEvents()

    # Verify KPI / P&L Bindings
    # Net Sales = ₱500, COGS = ₱200, Gross Profit = ₱300, OPEX = ₱50, Net Operating Profit = ₱250
    assert page._current_summary is not None
    assert page._current_summary.net_sales == Decimal("500.00")
    assert page._current_summary.cogs == Decimal("200.00")
    assert page._current_summary.gross_profit == Decimal("300.00")
    assert page._current_summary.operating_expenses == Decimal("50.00")
    assert page._current_summary.net_operating_profit == Decimal("250.00")

    # 4. VOID the Expense and refresh
    exp_service.void_expense(
        VoidExpenseDTO(expense_id=exp.id, void_reason="Incorrect disbursement voucher for E2E test"),
        actor=admin_user,
    )

    page.btn_refresh.click()
    QApplication.processEvents()

    # OPEX drops to ₱0.00, Net Operating Profit returns to ₱300.00
    assert page._current_summary.operating_expenses == Decimal("0.00")
    assert page._current_summary.net_operating_profit == Decimal("300.00")


# ── 4. COGS Immutability & Purchasing Anti-Double-Counting ───────────

def test_main_window_reports_cogs_immutability_and_purchasing_anti_double_count(qtbot, db_session, admin_user):
    """Product cost changes after sale do not alter historical COGS, and received POs do not reduce OPEX."""
    prod_service = ProductService(db_session)
    sales_service = SalesService(db_session)
    purch_service = PurchasingService(db_session)

    # 1. Product at Cost ₱50, Price ₱100
    prod = prod_service.create(
        ProductFormDTO(
            sku="IMMUTABLE-COGS-1",
            name="Immutable COGS Test Item",
            cost_price=Decimal("50.00"),
            selling_price=Decimal("100.00"),
            reorder_level=10,
        ),
        actor=admin_user,
    )
    inv = db_session.query(Inventory).filter(Inventory.product_id == prod.id).first()
    if not inv:
        inv = Inventory(product_id=prod.id, quantity_on_hand=100)
        db_session.add(inv)
    else:
        inv.quantity_on_hand = 100
    db_session.commit()

    # 2. Sell 2 units -> COGS = ₱100
    cart_item = CartItemDTO(
        product_id=prod.id,
        sku="IMMUTABLE-COGS-1",
        name="Immutable COGS Test Item",
        unit_price=Decimal("100.00"),
        quantity=2,
        available_stock=100,
    )
    sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[cart_item],
            payment_method="CASH",
            amount_tendered=Decimal("224.00"),
            discount_amount=Decimal("0.00"),
            cashier_id=admin_user.id,
        ),
        actor=admin_user,
    )

    # 3. Update Product cost price to ₱80 (simulating later supplier price increase)
    prod_orm = db_session.get(Product, prod.id)
    prod_orm.cost_price = Decimal("80.00")
    db_session.commit()

    # 4. Create Supplier and Receive a Purchase Order of 50 units @ ₱80 = ₱4,000 inventory
    supplier = Supplier(
        code="SUP-E2E-01",
        name="E2E Test Wholesale Supplier",
        phone="09171234567",
        payment_terms="NET_30",
    )
    db_session.add(supplier)
    db_session.commit()

    po = purch_service.create_po(
        CreatePurchaseOrderDTO(
            supplier_id=supplier.id,
            items=[CreatePOItemDTO(product_id=prod.id, quantity=50, unit_cost=Decimal("80.00"))],
            notes="Inventory intake PO",
        ),
        actor=admin_user,
    )
    purch_service.receive_stock(po.id, actor=admin_user)

    # Open MainWindow
    window = MainWindow(current_user=admin_user, session=db_session)
    qtbot.addWidget(window)
    window.show()

    window.navigate_to("reports")
    page: ReportsPage = window.stack.currentWidget()
    page._preset_buttons["today"].click()
    QApplication.processEvents()

    # Historical COGS must remain ₱100.00 (NOT 2 * ₱80 = ₱160.00)
    assert page._current_summary.cogs == Decimal("100.00")
    assert page._current_summary.gross_profit == Decimal("100.00")

    # Received Purchasing Intake shows ₱4,000.00 asset addition
    assert page._current_purchasing.received_purchase_value == Decimal("4000.00")

    # Anti-double-count: Net Operating Profit is NOT reduced by the ₱4,000 purchase order!
    assert page._current_summary.operating_expenses == Decimal("0.00")
    assert page._current_summary.net_operating_profit == Decimal("100.00")


# ── 5. Timezone Boundary E2E ─────────────────────────────────────────

def test_main_window_reports_asia_manila_timezone_boundary(qtbot, db_session, admin_user):
    """Transactions created at Manila midnight boundary (UTC previous day) are included in Manila date report."""
    prod_service = ProductService(db_session)
    sales_service = SalesService(db_session)

    prod = prod_service.create(
        ProductFormDTO(
            sku="TZ-TEST-PROD",
            name="Timezone Boundary Item",
            cost_price=Decimal("10.00"),
            selling_price=Decimal("20.00"),
            reorder_level=2,
        ),
        actor=admin_user,
    )
    inv = db_session.query(Inventory).filter(Inventory.product_id == prod.id).first()
    if not inv:
        inv = Inventory(product_id=prod.id, quantity_on_hand=20)
        db_session.add(inv)
    else:
        inv.quantity_on_hand = 20
    db_session.commit()

    # Create sale
    cart_item = CartItemDTO(
        product_id=prod.id,
        sku="TZ-TEST-PROD",
        name="Timezone Boundary Item",
        unit_price=Decimal("20.00"),
        quantity=1,
        available_stock=20,
    )
    sale_resp = sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[cart_item],
            payment_method="CASH",
            amount_tendered=Decimal("22.40"),
            discount_amount=Decimal("0.00"),
            cashier_id=admin_user.id,
        ),
        actor=admin_user,
    )

    # Force timestamp to Aug 14 16:30:00 UTC (= Aug 15 00:30:00 Asia/Manila)
    from infrastructure.database.models.sales import Sale
    sale_orm = db_session.get(Sale, sale_resp.id)
    sale_orm.created_at = datetime(2026, 8, 14, 16, 30, 0)
    db_session.commit()

    window = MainWindow(current_user=admin_user, session=db_session)
    qtbot.addWidget(window)
    window.show()

    window.navigate_to("reports")
    page: ReportsPage = window.stack.currentWidget()

    # Query for Aug 15, 2026
    page._preset_buttons["custom"].click()
    page.dt_start.setDate(QDate(2026, 8, 15))
    page.dt_end.setDate(QDate(2026, 8, 15))
    QApplication.processEvents()

    # Sale must be captured in Aug 15 Manila report
    assert page._current_summary.gross_sales == Decimal("20.00")
    assert page._current_summary.net_sales == Decimal("20.00")


# ── 6. Integrated CSV Export E2E ─────────────────────────────────────

def test_main_window_reports_csv_export_e2e(qtbot, db_session, admin_user):
    """Exporting CSV from the integrated MainWindow saves UTF-8-SIG encoded files with accurate data."""
    window = MainWindow(current_user=admin_user, session=db_session)
    qtbot.addWidget(window)
    window.show()

    window.navigate_to("reports")
    page: ReportsPage = window.stack.currentWidget()

    with tempfile.TemporaryDirectory() as tmp_dir:
        fin_path = os.path.join(tmp_dir, "export_fin_summary.csv")
        prod_path = os.path.join(tmp_dir, "export_prod_leaderboard.csv")

        # Export Financial Summary
        start_d, end_d = page._get_active_date_range()
        page._report_export_service.export_financial_summary_csv(
            start_date=start_d,
            end_date=end_d,
            actor=admin_user,
            target_path=fin_path,
        )

        assert os.path.exists(fin_path)
        with open(fin_path, "rb") as f:
            raw = f.read()
            assert raw.startswith(b"\xef\xbb\xbf")  # UTF-8-SIG BOM
            content = raw.decode("utf-8-sig")
            assert "RetailFlow POS - Executive Financial Summary" in content

        # Export Product Performance
        page._report_export_service.export_product_performance_csv(
            start_date=start_d,
            end_date=end_d,
            actor=admin_user,
            target_path=prod_path,
        )
        assert os.path.exists(prod_path)


# ── 7. Responsive Layout Smoke Test ──────────────────────────────────

def test_main_window_reports_responsive_viewport_mode(qtbot, db_session, admin_user):
    """ReportsPage dynamically reflects available content width inside MainWindow."""
    window = MainWindow(current_user=admin_user, session=db_session)
    qtbot.addWidget(window)
    window.show()

    window.navigate_to("reports")
    page: ReportsPage = window.stack.currentWidget()

    # Small screen (1024x580) -> Page content width is < 1180px -> Compact mode active
    page.resize(1000, 600)
    QApplication.processEvents()
    assert page.width() < ReportsPage.BREAKPOINT_WIDTH
    assert page._is_compact_layout is True

    # Large screen (1400x900) -> Page content width > 1180px -> Wide mode active
    page.resize(1400, 900)
    QApplication.processEvents()
    assert page.width() >= ReportsPage.BREAKPOINT_WIDTH
    assert page._is_compact_layout is False


# ── 8. Performance Smoke Test ────────────────────────────────────────

def test_main_window_reports_initial_load_performance(qtbot, db_session, admin_user):
    """Initial production load of MainWindow Reports page executes rapidly under 2000ms."""
    start_time = time.perf_counter()

    window = MainWindow(current_user=admin_user, session=db_session)
    qtbot.addWidget(window)
    window.show()
    window.navigate_to("reports")
    QApplication.processEvents()

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    # Ensure rapid responsiveness
    assert elapsed_ms < 2000.0  # Generous upper bound for GUI initialization
    assert window.stack.currentWidget() is not None
