"""
RetailFlow POS - ReportService Integration Tests
Comprehensive verification of all financial calculations, Profit & Loss reporting,
Asia/Manila business-day timezone conversion, midnight/year-end boundaries, continuous
timeline zero-filling, cashier performance, product analytics, and inventory valuations.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
import pytest

from application.dto.sales_dto import CartItemDTO, CheckoutRequestDTO
from application.services.expense_service import ExpenseService
from application.services.report_service import ReportService
from application.services.sales_service import SalesService
from domain.exceptions import AuthorizationError, ValidationError
from infrastructure.database.models.auth import Permission, Role, User
from infrastructure.database.models.expense import Expense
from infrastructure.database.models.inventory import Inventory
from infrastructure.database.models.product import Product
from infrastructure.database.models.purchasing import PurchaseOrder, PurchaseOrderItem
from infrastructure.database.models.sales import Sale, SaleLineItem
from infrastructure.database.models.supplier import Supplier


@pytest.fixture
def report_test_env(db_session):
    """Set up test users (Admin, Manager, Cashier, Restricted), products, inventory, and services."""
    # 1. Permissions
    perm_report = Permission(code="view_reports", name="View Reports", module="reports")
    perm_sale = Permission(code="process_sale", name="Process Sale", module="sales")
    perm_view_exp = Permission(code="view_expenses", name="View Expenses", module="expenses")
    db_session.add_all([perm_report, perm_sale, perm_view_exp])
    db_session.flush()

    role_mgr = Role(name="Manager Role", code="manager_role", permissions=[perm_report, perm_sale, perm_view_exp])
    role_cashier = Role(name="Cashier Role", code="cashier_role", permissions=[perm_sale])
    db_session.add_all([role_mgr, role_cashier])
    db_session.flush()

    user_mgr = User(username="mgr_alice", password_hash="hash", full_name="Alice Manager", roles=[role_mgr])
    user_cashier1 = User(username="csh_bob", password_hash="hash", full_name="Bob Cashier", roles=[role_cashier])
    user_cashier2 = User(username="csh_charlie", password_hash="hash", full_name="Charlie Cashier", roles=[role_cashier])
    user_restricted = User(username="usr_restricted", password_hash="hash", full_name="Restricted User", roles=[role_cashier])
    db_session.add_all([user_mgr, user_cashier1, user_cashier2, user_restricted])
    db_session.flush()

    # 2. Products & Inventory
    # Prod 1: Cost ₱60.00, Sell ₱100.00, Stock 50
    prod1 = Product(sku="RPT-P1", name="Product One", cost_price=Decimal("60.00"), selling_price=Decimal("100.00"), status="active")
    # Prod 2: Cost ₱25.00, Sell ₱50.00, Stock 100
    prod2 = Product(sku="RPT-P2", name="Product Two", cost_price=Decimal("25.00"), selling_price=Decimal("50.00"), status="active")
    # Prod 3: Cost ₱10.00, Sell ₱20.00, Stock 0 (Out of stock)
    prod3 = Product(sku="RPT-P3", name="Product Three", cost_price=Decimal("10.00"), selling_price=Decimal("20.00"), status="active")
    db_session.add_all([prod1, prod2, prod3])
    db_session.flush()

    inv1 = Inventory(product_id=prod1.id, quantity_on_hand=50)
    inv2 = Inventory(product_id=prod2.id, quantity_on_hand=100)
    inv3 = Inventory(product_id=prod3.id, quantity_on_hand=0)
    db_session.add_all([inv1, inv2, inv3])
    db_session.commit()

    return {
        "user_mgr": user_mgr,
        "user_cashier1": user_cashier1,
        "user_cashier2": user_cashier2,
        "user_restricted": user_restricted,
        "prod1": prod1,
        "prod2": prod2,
        "prod3": prod3,
    }


def test_financial_summary_empty_period(db_session, report_test_env):
    """Empty date range returns zero values and 0.00% margins without error."""
    report_service = ReportService(db_session)
    start = date(2026, 1, 1)
    end = date(2026, 1, 7)

    summary = report_service.get_financial_summary(start, end)
    assert summary.gross_sales == Decimal("0.00")
    assert summary.discounts == Decimal("0.00")
    assert summary.net_sales == Decimal("0.00")
    assert summary.output_vat == Decimal("0.00")
    assert summary.total_collections == Decimal("0.00")
    assert summary.cogs == Decimal("0.00")
    assert summary.gross_profit == Decimal("0.00")
    assert summary.gross_margin_percent == Decimal("0.00")
    assert summary.operating_expenses == Decimal("0.00")
    assert summary.net_operating_profit == Decimal("0.00")
    assert summary.net_operating_margin_percent == Decimal("0.00")


def test_financial_summary_full_pl_pipeline(db_session, report_test_env):
    """
    Test complete P&L calculation:
    Sale: 2x Prod 1 (Sell ₱100, Cost ₱60) + 2x Prod 2 (Sell ₱50, Cost ₱25)
    Subtotal: ₱300.00
    Discount: ₱50.00
    Taxable: ₱250.00
    Output VAT (12%): ₱30.00
    Total Collections: ₱280.00
    Net Sales: ₱300.00 - ₱50.00 = ₱250.00
    COGS: 2x ₱60 + 2x ₱25 = ₱170.00
    Gross Profit: ₱250.00 - ₱170.00 = ₱80.00
    Gross Margin %: 80 / 250 * 100 = 32.00%

    Expenses: 1 PAID expense of ₱30.00, 1 VOID expense of ₱50.00
    OPEX: ₱30.00 (VOID excluded)
    Net Operating Profit: ₱80.00 - ₱30.00 = ₱50.00
    Net Operating Margin %: 50 / 250 * 100 = 20.00%
    """
    env = report_test_env
    sales_service = SalesService(db_session)
    report_service = ReportService(db_session)

    today = date(2026, 8, 15)

    # 1. Process Sale
    request = CheckoutRequestDTO(
        items=[
            CartItemDTO(product_id=env["prod1"].id, sku=env["prod1"].sku, name=env["prod1"].name, unit_price=Decimal("100.00"), quantity=2),
            CartItemDTO(product_id=env["prod2"].id, sku=env["prod2"].sku, name=env["prod2"].name, unit_price=Decimal("50.00"), quantity=2),
        ],
        payment_method="GCASH",
        amount_tendered=Decimal("300.00"),
        discount_amount=Decimal("50.00"),
    )
    sale_resp = sales_service.process_checkout(request, env["user_cashier1"])

    # Overwrite created_at to exact UTC time (10:30 AM Manila = 02:30 UTC)
    sale_db = db_session.query(Sale).filter(Sale.id == sale_resp.id).first()
    sale_db.created_at = datetime(2026, 8, 15, 2, 30, 0)
    db_session.commit()

    # 2. Add Expenses (1 PAID, 1 VOID)
    exp_paid = Expense(
        voucher_number="EXP-20260815-0001",
        category="utilities",
        title="Water Bill",
        payee="Water Corp",
        amount=Decimal("30.00"),
        payment_method="CASH",
        expense_date=today,
        status="paid",
    )
    exp_void = Expense(
        voucher_number="EXP-20260815-0002",
        category="supplies",
        title="Mistaken Supplies",
        payee="Supply Co",
        amount=Decimal("50.00"),
        payment_method="CASH",
        expense_date=today,
        status="void",
        void_reason="Duplicate voucher",
    )
    db_session.add_all([exp_paid, exp_void])
    db_session.commit()

    # 3. Query Financial Summary
    summary = report_service.get_financial_summary(today, today)
    assert summary.gross_sales == Decimal("300.00")
    assert summary.discounts == Decimal("50.00")
    assert summary.net_sales == Decimal("250.00")
    assert summary.output_vat == Decimal("30.00")
    assert summary.total_collections == Decimal("280.00")
    assert summary.cogs == Decimal("170.00")
    assert summary.gross_profit == Decimal("80.00")
    assert summary.gross_margin_percent == Decimal("32.00")
    assert summary.operating_expenses == Decimal("30.00")
    assert summary.net_operating_profit == Decimal("50.00")
    assert summary.net_operating_margin_percent == Decimal("20.00")


def test_manila_midnight_boundary_cases(db_session, report_test_env):
    """
    Controlled Asia/Manila Midnight Boundary Verification:
    Requested Manila Reporting Day: Aug 15, 2026.
    
    Case A: Sale at Aug 15 00:00:00 Manila (UTC Aug 14 16:00:00) -> INCLUDED in Aug 15
    Case B: Sale at Aug 15 00:30:00 Manila (UTC Aug 14 16:30:00) -> INCLUDED in Aug 15
    Case C: Sale at Aug 15 23:59:59 Manila (UTC Aug 15 15:59:59) -> INCLUDED in Aug 15
    Case D: Sale at Aug 16 00:00:00 Manila (UTC Aug 15 16:00:00) -> EXCLUDED from Aug 15 (belongs to Aug 16)
    """
    env = report_test_env
    report_service = ReportService(db_session)

    # Case A (Aug 15 00:00 Manila -> UTC Aug 14 16:00:00)
    sa = Sale(
        transaction_number="TXN-CASE-A", subtotal=Decimal("100.00"), discount_amount=Decimal("0.00"),
        total_amount=Decimal("112.00"), status="COMPLETED", payment_method="CASH",
        created_at=datetime(2026, 8, 14, 16, 0, 0),
        items=[SaleLineItem(product_id=env["prod1"].id, product_name=env["prod1"].name, unit_price=Decimal("100.00"), unit_cost=Decimal("60.00"), quantity=1, subtotal=Decimal("100.00"))],
    )
    # Case B (Aug 15 00:30 Manila -> UTC Aug 14 16:30:00)
    sb = Sale(
        transaction_number="TXN-CASE-B", subtotal=Decimal("100.00"), discount_amount=Decimal("0.00"),
        total_amount=Decimal("112.00"), status="COMPLETED", payment_method="CASH",
        created_at=datetime(2026, 8, 14, 16, 30, 0),
        items=[SaleLineItem(product_id=env["prod1"].id, product_name=env["prod1"].name, unit_price=Decimal("100.00"), unit_cost=Decimal("60.00"), quantity=1, subtotal=Decimal("100.00"))],
    )
    # Case C (Aug 15 23:59:59 Manila -> UTC Aug 15 15:59:59)
    sc = Sale(
        transaction_number="TXN-CASE-C", subtotal=Decimal("100.00"), discount_amount=Decimal("0.00"),
        total_amount=Decimal("112.00"), status="COMPLETED", payment_method="CASH",
        created_at=datetime(2026, 8, 15, 15, 59, 59),
        items=[SaleLineItem(product_id=env["prod1"].id, product_name=env["prod1"].name, unit_price=Decimal("100.00"), unit_cost=Decimal("60.00"), quantity=1, subtotal=Decimal("100.00"))],
    )
    # Case D (Aug 16 00:00:00 Manila -> UTC Aug 15 16:00:00)
    sd = Sale(
        transaction_number="TXN-CASE-D", subtotal=Decimal("100.00"), discount_amount=Decimal("0.00"),
        total_amount=Decimal("112.00"), status="COMPLETED", payment_method="CASH",
        created_at=datetime(2026, 8, 15, 16, 0, 0),
        items=[SaleLineItem(product_id=env["prod1"].id, product_name=env["prod1"].name, unit_price=Decimal("100.00"), unit_cost=Decimal("60.00"), quantity=1, subtotal=Decimal("100.00"))],
    )
    db_session.add_all([sa, sb, sc, sd])
    db_session.commit()

    # Query for Aug 15 (Manila Day)
    summary_15 = report_service.get_financial_summary(date(2026, 8, 15), date(2026, 8, 15))
    assert summary_15.gross_sales == Decimal("300.00"), "Aug 15 report must include Case A, B, and C (₱300) and exclude Case D!"
    assert summary_15.cogs == Decimal("180.00")

    # Query for Aug 16 (Manila Day)
    summary_16 = report_service.get_financial_summary(date(2026, 8, 16), date(2026, 8, 16))
    assert summary_16.gross_sales == Decimal("100.00"), "Aug 16 report must include Case D (₱100)!"

    # Test Daily Trend grouping for Aug 15 to Aug 16
    trend = report_service.get_daily_financial_trend(date(2026, 8, 15), date(2026, 8, 16))
    assert len(trend) == 2
    assert trend[0].date == "2026-08-15"
    assert trend[0].net_sales == Decimal("300.00")
    assert trend[1].date == "2026-08-16"
    assert trend[1].net_sales == Decimal("100.00")


def test_manila_month_and_year_end_boundaries(db_session, report_test_env):
    """
    Verify Year-End & New Year Boundary:
    Sale 1: Dec 31, 2026 23:59:00 Manila (UTC Dec 31 15:59:00) -> Belongs to 2026
    Sale 2: Jan 1, 2027 00:00:00 Manila (UTC Dec 31 16:00:00) -> Belongs to 2027
    """
    env = report_test_env
    report_service = ReportService(db_session)

    s_2026 = Sale(
        transaction_number="TXN-YE-2026", subtotal=Decimal("500.00"), discount_amount=Decimal("0.00"),
        total_amount=Decimal("560.00"), status="COMPLETED", payment_method="CASH",
        created_at=datetime(2026, 12, 31, 15, 59, 0),
        items=[SaleLineItem(product_id=env["prod1"].id, product_name=env["prod1"].name, unit_price=Decimal("100.00"), unit_cost=Decimal("60.00"), quantity=5, subtotal=Decimal("500.00"))],
    )
    s_2027 = Sale(
        transaction_number="TXN-NY-2027", subtotal=Decimal("750.00"), discount_amount=Decimal("0.00"),
        total_amount=Decimal("840.00"), status="COMPLETED", payment_method="CASH",
        created_at=datetime(2026, 12, 31, 16, 0, 0),  # Exactly Jan 1 00:00:00 Manila
        items=[SaleLineItem(product_id=env["prod1"].id, product_name=env["prod1"].name, unit_price=Decimal("100.00"), unit_cost=Decimal("60.00"), quantity=7, subtotal=Decimal("700.00"))],
    )
    db_session.add_all([s_2026, s_2027])
    db_session.commit()

    # 2026 Annual Report
    annual_2026 = report_service.get_financial_summary(date(2026, 1, 1), date(2026, 12, 31))
    assert annual_2026.gross_sales == Decimal("500.00")

    # 2027 Annual Report
    annual_2027 = report_service.get_financial_summary(date(2027, 1, 1), date(2027, 12, 31))
    assert annual_2027.gross_sales == Decimal("750.00")


def test_daily_financial_trend_continuous_zero_filling(db_session, report_test_env):
    """
    Requested range: Aug 1 to Aug 5 (5 days).
    Sales on Aug 1 and Aug 3.
    Expenses on Aug 3 and Aug 5.
    Aug 2 and Aug 4 have no activity.
    Verify all 5 days exist in sequence and missing days have ₱0.00.
    """
    env = report_test_env
    report_service = ReportService(db_session)

    # Sale on Aug 1 14:00 Manila -> UTC Aug 1 06:00
    s1 = Sale(
        transaction_number="TXN-TR-1",
        subtotal=Decimal("100.00"),
        discount_amount=Decimal("10.00"),
        total_amount=Decimal("100.80"),
        status="COMPLETED",
        payment_method="CASH",
        created_at=datetime(2026, 8, 1, 6, 0, 0),
        items=[SaleLineItem(product_id=env["prod1"].id, product_name=env["prod1"].name, unit_price=Decimal("100.00"), unit_cost=Decimal("60.00"), quantity=1, subtotal=Decimal("100.00"))],
    )
    # Sale on Aug 3 11:00 Manila -> UTC Aug 3 03:00
    s2 = Sale(
        transaction_number="TXN-TR-2",
        subtotal=Decimal("50.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("56.00"),
        status="COMPLETED",
        payment_method="GCASH",
        created_at=datetime(2026, 8, 3, 3, 0, 0),
        items=[SaleLineItem(product_id=env["prod2"].id, product_name=env["prod2"].name, unit_price=Decimal("50.00"), unit_cost=Decimal("25.00"), quantity=1, subtotal=Decimal("50.00"))],
    )
    # Expense on Aug 3
    e1 = Expense(
        voucher_number="EXP-TR-1", category="utilities", title="Electric", payee="Meralco", amount=Decimal("20.00"), payment_method="CASH", expense_date=date(2026, 8, 3), status="paid"
    )
    # Expense on Aug 5
    e2 = Expense(
        voucher_number="EXP-TR-2", category="supplies", title="Bags", payee="Pack Co", amount=Decimal("15.00"), payment_method="CASH", expense_date=date(2026, 8, 5), status="paid"
    )
    db_session.add_all([s1, s2, e1, e2])
    db_session.commit()

    points = report_service.get_daily_financial_trend(date(2026, 8, 1), date(2026, 8, 5))
    assert len(points) == 5

    # Day 1: Aug 1 (Net Sales: 90, COGS: 60, GP: 30, OPEX: 0, Net: 30)
    assert points[0].date == "2026-08-01"
    assert points[0].net_sales == Decimal("90.00")
    assert points[0].cogs == Decimal("60.00")
    assert points[0].gross_profit == Decimal("30.00")
    assert points[0].opex == Decimal("0.00")
    assert points[0].net_operating_profit == Decimal("30.00")

    # Day 2: Aug 2 (Zero-filled!)
    assert points[1].date == "2026-08-02"
    assert points[1].net_sales == Decimal("0.00")
    assert points[1].cogs == Decimal("0.00")
    assert points[1].gross_profit == Decimal("0.00")
    assert points[1].opex == Decimal("0.00")
    assert points[1].net_operating_profit == Decimal("0.00")

    # Day 3: Aug 3 (Net Sales: 50, COGS: 25, GP: 25, OPEX: 20, Net: 5)
    assert points[2].date == "2026-08-03"
    assert points[2].net_sales == Decimal("50.00")
    assert points[2].cogs == Decimal("25.00")
    assert points[2].gross_profit == Decimal("25.00")
    assert points[2].opex == Decimal("20.00")
    assert points[2].net_operating_profit == Decimal("5.00")

    # Day 4: Aug 4 (Zero-filled!)
    assert points[3].date == "2026-08-04"
    assert points[3].net_sales == Decimal("0.00")

    # Day 5: Aug 5 (Net Sales: 0, OPEX: 15, Net: -15)
    assert points[4].date == "2026-08-05"
    assert points[4].opex == Decimal("15.00")
    assert points[4].net_operating_profit == Decimal("-15.00")


def test_cashier_performance_metrics(db_session, report_test_env):
    """Verify cashier sales, collections, AOV, discounts, and units sold."""
    env = report_test_env
    report_service = ReportService(db_session)
    c1 = env["user_cashier1"]
    c2 = env["user_cashier2"]

    # Bob: 2 sales (Aug 15 09:00 Manila -> UTC 01:00, Aug 15 11:00 Manila -> UTC 03:00)
    s1 = Sale(
        transaction_number="TXN-CP-1",
        cashier_id=c1.id,
        subtotal=Decimal("100.00"),
        discount_amount=Decimal("10.00"),
        tax_amount=Decimal("10.80"),
        total_amount=Decimal("100.80"),
        status="COMPLETED",
        payment_method="CASH",
        created_at=datetime(2026, 8, 15, 1, 0, 0),
        items=[SaleLineItem(product_id=env["prod1"].id, product_name=env["prod1"].name, unit_price=Decimal("100.00"), unit_cost=Decimal("60.00"), quantity=1, subtotal=Decimal("100.00"))],
    )
    s2 = Sale(
        transaction_number="TXN-CP-2",
        cashier_id=c1.id,
        subtotal=Decimal("200.00"),
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("24.00"),
        total_amount=Decimal("224.00"),
        status="COMPLETED",
        payment_method="CASH",
        created_at=datetime(2026, 8, 15, 3, 0, 0),
        items=[SaleLineItem(product_id=env["prod1"].id, product_name=env["prod1"].name, unit_price=Decimal("100.00"), unit_cost=Decimal("60.00"), quantity=2, subtotal=Decimal("200.00"))],
    )

    # Charlie: 1 sale (Aug 15 14:00 Manila -> UTC 06:00)
    s3 = Sale(
        transaction_number="TXN-CP-3",
        cashier_id=c2.id,
        subtotal=Decimal("50.00"),
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("6.00"),
        total_amount=Decimal("56.00"),
        status="COMPLETED",
        payment_method="MAYA",
        created_at=datetime(2026, 8, 15, 6, 0, 0),
        items=[SaleLineItem(product_id=env["prod2"].id, product_name=env["prod2"].name, unit_price=Decimal("50.00"), unit_cost=Decimal("25.00"), quantity=1, subtotal=Decimal("50.00"))],
    )
    db_session.add_all([s1, s2, s3])
    db_session.commit()

    perf = report_service.get_cashier_performance(date(2026, 8, 15), date(2026, 8, 15))
    assert len(perf) == 2

    bob_perf = next(p for p in perf if p.cashier_id == c1.id)
    assert bob_perf.cashier_name == "Bob Cashier"
    assert bob_perf.transaction_count == 2
    assert bob_perf.net_sales == Decimal("290.00")
    assert bob_perf.collections == Decimal("324.80")
    assert bob_perf.average_order_value == Decimal("145.00")
    assert bob_perf.discounts == Decimal("10.00")
    assert bob_perf.units_sold == 3

    charlie_perf = next(p for p in perf if p.cashier_id == c2.id)
    assert charlie_perf.cashier_name == "Charlie Cashier"
    assert charlie_perf.transaction_count == 1
    assert charlie_perf.net_sales == Decimal("50.00")
    assert charlie_perf.collections == Decimal("56.00")
    assert charlie_perf.average_order_value == Decimal("50.00")
    assert charlie_perf.units_sold == 1


def test_product_performance_leaderboard(db_session, report_test_env):
    """Verify product ranking by gross revenue and direct gross margin."""
    env = report_test_env
    report_service = ReportService(db_session)

    sale = Sale(
        transaction_number="TXN-PP-1",
        subtotal=Decimal("400.00"),
        total_amount=Decimal("448.00"),
        status="COMPLETED",
        payment_method="CASH",
        created_at=datetime(2026, 8, 15, 4, 0, 0),
        items=[
            SaleLineItem(product_id=env["prod1"].id, product_name=env["prod1"].name, unit_price=Decimal("100.00"), unit_cost=Decimal("60.00"), quantity=3, subtotal=Decimal("300.00")),
            SaleLineItem(product_id=env["prod2"].id, product_name=env["prod2"].name, unit_price=Decimal("50.00"), unit_cost=Decimal("25.00"), quantity=2, subtotal=Decimal("100.00")),
        ],
    )
    db_session.add(sale)
    db_session.commit()

    ranking = report_service.get_product_performance(date(2026, 8, 15), date(2026, 8, 15))
    assert len(ranking) == 2

    top = ranking[0]
    assert top.sku == "RPT-P1"
    assert top.quantity_sold == 3
    assert top.gross_revenue == Decimal("300.00")
    assert top.historical_cogs == Decimal("180.00")
    assert top.direct_margin_before_order_discount == Decimal("120.00")

    second = ranking[1]
    assert second.sku == "RPT-P2"
    assert second.quantity_sold == 2
    assert second.gross_revenue == Decimal("100.00")
    assert second.historical_cogs == Decimal("50.00")
    assert second.direct_margin_before_order_discount == Decimal("50.00")


def test_payment_method_breakdown(db_session, report_test_env):
    """Verify payment method distribution sums and percentages."""
    env = report_test_env
    report_service = ReportService(db_session)

    s1 = Sale(transaction_number="TXN-PM-1", total_amount=Decimal("600.00"), status="COMPLETED", payment_method="CASH", created_at=datetime(2026, 8, 15, 2, 0, 0))
    s2 = Sale(transaction_number="TXN-PM-2", total_amount=Decimal("400.00"), status="COMPLETED", payment_method="GCASH", created_at=datetime(2026, 8, 15, 3, 0, 0))
    db_session.add_all([s1, s2])
    db_session.commit()

    pm_list = report_service.get_payment_method_breakdown(date(2026, 8, 15), date(2026, 8, 15))
    assert len(pm_list) == 2

    cash = next(p for p in pm_list if p.payment_method == "CASH")
    assert cash.total_amount == Decimal("600.00")
    assert cash.percentage == Decimal("60.00")

    gcash = next(p for p in pm_list if p.payment_method == "GCASH")
    assert gcash.total_amount == Decimal("400.00")
    assert gcash.percentage == Decimal("40.00")


def test_inventory_valuation(db_session, report_test_env):
    """
    Inventory valuation:
    Prod 1: 50 units * ₱60 cost = ₱3,000 cost | 50 * ₱100 sell = ₱5,000 retail
    Prod 2: 100 units * ₱25 cost = ₱2,500 cost | 100 * ₱50 sell = ₱5,000 retail
    Prod 3: 0 units
    Total Cost Value = ₱5,500.00
    Total Retail Value = ₱10,000.00
    Potential Unrealized Margin = ₱4,500.00
    """
    report_service = ReportService(db_session)
    val = report_service.get_inventory_value()

    assert val.total_products == 3
    assert val.total_units_on_hand == 150
    assert val.current_cost_value == Decimal("5500.00")
    assert val.current_retail_value == Decimal("10000.00")
    assert val.potential_unrealized_margin == Decimal("4500.00")


def test_received_purchase_value(db_session, report_test_env):
    """Verify purchasing summary includes only RECEIVED purchase orders."""
    sup = Supplier(code="SUP-TEST-001", name="Test Wholesaler", contact_person="John", phone="09111111111", email="sup@test.com")
    db_session.add(sup)
    db_session.flush()

    po_rcvd = PurchaseOrder(
        po_number="PO-RPT-1",
        supplier_id=sup.id,
        order_date=datetime(2026, 8, 10, 2, 0, 0),
        received_at=datetime(2026, 8, 12, 7, 0, 0),
        status="RECEIVED",
        total_amount=Decimal("12500.00"),
        items=[PurchaseOrderItem(product_id=report_test_env["prod1"].id, product_name="Product One", quantity_ordered=100, quantity_received=100, unit_cost=Decimal("50.00"), subtotal=Decimal("5000.00"))],
    )
    po_ordered = PurchaseOrder(
        po_number="PO-RPT-2",
        supplier_id=sup.id,
        order_date=datetime(2026, 8, 11, 2, 0, 0),
        status="ORDERED",
        total_amount=Decimal("8000.00"),
        items=[],
    )
    db_session.add_all([po_rcvd, po_ordered])
    db_session.commit()

    report_service = ReportService(db_session)
    intake = report_service.get_received_purchase_value(date(2026, 8, 10), date(2026, 8, 13))

    assert intake.received_order_count == 1
    assert intake.received_purchase_value == Decimal("12500.00")
    assert intake.total_units_received == 100


def test_report_service_permission_enforcement(db_session, report_test_env):
    """Verify AuthorizationError is raised when actor lacks 'view_reports'."""
    env = report_test_env
    report_service = ReportService(db_session)

    # Alice (Manager) has view_reports -> Success
    summary = report_service.get_financial_summary(date(2026, 8, 1), date(2026, 8, 15), actor=env["user_mgr"])
    assert summary is not None

    # Bob (Cashier) lacks view_reports -> Raises AuthorizationError
    with pytest.raises(AuthorizationError):
        report_service.get_financial_summary(date(2026, 8, 1), date(2026, 8, 15), actor=env["user_cashier1"])

    with pytest.raises(AuthorizationError):
        report_service.get_daily_financial_trend(date(2026, 8, 1), date(2026, 8, 15), actor=env["user_cashier1"])


def test_invalid_date_range_raises_validation_error(db_session, report_test_env):
    """Start date after end date raises ValidationError."""
    report_service = ReportService(db_session)
    with pytest.raises(ValidationError):
        report_service.get_financial_summary(date(2026, 8, 15), date(2026, 8, 10))


def test_get_expense_category_breakdown(db_session, report_test_env):
    """Verify category totals and pure Decimal percentage calculation with VOID exclusion."""
    report_service = ReportService(db_session)

    # 1. Empty period returns empty list safely
    empty_res = report_service.get_expense_category_breakdown(date(2026, 1, 1), date(2026, 1, 7))
    assert empty_res == []

    # 2. Add Expenses
    e1 = Expense(
        voucher_number="EXP-CAT-1", category="utilities", title="Electric", payee="Meralco",
        amount=Decimal("600.00"), payment_method="CASH", expense_date=date(2026, 8, 10), status="paid"
    )
    e2 = Expense(
        voucher_number="EXP-CAT-2", category="salaries", title="Staff Pay", payee="Staff",
        amount=Decimal("300.00"), payment_method="BANK_TRANSFER", expense_date=date(2026, 8, 12), status="paid"
    )
    e3 = Expense(
        voucher_number="EXP-CAT-3", category="supplies", title="Bags", payee="Pack Co",
        amount=Decimal("100.00"), payment_method="CASH", expense_date=date(2026, 8, 14), status="paid"
    )
    e_void = Expense(
        voucher_number="EXP-CAT-4", category="marketing", title="Flyers", payee="Print Co",
        amount=Decimal("500.00"), payment_method="CASH", expense_date=date(2026, 8, 14), status="void",
        void_reason="Cancelled ad run"
    )
    db_session.add_all([e1, e2, e3, e_void])
    db_session.commit()

    breakdown = report_service.get_expense_category_breakdown(date(2026, 8, 1), date(2026, 8, 15))
    # Total OPEX = 600 + 300 + 100 = 1,000.00 (VOID excluded)
    assert len(breakdown) == 3

    # Utilities: 600 / 1000 = 60.00%
    assert breakdown[0].category == "utilities"
    assert breakdown[0].category_display == "Utilities (Power, Water, Internet)"
    assert breakdown[0].amount == Decimal("600.00")
    assert breakdown[0].percentage == Decimal("60.00")

    # Salaries: 300 / 1000 = 30.00%
    assert breakdown[1].category == "salaries"
    assert breakdown[1].category_display == "Staff Wages & Allowances"
    assert breakdown[1].amount == Decimal("300.00")
    assert breakdown[1].percentage == Decimal("30.00")

    # Supplies: 100 / 1000 = 10.00%
    assert breakdown[2].category == "supplies"
    assert breakdown[2].category_display == "Store Supplies & Packaging"
    assert breakdown[2].amount == Decimal("100.00")
    assert breakdown[2].percentage == Decimal("10.00")

