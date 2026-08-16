"""
RetailFlow POS - ReportExportService Tests
Comprehensive verification of permission enforcement, CSV formula injection protection,
UTF-8-SIG encoding, Decimal formatting, predictable filenames, and all 5 report export datasets.
"""

from datetime import date
from decimal import Decimal
import os
import tempfile
import pytest

from application.dto.report_dto import (
    CashierPerformanceDTO,
    DailyFinancialPointDTO,
    ExpenseCategoryBreakdownDTO,
    FinancialSummaryDTO,
    InventoryValueDTO,
    PaymentMethodSummaryDTO,
    ProductPerformanceDTO,
    PurchaseIntakeSummaryDTO,
)
from application.services.report_export_service import (
    ReportExportService,
    sanitize_csv_text,
    sanitize_filename,
)
from application.services.report_service import ReportService
from domain.exceptions import AuthorizationError
from infrastructure.database.models.auth import Permission, Role, User
from unittest.mock import MagicMock


@pytest.fixture
def mock_report_service():
    service = MagicMock(spec=ReportService)

    sample_summary = FinancialSummaryDTO(
        start_date="2026-08-01",
        end_date="2026-08-15",
        gross_sales=Decimal("30000.00"),
        discounts=Decimal("2000.00"),
        net_sales=Decimal("28000.00"),
        output_vat=Decimal("3360.00"),
        total_collections=Decimal("31360.00"),
        cogs=Decimal("16000.00"),
        gross_profit=Decimal("12000.00"),
        gross_margin_percent=Decimal("42.86"),
        operating_expenses=Decimal("4000.00"),
        net_operating_profit=Decimal("8000.00"),
        net_operating_margin_percent=Decimal("28.57"),
    )
    service.get_financial_summary.return_value = sample_summary

    sample_products = [
        ProductPerformanceDTO(
            product_id=1,
            sku="=CMD|' /C calc'!A0",
            product_name="@Formula Injected Item",
            quantity_sold=50,
            gross_revenue=Decimal("15000.00"),
            historical_cogs=Decimal("8000.00"),
            direct_margin_before_order_discount=Decimal("7000.00"),
        ),
        ProductPerformanceDTO(
            product_id=2,
            sku="SKU-BETA",
            product_name="Standard Product (Special 'Edition', 500g)",
            quantity_sold=30,
            gross_revenue=Decimal("9000.00"),
            historical_cogs=Decimal("5000.00"),
            direct_margin_before_order_discount=Decimal("4000.00"),
        ),
    ]
    service.get_product_performance.return_value = sample_products

    sample_cashiers = [
        CashierPerformanceDTO(
            cashier_id=1,
            cashier_name="+Admin Cashier",
            transaction_count=25,
            net_sales=Decimal("20000.00"),
            collections=Decimal("22400.00"),
            average_order_value=Decimal("800.00"),
            discounts=Decimal("1500.00"),
            units_sold=65,
        ),
    ]
    service.get_cashier_performance.return_value = sample_cashiers

    sample_opex = [
        ExpenseCategoryBreakdownDTO(
            category="utilities",
            category_display="Utilities (Power, Water, Internet)",
            amount=Decimal("2400.00"),
            percentage=Decimal("60.00"),
        ),
        ExpenseCategoryBreakdownDTO(
            category="supplies",
            category_display="Store Supplies & Packaging",
            amount=Decimal("1600.00"),
            percentage=Decimal("40.00"),
        ),
    ]
    service.get_expense_category_breakdown.return_value = sample_opex

    sample_payments = [
        PaymentMethodSummaryDTO(
            payment_method="CASH",
            payment_method_display="Cash (Over-The-Counter)",
            transaction_count=20,
            total_amount=Decimal("20000.00"),
            percentage=Decimal("63.78"),
        ),
        PaymentMethodSummaryDTO(
            payment_method="GCASH",
            payment_method_display="GCash / QR",
            transaction_count=10,
            total_amount=Decimal("11360.00"),
            percentage=Decimal("36.22"),
        ),
    ]
    service.get_payment_method_breakdown.return_value = sample_payments

    return service


@pytest.fixture
def test_admin_user(db_session):
    perm_report = Permission(code="view_reports", name="View Reports", module="reports")
    perm_export = Permission(code="export_reports", name="Export Reports", module="reports")
    db_session.add_all([perm_report, perm_export])
    db_session.flush()

    admin_role = Role(name="Admin", code="admin", permissions=[perm_report, perm_export])
    db_session.add(admin_role)
    db_session.flush()

    user = User(username="admin_export_test", password_hash="hash", full_name="Admin Exporter", roles=[admin_role])
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_cashier_user(db_session):
    user = User(username="cashier_export_test", password_hash="hash", full_name="Cashier No Export", roles=[])
    db_session.add(user)
    db_session.commit()
    return user


def test_sanitize_csv_text_formula_injection():
    """Formulas starting with =, +, -, @, tab are safely prefixed with single quote."""
    assert sanitize_csv_text("=SUM(A1:A10)") == "'=SUM(A1:A10)"
    assert sanitize_csv_text("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"
    assert sanitize_csv_text("-1+1") == "'-1+1"
    assert sanitize_csv_text("@SOMETHING") == "'@SOMETHING"
    assert sanitize_csv_text("\tTABBED") == "'\tTABBED"
    assert sanitize_csv_text("Normal Product Name") == "Normal Product Name"
    assert sanitize_csv_text("") == ""
    assert sanitize_csv_text(None) == ""


def test_sanitize_filename_illegal_chars():
    """Filenames with illegal Windows characters are safely sanitized."""
    assert sanitize_filename("report:2026/08/15*final?.csv") == "report_2026_08_15_final_.csv"


def test_export_filename_generation():
    """Predictable filenames generated for all report types."""
    start = date(2026, 8, 1)
    end = date(2026, 8, 15)
    fn = ReportExportService.get_default_filename("Financial Summary", start, end)
    assert fn == "retailflow_financial_summary_2026-08-01_to_2026-08-15.csv"

    fn_prod = ReportExportService.get_default_filename("Product Performance", start, end)
    assert fn_prod == "retailflow_product_performance_2026-08-01_to_2026-08-15.csv"


def test_export_financial_summary_csv(mock_report_service, test_admin_user):
    """Financial Summary CSV exports metadata, 2-decimal numbers, and disclaimer in UTF-8-SIG."""
    exporter = ReportExportService(mock_report_service)
    start = date(2026, 8, 1)
    end = date(2026, 8, 15)

    with tempfile.TemporaryDirectory() as tmp_dir:
        target_path = os.path.join(tmp_dir, "fin_summary.csv")
        content = exporter.export_financial_summary_csv(start, end, test_admin_user, target_path)

        assert os.path.exists(target_path)
        with open(target_path, "rb") as f:
            raw_bytes = f.read()
            # Verify UTF-8-SIG BOM
            assert raw_bytes.startswith(b"\xef\xbb\xbf")

        # Content verification
        assert "RetailFlow POS - Executive Financial Summary" in content
        assert "Gross Sales,30000.00," in content
        assert "Net Sales,28000.00," in content
        assert "Gross Margin (%),,42.86" in content
        assert "Net Operating Profit,8000.00," in content
        assert "Net Operating Margin (%),,28.57" in content
        assert "Gross Output VAT,3360.00," in content
        assert "Gross Collections (Total Tendered),31360.00," in content


def test_export_product_performance_csv_sanitization(mock_report_service, test_admin_user):
    """Product performance CSV sanitizes injected formulas and quotes commas."""
    exporter = ReportExportService(mock_report_service)
    start = date(2026, 8, 1)
    end = date(2026, 8, 15)

    content = exporter.export_product_performance_csv(start, end, test_admin_user)

    # Injected =CMD and @Formula must be prefixed with single quote
    assert "'=CMD|' /C calc'!A0" in content
    assert "'@Formula Injected Item" in content
    # Embedded comma and quote properly quoted by csv module
    assert '"Standard Product (Special \'Edition\', 500g)"' in content
    assert "15000.00,8000.00,7000.00" in content or "15000.00,0.00,15000.00,8000.00,7000.00" in content


def test_export_cashier_performance_csv(mock_report_service, test_admin_user):
    """Cashier performance CSV distinguishes Net Sales from Total Collections."""
    exporter = ReportExportService(mock_report_service)
    start = date(2026, 8, 1)
    end = date(2026, 8, 15)

    content = exporter.export_cashier_performance_csv(start, end, test_admin_user)

    assert "'+Admin Cashier,25,65,0,65,20000.00,22400.00,0.00,22400.00,800.00,1500.00" in content


def test_export_opex_breakdown_csv(mock_report_service, test_admin_user):
    """OPEX breakdown CSV includes category rows and total summary."""
    exporter = ReportExportService(mock_report_service)
    start = date(2026, 8, 1)
    end = date(2026, 8, 15)

    content = exporter.export_opex_breakdown_csv(start, end, test_admin_user)

    assert '"Utilities (Power, Water, Internet)",2400.00,60.00' in content
    assert "Store Supplies & Packaging,1600.00,40.00" in content
    assert "TOTAL OPERATING EXPENSES,4000.00,100.00" in content


def test_export_payment_methods_csv(mock_report_service, test_admin_user):
    """Payment methods CSV exports collections channels and total collections."""
    exporter = ReportExportService(mock_report_service)
    start = date(2026, 8, 1)
    end = date(2026, 8, 15)

    content = exporter.export_payment_methods_csv(start, end, test_admin_user)

    assert "Cash (Over-The-Counter),20,20000.00,63.78" in content
    assert "GCash / QR,10,11360.00,36.22" in content
    assert "TOTAL COLLECTIONS,30,31360.00,100.00" in content


def test_export_permission_enforcement_raises_authorization_error(mock_report_service, test_cashier_user):
    """Users without export_reports permission cannot invoke export methods."""
    exporter = ReportExportService(mock_report_service)
    start = date(2026, 8, 1)
    end = date(2026, 8, 15)

    with pytest.raises(AuthorizationError) as exc_info:
        exporter.export_financial_summary_csv(start, end, test_cashier_user)
    assert "does not have permission 'export_reports'" in str(exc_info.value)

    with pytest.raises(AuthorizationError):
        exporter.export_product_performance_csv(start, end, test_cashier_user)

    with pytest.raises(AuthorizationError):
        exporter.export_cashier_performance_csv(start, end, test_cashier_user)

    with pytest.raises(AuthorizationError):
        exporter.export_opex_breakdown_csv(start, end, test_cashier_user)

    with pytest.raises(AuthorizationError):
        exporter.export_payment_methods_csv(start, end, test_cashier_user)
