"""
RetailFlow POS - Returns to Reports Integration Test Suite
Comprehensive verification of all financial reporting reconciliations with Returns & Refunds:
1. Baseline period without returns
2. Same-period RESTOCK return (perfect net zero)
3. Same-period DAMAGED write-off return (retained product cost in COGS)
4. Order-level discount apportionment across partial returns
5. Cross-period return recognition (prior month untouched, current month reflects reversals)
6. Cashier attribution to original Sale cashier (not return operator)
7. Cashier with return-only period (negative net sales, 0 transactions, 0.00 AOV)
8. Product performance with return-only period and deterministic tie-breaking
9. Refunds by Method distribution and zero-division protection
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
import pytest

from app.constants import RefundMethod, ReturnDisposition, ReturnReason, ReturnStatus
from application.dto.returns_dto import (
    ProcessReturnRequestDTO,
    ReturnItemRequestDTO,
)
from application.dto.sales_dto import CartItemDTO, CheckoutRequestDTO
from application.services.product_service import ProductService
from application.services.report_service import ReportService
from application.services.returns_service import ReturnsService
from application.services.sales_service import SalesService
from infrastructure.database.models.auth import Permission, Role, User
from infrastructure.database.models.inventory import Inventory
from infrastructure.database.models.product import Category, Product
from infrastructure.database.models.returns import SalesReturn, SalesReturnItem
from infrastructure.database.models.sales import Sale, SaleLineItem


@pytest.fixture
def test_users(db_session):
    """Fixture providing admin, cashier A, and cashier B."""
    perm_reports = Permission(code="view_reports", name="View Reports", module="reports")
    perm_sales = Permission(code="process_sale", name="Process Sale", module="pos")
    perm_view_sales = Permission(code="view_sales", name="View Sales", module="sales")
    perm_returns = Permission(code="return_sales", name="Process Returns", module="sales")
    perm_approve = Permission(code="refund_approve", name="Approve Returns", module="sales")
    db_session.add_all([perm_reports, perm_sales, perm_view_sales, perm_returns, perm_approve])
    db_session.flush()

    admin_role = Role(name="Admin", code="admin", permissions=[perm_reports, perm_sales, perm_view_sales, perm_returns, perm_approve])
    cashier_role = Role(name="Cashier", code="cashier", permissions=[perm_sales, perm_view_sales, perm_returns])
    db_session.add_all([admin_role, cashier_role])
    db_session.flush()

    admin = User(username="admin_rep", password_hash="hash", full_name="Admin Manager", roles=[admin_role])
    cashier_a = User(username="cashier_a", password_hash="hash", full_name="Cashier Alice", roles=[cashier_role])
    cashier_b = User(username="cashier_b", password_hash="hash", full_name="Cashier Bob", roles=[cashier_role])
    db_session.add_all([admin, cashier_a, cashier_b])
    db_session.commit()

    return {"admin": admin, "cashier_a": cashier_a, "cashier_b": cashier_b}


@pytest.fixture
def catalog_products(db_session):
    """Fixture providing catalog products with distinct cost, selling price, and inventory."""
    cat = Category(name="Electronics")
    db_session.add(cat)
    db_session.flush()

    # Product 1: Selling ₱100.00, Cost ₱60.00, Stock 50
    p1 = Product(
        sku="SKU-PHONE-CASE",
        name="Silicone Phone Case",
        selling_price=Decimal("100.00"),
        cost_price=Decimal("60.00"),
        category_id=cat.id,
        status="active",
    )
    # Product 2: Selling ₱250.00, Cost ₱150.00, Stock 30
    p2 = Product(
        sku="SKU-CHARGER",
        name="Fast Wall Charger 30W",
        selling_price=Decimal("250.00"),
        cost_price=Decimal("150.00"),
        category_id=cat.id,
        status="active",
    )
    # Product 3: Selling ₱500.00, Cost ₱300.00, Stock 20
    p3 = Product(
        sku="SKU-HEADPHONES",
        name="Wireless Bluetooth Earbuds",
        selling_price=Decimal("500.00"),
        cost_price=Decimal("300.00"),
        category_id=cat.id,
        status="active",
    )
    db_session.add_all([p1, p2, p3])
    db_session.flush()

    inv1 = Inventory(product_id=p1.id, quantity_on_hand=50)
    inv2 = Inventory(product_id=p2.id, quantity_on_hand=30)
    inv3 = Inventory(product_id=p3.id, quantity_on_hand=20)
    db_session.add_all([inv1, inv2, inv3])
    db_session.commit()

    return {"p1": p1, "p2": p2, "p3": p3, "inv1": inv1, "inv2": inv2, "inv3": inv3}


# ── 1. Baseline & Same-Period RESTOCK Return ──────────────────────────

def test_same_period_restock_return_reconciliation(db_session, test_users, catalog_products):
    """
    Sale of 2 phone cases (₱200) + 1 charger (₱250) = ₱450 gross + ₱54 VAT = ₱504 total due.
    Full return of all items with RESTOCK (₱450 taxable + ₱54 VAT = ₱504 refund).
    Period Net Sales = ₱0.00, Net COGS = ₱0.00, Net Collections = ₱0.00, Net VAT = ₱0.00.
    Inventory stock restored to original levels.
    """
    sales_service = SalesService(db_session)
    returns_service = ReturnsService(db_session)
    report_service = ReportService(db_session)

    admin = test_users["admin"]
    cashier = test_users["cashier_a"]
    p1 = catalog_products["p1"]
    p2 = catalog_products["p2"]
    inv1 = catalog_products["inv1"]
    inv2 = catalog_products["inv2"]

    # 1. Checkout Sale (₱450 subtotal + ₱54 tax = ₱504)
    checkout_req = CheckoutRequestDTO(
        items=[
            CartItemDTO(product_id=p1.id, sku=p1.sku, name=p1.name, quantity=2, unit_price=Decimal("100.00")),
            CartItemDTO(product_id=p2.id, sku=p2.sku, name=p2.name, quantity=1, unit_price=Decimal("250.00")),
        ],
        payment_method="CASH",
        amount_tendered=Decimal("504.00"),
        discount_amount=Decimal("0.00"),
    )
    sale_dto = sales_service.process_checkout(checkout_req, cashier)
    db_session.commit()

    # 2. Process Full Return with RESTOCK
    return_items = returns_service.get_returnable_items(sale_dto.id, cashier)
    return_req = ProcessReturnRequestDTO(
        sale_id=sale_dto.id,
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
        reason_notes="Customer changed mind immediately",
        refund_payment_method=RefundMethod.CASH.value,
        items=[
            ReturnItemRequestDTO(
                sale_line_item_id=item.sale_line_item_id,
                quantity=item.remaining_returnable_quantity,
                disposition=ReturnDisposition.RESTOCK.value,
            )
            for item in return_items
        ],
    )
    ret_dto = returns_service.process_return(return_req, actor=cashier, approver=admin, idempotency_key="RESTOCK-E2E-001")
    db_session.commit()

    # 3. Query Financial Summary for Today
    today = date.today()
    summary = report_service.get_financial_summary(today, today, actor=admin)

    # Reconciliations
    assert summary.gross_sales == Decimal("450.00")
    assert summary.sales_returns == Decimal("450.00")
    assert summary.net_sales == Decimal("0.00")
    assert summary.gross_output_vat == Decimal("54.00")
    assert summary.vat_reversals == Decimal("54.00")
    assert summary.net_output_vat == Decimal("0.00")
    assert summary.total_collections == Decimal("504.00")
    assert summary.refunds_issued == Decimal("504.00")
    assert summary.net_collections == Decimal("0.00")
    assert summary.original_cogs == Decimal("270.00")
    assert summary.cogs_reversals == Decimal("270.00")
    assert summary.cogs == Decimal("0.00")
    assert summary.gross_profit == Decimal("0.00")
    assert summary.net_operating_profit == Decimal("0.00")

    # Inventory stock verified restored
    db_session.refresh(inv1)
    db_session.refresh(inv2)
    assert inv1.quantity_on_hand == 50
    assert inv2.quantity_on_hand == 30


# ── 2. Same-Period DAMAGED Write-Off Return ──────────────────────────

def test_same_period_damaged_return_retains_cogs_loss(db_session, test_users, catalog_products):
    """
    Sale of 1 Headphones (₱500, Cost ₱300) + ₱60 VAT = ₱560 total due.
    Return disposition = DAMAGED (inventory written off).
    Revenue is reversed (-₱500), but COGS reversal is ₱0.00.
    Gross Profit = Net Sales (₱0.00) - COGS (₱300.00) = -₱300.00 (loss correctly recognized).
    Stock is NOT restored (remains 19).
    """
    sales_service = SalesService(db_session)
    returns_service = ReturnsService(db_session)
    report_service = ReportService(db_session)

    admin = test_users["admin"]
    cashier = test_users["cashier_a"]
    p3 = catalog_products["p3"]
    inv3 = catalog_products["inv3"]

    # 1. Checkout Sale (₱500 + ₱60 tax = ₱560)
    checkout_req = CheckoutRequestDTO(
        items=[CartItemDTO(product_id=p3.id, sku=p3.sku, name=p3.name, quantity=1, unit_price=Decimal("500.00"))],
        payment_method="CASH",
        amount_tendered=Decimal("560.00"),
        discount_amount=Decimal("0.00"),
    )
    sale_dto = sales_service.process_checkout(checkout_req, cashier)
    db_session.commit()

    # 2. Process Return with DAMAGED_WRITE_OFF disposition
    return_items = returns_service.get_returnable_items(sale_dto.id, cashier)
    return_req = ProcessReturnRequestDTO(
        sale_id=sale_dto.id,
        reason_code=ReturnReason.DEFECTIVE.value,
        reason_notes="Defective speaker driver",
        refund_payment_method=RefundMethod.CASH.value,
        items=[
            ReturnItemRequestDTO(
                sale_line_item_id=return_items[0].sale_line_item_id,
                quantity=1,
                disposition=ReturnDisposition.DAMAGED_WRITE_OFF.value,
            )
        ],
    )
    returns_service.process_return(return_req, actor=cashier, approver=admin, idempotency_key="DAMAGED-E2E-001")
    db_session.commit()

    # 3. Query Financial Summary
    today = date.today()
    summary = report_service.get_financial_summary(today, today, actor=admin)

    assert summary.gross_sales == Decimal("500.00")
    assert summary.sales_returns == Decimal("500.00")
    assert summary.net_sales == Decimal("0.00")
    assert summary.gross_output_vat == Decimal("60.00")
    assert summary.vat_reversals == Decimal("60.00")
    assert summary.net_output_vat == Decimal("0.00")
    assert summary.original_cogs == Decimal("300.00")
    assert summary.cogs_reversals == Decimal("0.00")  # DAMAGED items have 0 COGS reversal
    assert summary.cogs == Decimal("300.00")          # Loss retained in reported COGS
    assert summary.gross_profit == Decimal("-300.00")
    assert summary.net_operating_profit == Decimal("-300.00")

    # Inventory stock remains 19 (not restocked)
    db_session.refresh(inv3)
    assert inv3.quantity_on_hand == 19


# ── 3. Partial Return with Order-Level Discount Apportionment ─────────

def test_partial_return_with_discount_apportionment(db_session, test_users, catalog_products):
    """
    Sale of 2 phone cases (₱200) + 1 charger (₱250) = ₱450 gross.
    Order discount = ₱50.00 -> Taxable = ₱400.00 + ₱48 VAT = ₱448.00 total due.
    Return 1 phone case with RESTOCK.
    Financial summary reflects exact net sales and refund.
    """
    sales_service = SalesService(db_session)
    returns_service = ReturnsService(db_session)
    report_service = ReportService(db_session)

    admin = test_users["admin"]
    cashier = test_users["cashier_a"]
    p1 = catalog_products["p1"]
    p2 = catalog_products["p2"]

    # 1. Checkout Sale with ₱50.00 discount (₱400 taxable + ₱48 tax = ₱448)
    checkout_req = CheckoutRequestDTO(
        items=[
            CartItemDTO(product_id=p1.id, sku=p1.sku, name=p1.name, quantity=2, unit_price=Decimal("100.00")),
            CartItemDTO(product_id=p2.id, sku=p2.sku, name=p2.name, quantity=1, unit_price=Decimal("250.00")),
        ],
        payment_method="CASH",
        amount_tendered=Decimal("448.00"),
        discount_amount=Decimal("50.00"),
    )
    sale_dto = sales_service.process_checkout(checkout_req, cashier)
    db_session.commit()

    # 2. Return 1 phone case
    return_items = returns_service.get_returnable_items(sale_dto.id, cashier)
    case_item = next(item for item in return_items if item.product_id == p1.id)

    return_req = ProcessReturnRequestDTO(
        sale_id=sale_dto.id,
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
        reason_notes="Returning 1 of 2 cases",
        refund_payment_method=RefundMethod.CASH.value,
        items=[
            ReturnItemRequestDTO(
                sale_line_item_id=case_item.sale_line_item_id,
                quantity=1,
                disposition=ReturnDisposition.RESTOCK.value,
            )
        ],
    )
    ret_dto = returns_service.process_return(return_req, actor=cashier, approver=admin, idempotency_key="PARTIAL-E2E-001")
    db_session.commit()

    # 3. Query Financial Summary
    today = date.today()
    summary = report_service.get_financial_summary(today, today, actor=admin)

    assert summary.gross_sales == Decimal("450.00")
    assert summary.discounts == Decimal("50.00")
    assert summary.sales_returns == ret_dto.taxable_reversal
    expected_net_sales = Decimal("450.00") - Decimal("50.00") - ret_dto.taxable_reversal
    assert summary.net_sales == expected_net_sales
    assert summary.refunds_issued == ret_dto.total_refund_amount
    assert summary.net_collections == Decimal("448.00") - ret_dto.total_refund_amount
    assert summary.cogs_reversals == Decimal("60.00")
    assert summary.cogs == Decimal("270.00") - Decimal("60.00")


# ── 4. Cross-Period Return Recognition ───────────────────────────────

def test_cross_period_return_recognition(db_session, test_users, catalog_products):
    """
    Sale occurs in Period 1 (e.g. 2026-07-15, ₱500 gross, ₱60 VAT, ₱560 collections, ₱300 COGS).
    Return occurs in Period 2 (e.g. 2026-08-15, ₱560 refund, ₱300 COGS reversal).
    Period 1 report: Gross Sales = ₱500, Net Sales = ₱500, Returns = ₱0, Net COGS = ₱300.
    Period 2 report: Gross Sales = ₱0, Returns = ₱500, Net Sales = -₱500, COGS Reversal = ₱300, Net COGS = -₱300, Gross Profit = -₱200.
    Prior period is strictly unmodified.
    """
    sales_service = SalesService(db_session)
    returns_service = ReturnsService(db_session)
    report_service = ReportService(db_session)

    admin = test_users["admin"]
    cashier = test_users["cashier_a"]
    p3 = catalog_products["p3"]

    # 1. Checkout Sale (₱500 + ₱60 tax = ₱560)
    checkout_req = CheckoutRequestDTO(
        items=[CartItemDTO(product_id=p3.id, sku=p3.sku, name=p3.name, quantity=1, unit_price=Decimal("500.00"))],
        payment_method="CASH",
        amount_tendered=Decimal("560.00"),
        discount_amount=Decimal("0.00"),
    )
    sale_dto = sales_service.process_checkout(checkout_req, cashier)
    db_session.commit()

    # Manually backdate Sale to 2026-07-15 (UTC 2026-07-15 02:00:00)
    sale_model = db_session.query(Sale).filter(Sale.id == sale_dto.id).one()
    sale_model.created_at = datetime(2026, 7, 15, 2, 0, 0)
    db_session.commit()

    # 2. Process Return on 2026-08-15
    return_items = returns_service.get_returnable_items(sale_dto.id, cashier)
    return_req = ProcessReturnRequestDTO(
        sale_id=sale_dto.id,
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
        refund_payment_method=RefundMethod.CASH.value,
        items=[
            ReturnItemRequestDTO(
                sale_line_item_id=return_items[0].sale_line_item_id,
                quantity=1,
                disposition=ReturnDisposition.RESTOCK.value,
            )
        ],
    )
    ret_dto = returns_service.process_return(return_req, actor=cashier, approver=admin, idempotency_key="CROSS-PERIOD-001")
    db_session.commit()

    ret_model = db_session.query(SalesReturn).filter(SalesReturn.id == ret_dto.id).one()
    ret_model.return_date = date(2026, 8, 15)
    ret_model.created_at = datetime(2026, 8, 15, 3, 0, 0)
    db_session.commit()

    # 3. Query Period 1 (July 2026)
    july_summary = report_service.get_financial_summary(date(2026, 7, 1), date(2026, 7, 31), actor=admin)
    assert july_summary.gross_sales == Decimal("500.00")
    assert july_summary.sales_returns == Decimal("0.00")
    assert july_summary.net_sales == Decimal("500.00")
    assert july_summary.gross_output_vat == Decimal("60.00")
    assert july_summary.vat_reversals == Decimal("0.00")
    assert july_summary.net_output_vat == Decimal("60.00")
    assert july_summary.original_cogs == Decimal("300.00")
    assert july_summary.cogs_reversals == Decimal("0.00")
    assert july_summary.cogs == Decimal("300.00")
    assert july_summary.gross_profit == Decimal("200.00")
    assert july_summary.total_collections == Decimal("560.00")
    assert july_summary.refunds_issued == Decimal("0.00")
    assert july_summary.net_collections == Decimal("560.00")

    # 4. Query Period 2 (August 2026)
    aug_summary = report_service.get_financial_summary(date(2026, 8, 1), date(2026, 8, 31), actor=admin)
    assert aug_summary.gross_sales == Decimal("0.00")
    assert aug_summary.sales_returns == Decimal("500.00")
    assert aug_summary.net_sales == Decimal("-500.00")
    assert aug_summary.gross_output_vat == Decimal("0.00")
    assert aug_summary.vat_reversals == Decimal("60.00")
    assert aug_summary.net_output_vat == Decimal("-60.00")
    assert aug_summary.original_cogs == Decimal("0.00")
    assert aug_summary.cogs_reversals == Decimal("300.00")
    assert aug_summary.cogs == Decimal("-300.00")
    assert aug_summary.gross_profit == Decimal("-200.00")
    assert aug_summary.total_collections == Decimal("0.00")
    assert aug_summary.refunds_issued == Decimal("560.00")
    assert aug_summary.net_collections == Decimal("-560.00")


# ── 5. Cashier Attribution to Original Cashier ───────────────────────

def test_cashier_attribution_to_original_sale_cashier(db_session, test_users, catalog_products):
    """
    Cashier Alice processes a ₱250 sale + ₱30 VAT = ₱280 total.
    Cashier Bob processes the ₱280 return voucher for that sale.
    Cashier Performance Report attributes the return to Alice (original seller), NOT Bob.
    """
    sales_service = SalesService(db_session)
    returns_service = ReturnsService(db_session)
    report_service = ReportService(db_session)

    admin = test_users["admin"]
    alice = test_users["cashier_a"]
    bob = test_users["cashier_b"]
    p2 = catalog_products["p2"]

    # 1. Alice makes the sale (₱250 + ₱30 tax = ₱280)
    checkout_req = CheckoutRequestDTO(
        items=[CartItemDTO(product_id=p2.id, sku=p2.sku, name=p2.name, quantity=1, unit_price=Decimal("250.00"))],
        payment_method="CASH",
        amount_tendered=Decimal("280.00"),
        discount_amount=Decimal("0.00"),
    )
    sale_dto = sales_service.process_checkout(checkout_req, alice)
    db_session.commit()

    # 2. Bob processes the return
    return_items = returns_service.get_returnable_items(sale_dto.id, bob)
    return_req = ProcessReturnRequestDTO(
        sale_id=sale_dto.id,
        reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
        refund_payment_method=RefundMethod.CASH.value,
        items=[
            ReturnItemRequestDTO(
                sale_line_item_id=return_items[0].sale_line_item_id,
                quantity=1,
                disposition=ReturnDisposition.RESTOCK.value,
            )
        ],
    )
    returns_service.process_return(return_req, actor=bob, approver=admin, idempotency_key="CASHIER-ATTR-001")
    db_session.commit()

    # 3. Query Cashier Performance
    today = date.today()
    cashiers = report_service.get_cashier_performance(today, today, actor=admin)

    alice_perf = next((c for c in cashiers if c.cashier_id == alice.id), None)
    bob_perf = next((c for c in cashiers if c.cashier_id == bob.id), None)

    assert alice_perf is not None
    assert alice_perf.transaction_count == 1
    assert alice_perf.net_sales == Decimal("0.00")
    assert alice_perf.collections == Decimal("280.00")
    assert alice_perf.refunds_issued == Decimal("280.00")
    assert alice_perf.net_collections == Decimal("0.00")
    assert alice_perf.units_returned == 1
    assert alice_perf.net_units == 0
    assert alice_perf.average_order_value == Decimal("0.00")

    assert bob_perf is None


# ── 6. Cashier with Return-Only Period ────────────────────────────────

def test_cashier_with_return_only_period(db_session, test_users, catalog_products):
    """
    Cashier Alice made a sale in July (₱500 + ₱60 tax = ₱560).
    A return for that sale is recognized in August.
    Alice has transaction_count = 0, net_sales = -₱500, average_order_value = ₱0.00.
    """
    sales_service = SalesService(db_session)
    returns_service = ReturnsService(db_session)
    report_service = ReportService(db_session)

    admin = test_users["admin"]
    alice = test_users["cashier_a"]
    p3 = catalog_products["p3"]

    # 1. Sale in July
    sale_dto = sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[CartItemDTO(product_id=p3.id, sku=p3.sku, name=p3.name, quantity=1, unit_price=Decimal("500.00"))],
            payment_method="CASH",
            amount_tendered=Decimal("560.00"),
            discount_amount=Decimal("0.00"),
        ),
        alice,
    )
    db_session.commit()

    sale_model = db_session.query(Sale).filter(Sale.id == sale_dto.id).one()
    sale_model.created_at = datetime(2026, 7, 10, 5, 0, 0)
    db_session.commit()

    # 2. Return in August
    return_items = returns_service.get_returnable_items(sale_dto.id, alice)
    ret_dto = returns_service.process_return(
        ProcessReturnRequestDTO(
            sale_id=sale_dto.id,
            reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
            refund_payment_method=RefundMethod.CASH.value,
            items=[
                ReturnItemRequestDTO(
                    sale_line_item_id=return_items[0].sale_line_item_id,
                    quantity=1,
                    disposition=ReturnDisposition.RESTOCK.value,
                )
            ],
        ),
        actor=alice,
        approver=admin,
        idempotency_key="CASHIER-RET-ONLY-001",
    )
    db_session.commit()

    ret_model = db_session.query(SalesReturn).filter(SalesReturn.id == ret_dto.id).one()
    ret_model.return_date = date(2026, 8, 10)
    ret_model.created_at = datetime(2026, 8, 10, 5, 0, 0)
    db_session.commit()

    # 3. Query August Cashier Performance
    cashiers = report_service.get_cashier_performance(date(2026, 8, 1), date(2026, 8, 31), actor=admin)
    alice_perf = next((c for c in cashiers if c.cashier_id == alice.id), None)

    assert alice_perf is not None
    assert alice_perf.transaction_count == 0
    assert alice_perf.net_sales == Decimal("-500.00")
    assert alice_perf.collections == Decimal("0.00")
    assert alice_perf.refunds_issued == Decimal("560.00")
    assert alice_perf.net_collections == Decimal("-560.00")
    assert alice_perf.units_returned == 1
    assert alice_perf.net_units == -1
    assert alice_perf.average_order_value == Decimal("0.00")


# ── 7. Product Performance Leaderboard & Deterministic Sorting ────────

def test_product_performance_leaderboard_and_tie_breaking(db_session, test_users, catalog_products):
    """
    Product P1: Net Revenue = ₱300, Net Units = 3.
    Product P2: Net Revenue = ₱500, Net Units = 2.
    Product P3: Net Revenue = -₱500, Net Units = -1.
    Leaderboard ranks: #1 P2 (₱500), #2 P1 (₱300), #3 P3 (-₱500).
    """
    sales_service = SalesService(db_session)
    returns_service = ReturnsService(db_session)
    report_service = ReportService(db_session)

    admin = test_users["admin"]
    cashier = test_users["cashier_a"]
    p1 = catalog_products["p1"]
    p2 = catalog_products["p2"]
    p3 = catalog_products["p3"]

    today = date.today()

    # Prior sale of P3 (July: ₱500 + ₱60 tax = ₱560)
    sale_p3 = sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[CartItemDTO(product_id=p3.id, sku=p3.sku, name=p3.name, quantity=1, unit_price=Decimal("500.00"))],
            payment_method="CASH",
            amount_tendered=Decimal("560.00"),
            discount_amount=Decimal("0.00"),
        ),
        cashier,
    )
    db_session.commit()
    sale_p3_m = db_session.query(Sale).filter(Sale.id == sale_p3.id).one()
    sale_p3_m.created_at = datetime(2026, 7, 1, 10, 0, 0)
    db_session.commit()

    # Today: Sale of 5 P1 (₱500) and 2 P2 (₱500) = ₱1000 + ₱120 tax = ₱1120
    sale_today = sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[
                CartItemDTO(product_id=p1.id, sku=p1.sku, name=p1.name, quantity=5, unit_price=Decimal("100.00")),
                CartItemDTO(product_id=p2.id, sku=p2.sku, name=p2.name, quantity=2, unit_price=Decimal("250.00")),
            ],
            payment_method="CASH",
            amount_tendered=Decimal("1120.00"),
            discount_amount=Decimal("0.00"),
        ),
        cashier,
    )
    db_session.commit()

    # Today: Return 2 P1
    ret_items_today = returns_service.get_returnable_items(sale_today.id, cashier)
    p1_item = next(i for i in ret_items_today if i.product_id == p1.id)
    returns_service.process_return(
        ProcessReturnRequestDTO(
            sale_id=sale_today.id,
            reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
            refund_payment_method=RefundMethod.CASH.value,
            items=[ReturnItemRequestDTO(sale_line_item_id=p1_item.sale_line_item_id, quantity=2, disposition=ReturnDisposition.RESTOCK.value)],
        ),
        actor=cashier,
        approver=admin,
        idempotency_key="PROD-P1-RET-001",
    )
    db_session.commit()

    # Today: Return 1 P3 (from July sale)
    ret_items_p3 = returns_service.get_returnable_items(sale_p3.id, cashier)
    returns_service.process_return(
        ProcessReturnRequestDTO(
            sale_id=sale_p3.id,
            reason_code=ReturnReason.DEFECTIVE.value,
            refund_payment_method=RefundMethod.CASH.value,
            items=[ReturnItemRequestDTO(sale_line_item_id=ret_items_p3[0].sale_line_item_id, quantity=1, disposition=ReturnDisposition.RESTOCK.value)],
        ),
        actor=cashier,
        approver=admin,
        idempotency_key="PROD-P3-RET-001",
    )
    db_session.commit()

    # Query Product Performance for Today
    prods = report_service.get_product_performance(today, today, actor=admin)
    assert len(prods) == 3

    # Rank #1: P2
    assert prods[0].product_id == p2.id
    assert prods[0].quantity_sold == 2
    assert prods[0].quantity_returned == 0
    assert prods[0].net_units_sold == 2
    assert prods[0].net_gross_revenue == Decimal("500.00")
    assert prods[0].net_historical_cogs == Decimal("300.00")
    assert prods[0].direct_margin == Decimal("200.00")

    # Rank #2: P1
    assert prods[1].product_id == p1.id
    assert prods[1].quantity_sold == 5
    assert prods[1].quantity_returned == 2
    assert prods[1].net_units_sold == 3
    assert prods[1].net_gross_revenue == Decimal("300.00")
    assert prods[1].net_historical_cogs == Decimal("180.00")
    assert prods[1].direct_margin == Decimal("120.00")

    # Rank #3: P3 (return-only)
    assert prods[2].product_id == p3.id
    assert prods[2].quantity_sold == 0
    assert prods[2].quantity_returned == 1
    assert prods[2].net_units_sold == -1
    assert prods[2].net_gross_revenue == Decimal("-500.00")
    assert prods[2].net_historical_cogs == Decimal("-300.00")
    assert prods[2].direct_margin == Decimal("-200.00")


# ── 8. Refunds by Method Channel Breakdown ────────────────────────────

def test_refund_method_breakdown_and_zero_guard(db_session, test_users, catalog_products):
    """
    Refunds breakdown: 75.00% CASH and 25.00% ORIGINAL_METHOD.
    Empty period returns empty list without division-by-zero error.
    """
    sales_service = SalesService(db_session)
    returns_service = ReturnsService(db_session)
    report_service = ReportService(db_session)

    admin = test_users["admin"]
    cashier = test_users["cashier_a"]
    p1 = catalog_products["p1"]

    # 1. Empty period test (zero guard)
    empty_refs = report_service.get_refund_method_breakdown(date(2025, 1, 1), date(2025, 1, 1), actor=admin)
    assert empty_refs == []

    # 2. Checkout 2 sales
    # Sale 1: 3 * ₱100 = ₱300 + ₱36 tax = ₱336
    sale1 = sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[CartItemDTO(product_id=p1.id, sku=p1.sku, name=p1.name, quantity=3, unit_price=Decimal("100.00"))],
            payment_method="CASH",
            amount_tendered=Decimal("336.00"),
            discount_amount=Decimal("0.00"),
        ),
        cashier,
    )
    # Sale 2: 1 * ₱100 = ₱100 + ₱12 tax = ₱112
    sale2 = sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[CartItemDTO(product_id=p1.id, sku=p1.sku, name=p1.name, quantity=1, unit_price=Decimal("100.00"))],
            payment_method="GCASH",
            amount_tendered=Decimal("112.00"),
            discount_amount=Decimal("0.00"),
        ),
        cashier,
    )
    db_session.commit()

    # 3. Process returns
    ret_items1 = returns_service.get_returnable_items(sale1.id, cashier)
    returns_service.process_return(
        ProcessReturnRequestDTO(
            sale_id=sale1.id,
            reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
            refund_payment_method=RefundMethod.CASH.value,
            items=[ReturnItemRequestDTO(sale_line_item_id=ret_items1[0].sale_line_item_id, quantity=3, disposition=ReturnDisposition.RESTOCK.value)],
        ),
        actor=cashier,
        approver=admin,
        idempotency_key="REF-METHOD-001",
    )

    ret_items2 = returns_service.get_returnable_items(sale2.id, cashier)
    returns_service.process_return(
        ProcessReturnRequestDTO(
            sale_id=sale2.id,
            reason_code=ReturnReason.CUSTOMER_CHANGE_MIND.value,
            refund_payment_method=RefundMethod.ORIGINAL_METHOD.value,
            refund_reference="REF-GCASH-12345",
            items=[ReturnItemRequestDTO(sale_line_item_id=ret_items2[0].sale_line_item_id, quantity=1, disposition=ReturnDisposition.RESTOCK.value)],
        ),
        actor=cashier,
        approver=admin,
        idempotency_key="REF-METHOD-002",
    )
    db_session.commit()

    # 4. Query Refund Breakdown
    today = date.today()
    ref_breakdown = report_service.get_refund_method_breakdown(today, today, actor=admin)
    assert len(ref_breakdown) == 2

    cash_ref = next(r for r in ref_breakdown if r.refund_method.lower() == "cash")
    assert cash_ref.return_count == 1
    assert cash_ref.total_refund_amount == Decimal("336.00")
    assert cash_ref.percentage == Decimal("75.00")

    orig_ref = next(r for r in ref_breakdown if r.refund_method.lower() in ("original_method", "gcash"))
    assert orig_ref.return_count == 1
    assert orig_ref.total_refund_amount == Decimal("112.00")
    assert orig_ref.percentage == Decimal("25.00")
