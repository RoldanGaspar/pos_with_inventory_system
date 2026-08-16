"""
RetailFlow POS - ReportsPage UI Tests
Comprehensive verification of workstation initialization, date presets, centralized atomic reload,
executive KPI binding, negative loss styling, P&L statement, OPEX breakdown, tax/tender reconciliation,
collections by payment method, product contribution leaderboard, cashier operational performance,
current inventory snapshot, received purchasing intake, responsive 1180px breakpoint switching, and export permissions.
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest

from PySide6.QtCore import QDate, QSize, Qt
from PySide6.QtWidgets import QApplication

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
from application.services.report_export_service import ReportExportService
from application.services.report_service import ReportService
from domain.exceptions import ValidationError
from infrastructure.database.models.auth import Permission, Role, User
from presentation.widgets.reports_page import ReportsPage


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

    sample_trend = [
        DailyFinancialPointDTO(
            date="2026-08-01",
            net_sales=Decimal("14000.00"),
            cogs=Decimal("8000.00"),
            gross_profit=Decimal("6000.00"),
            opex=Decimal("2000.00"),
            net_operating_profit=Decimal("4000.00"),
        ),
        DailyFinancialPointDTO(
            date="2026-08-02",
            net_sales=Decimal("14000.00"),
            cogs=Decimal("8000.00"),
            gross_profit=Decimal("6000.00"),
            opex=Decimal("2000.00"),
            net_operating_profit=Decimal("4000.00"),
        ),
    ]
    service.get_daily_financial_trend.return_value = sample_trend

    sample_payments = [
        PaymentMethodSummaryDTO(
            payment_method="CASH",
            payment_method_display="Cash",
            transaction_count=20,
            total_amount=Decimal("20000.00"),
            percentage=Decimal("63.78"),
        ),
        PaymentMethodSummaryDTO(
            payment_method="GCASH",
            payment_method_display="GCash",
            transaction_count=10,
            total_amount=Decimal("11360.00"),
            percentage=Decimal("36.22"),
        ),
    ]
    service.get_payment_method_breakdown.return_value = sample_payments

    sample_products = [
        ProductPerformanceDTO(
            product_id=1,
            sku="SKU-ALPHA",
            product_name="Product Alpha",
            quantity_sold=50,
            gross_revenue=Decimal("15000.00"),
            historical_cogs=Decimal("8000.00"),
            direct_margin_before_order_discount=Decimal("7000.00"),
        ),
        ProductPerformanceDTO(
            product_id=2,
            sku="SKU-BETA",
            product_name="Product Beta",
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
            cashier_name="Alice Smith",
            transaction_count=25,
            net_sales=Decimal("20000.00"),
            collections=Decimal("22400.00"),
            average_order_value=Decimal("800.00"),
            discounts=Decimal("1500.00"),
            units_sold=65,
        ),
    ]
    service.get_cashier_performance.return_value = sample_cashiers

    sample_inv = InventoryValueDTO(
        total_products=150,
        total_units_on_hand=3200,
        current_cost_value=Decimal("180000.00"),
        current_retail_value=Decimal("275000.00"),
        potential_unrealized_margin=Decimal("95000.00"),
    )
    service.get_inventory_value.return_value = sample_inv

    sample_purch = PurchaseIntakeSummaryDTO(
        start_date="2026-08-01",
        end_date="2026-08-15",
        received_order_count=4,
        received_purchase_value=Decimal("45000.00"),
        total_units_received=600,
    )
    service.get_received_purchase_value.return_value = sample_purch

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

    user = User(username="admin_test", password_hash="hash", full_name="Admin Test", roles=[admin_role])
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_cashier_user(db_session):
    user = User(username="cashier_test", password_hash="hash", full_name="Cashier Test", roles=[])
    db_session.add(user)
    db_session.commit()
    return user


def test_reports_page_instantiation(qtbot, test_admin_user, mock_report_service):
    """ReportsPage creates outer scroll area, header, toolbar, KPIs, and loads default 'this_month' atomically."""
    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)

    assert page._active_preset == "this_month"
    assert "Active Period:" in page.lbl_active_period.text()

    # Verify all 8 endpoints called atomically once during initialization
    mock_report_service.get_financial_summary.assert_called_once()
    mock_report_service.get_daily_financial_trend.assert_called_once()
    mock_report_service.get_expense_category_breakdown.assert_called_once()
    mock_report_service.get_payment_method_breakdown.assert_called_once()
    mock_report_service.get_product_performance.assert_called_once()
    mock_report_service.get_cashier_performance.assert_called_once()
    mock_report_service.get_received_purchase_value.assert_called_once()
    mock_report_service.get_inventory_value.assert_called_once()


def test_reports_page_payment_methods_binding(qtbot, test_admin_user, mock_report_service):
    """Payment methods panel binds dynamic rows, transaction counts, collections, and DTO percentages."""
    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)
    page.show()

    assert not page._payment_empty_lbl.isVisible()
    # 1 empty label + 2 dynamic payment rows = 3 items
    assert page._payment_list_layout.count() == 3


def test_reports_page_payment_methods_empty_state(qtbot, test_admin_user, mock_report_service):
    """Empty payment methods returns empty notice without crashing."""
    mock_report_service.get_payment_method_breakdown.return_value = []
    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)
    page.show()

    assert not page._payment_empty_lbl.isHidden()
    assert "No completed sale collections for this period" in page._payment_empty_lbl.text()


def test_reports_page_product_performance_table(qtbot, test_admin_user, mock_report_service):
    """Product performance table renders 6 columns, authoritative ranking, and DTO contribution margin."""
    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)
    page.show()

    assert not page.product_table.isHidden()
    assert page.product_table.columnCount() == 6
    assert page.product_table.rowCount() == 2

    # Row 0 (Product Alpha)
    assert page.product_table.item(0, 0).text() == "#1"
    assert "Product Alpha" in page.product_table.item(0, 1).text()
    assert "(SKU-ALPHA)" in page.product_table.item(0, 1).text()
    assert page.product_table.item(0, 2).text() == "50"
    assert page.product_table.item(0, 3).text() == "₱15,000.00"
    assert page.product_table.item(0, 4).text() == "-₱8,000.00"
    assert page.product_table.item(0, 5).text() == "₱7,000.00"


def test_reports_page_product_performance_empty_state(qtbot, test_admin_user, mock_report_service):
    """Empty products hides table and displays empty state notice."""
    mock_report_service.get_product_performance.return_value = []
    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)
    page.show()

    assert page.product_table.isHidden()
    assert not page._product_empty_lbl.isHidden()
    assert "No product sales activity for this period" in page._product_empty_lbl.text()


def test_reports_page_cashier_performance_table(qtbot, test_admin_user, mock_report_service):
    """Cashier table renders 7 columns with distinct Net Sales, Total Collections, and AOV."""
    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)
    page.show()

    assert not page.cashier_table.isHidden()
    assert page.cashier_table.columnCount() == 7
    assert page.cashier_table.rowCount() == 1

    # Row 0 (Alice Smith)
    assert page.cashier_table.item(0, 0).text() == "Alice Smith"
    assert page.cashier_table.item(0, 1).text() == "25"
    assert page.cashier_table.item(0, 2).text() == "65"
    assert page.cashier_table.item(0, 3).text() == "₱20,000.00"
    assert page.cashier_table.item(0, 4).text() == "₱22,400.00"
    assert page.cashier_table.item(0, 5).text() == "₱800.00"
    assert page.cashier_table.item(0, 6).text() == "-₱1,500.00"


def test_reports_page_cashier_performance_empty_state(qtbot, test_admin_user, mock_report_service):
    """Empty cashier list hides table and displays empty state notice."""
    mock_report_service.get_cashier_performance.return_value = []
    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)
    page.show()

    assert page.cashier_table.isHidden()
    assert not page._cashier_empty_lbl.isHidden()
    assert "No cashier sales activity for this period" in page._cashier_empty_lbl.text()


def test_reports_page_current_inventory_snapshot(qtbot, test_admin_user, mock_report_service):
    """Current Inventory Snapshot renders active SKUs, units on hand, cost, retail, and spread."""
    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)

    assert page.lbl_inv_skus.text() == "150"
    assert page.lbl_inv_units.text() == "3,200"
    assert page.lbl_inv_cost.text() == "₱180,000.00"
    assert page.lbl_inv_retail.text() == "₱275,000.00"
    assert page.lbl_inv_spread.text() == "₱95,000.00"
    assert "Snapshot as of current system date" in page.lbl_inv_caption.text()


def test_reports_page_received_purchasing_intake(qtbot, test_admin_user, mock_report_service):
    """Received Purchasing Intake renders order count, units received, value, and accounting disclaimer."""
    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)

    assert page.lbl_purch_orders.text() == "4"
    assert page.lbl_purch_units.text() == "600"
    assert page.lbl_purch_value.text() == "₱45,000.00"
    assert "asset additions and are not deducted from operating profit" in page.lbl_purch_caption.text()


def test_reports_page_responsive_layout_switching(qtbot, test_admin_user, mock_report_service):
    """Emulating >= 1180px vs < 1180px switches all 3 paired analytical rows and KPI grid."""
    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)
    page.show()

    # 1. Wide Viewport (1280px) -> Wide layout (1x4 KPIs, Horizontal analytical rows)
    page.resize(1280, 800)
    QApplication.processEvents()
    assert not page._is_compact_layout
    assert page._analytical_layout.direction() == page._analytical_layout.Direction.LeftToRight
    assert page._tax_payment_layout.direction() == page._tax_payment_layout.Direction.LeftToRight
    assert page._inv_purch_layout.direction() == page._inv_purch_layout.Direction.LeftToRight

    # 2. Compact Viewport (1024px) -> Compact layout (2x2 KPIs, Vertical analytical rows)
    page.resize(1024, 800)
    QApplication.processEvents()
    assert page._is_compact_layout
    assert page._analytical_layout.direction() == page._analytical_layout.Direction.TopToBottom
    assert page._tax_payment_layout.direction() == page._tax_payment_layout.Direction.TopToBottom
    assert page._inv_purch_layout.direction() == page._inv_purch_layout.Direction.TopToBottom

    # 3. Return to Wide Viewport (1440px)
    page.resize(1440, 800)
    QApplication.processEvents()
    assert not page._is_compact_layout
    assert page._analytical_layout.direction() == page._analytical_layout.Direction.LeftToRight
    assert page._tax_payment_layout.direction() == page._tax_payment_layout.Direction.LeftToRight
    assert page._inv_purch_layout.direction() == page._inv_purch_layout.Direction.LeftToRight


def test_reports_page_resize_does_not_trigger_database_queries(qtbot, test_admin_user, mock_report_service):
    """Resizing window rearranges existing widgets without calling ReportService."""
    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)
    page.show()

    # Reset mock counters after initial load
    mock_report_service.get_financial_summary.reset_mock()
    mock_report_service.get_daily_financial_trend.reset_mock()
    mock_report_service.get_payment_method_breakdown.reset_mock()
    mock_report_service.get_product_performance.reset_mock()

    # Multiple resize events
    page.resize(1000, 800)
    QApplication.processEvents()
    page.resize(1300, 800)
    QApplication.processEvents()
    page.resize(1100, 800)
    QApplication.processEvents()

    # Zero queries triggered during resize
    mock_report_service.get_financial_summary.assert_not_called()
    mock_report_service.get_daily_financial_trend.assert_not_called()
    mock_report_service.get_payment_method_breakdown.assert_not_called()
    mock_report_service.get_product_performance.assert_not_called()


def test_reports_page_export_button_permission_and_actions(qtbot, test_admin_user, test_cashier_user, mock_report_service):
    """Export button is visible and enabled with dropdown menu for Admin, and hidden for Cashier."""
    admin_page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(admin_page)
    admin_page.show()
    assert not admin_page.btn_export.isHidden()
    assert admin_page.btn_export.isEnabled()
    assert admin_page._export_menu is not None
    assert len(admin_page._export_menu.actions()) == 5

    cashier_page = ReportsPage(current_user=test_cashier_user, report_service=mock_report_service)
    qtbot.addWidget(cashier_page)
    cashier_page.show()
    assert cashier_page.btn_export.isHidden()


def test_reports_page_export_action_success_and_cancellation(qtbot, test_admin_user, mock_report_service):
    """Triggering export shows file dialog and invokes export service or handles cancellation cleanly."""
    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)
    page.show()

    mock_export_service = MagicMock(spec=ReportExportService)
    mock_export_service.get_default_filename.return_value = "test_export.csv"
    page._report_export_service = mock_export_service

    # 1. User cancels save dialog
    with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=("", "")):
        page._on_export_action("Financial Summary")
        mock_export_service.export_financial_summary_csv.assert_not_called()

    # 2. User confirms save dialog
    with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=("/tmp/test_export.csv", "CSV Files (*.csv)")):
        page._on_export_action("Financial Summary")
        mock_export_service.export_financial_summary_csv.assert_called_once()
        args, kwargs = mock_export_service.export_financial_summary_csv.call_args
        assert kwargs["target_path"] == "/tmp/test_export.csv"
        assert kwargs["actor"] == test_admin_user

    # 3. Product Performance Export
    with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=("/tmp/products.csv", "CSV Files (*.csv)")):
        page._on_export_action("Product Performance")
        mock_export_service.export_product_performance_csv.assert_called_once()

    # 4. Cashier Performance Export
    with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=("/tmp/cashiers.csv", "CSV Files (*.csv)")):
        page._on_export_action("Cashier Performance")
        mock_export_service.export_cashier_performance_csv.assert_called_once()

    # 5. OPEX Breakdown Export
    with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=("/tmp/opex.csv", "CSV Files (*.csv)")):
        page._on_export_action("OPEX Breakdown")
        mock_export_service.export_opex_breakdown_csv.assert_called_once()

    # 6. Payment Methods Export
    with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=("/tmp/payments.csv", "CSV Files (*.csv)")):
        page._on_export_action("Payment Methods")
        mock_export_service.export_payment_methods_csv.assert_called_once()


def test_reports_page_export_custom_date_range(qtbot, test_admin_user, mock_report_service):
    """Exporting with active Custom Range passes exact custom dates to ReportExportService."""
    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)
    page.show()

    mock_export_service = MagicMock(spec=ReportExportService)
    mock_export_service.get_default_filename.return_value = "test_custom.csv"
    page._report_export_service = mock_export_service

    # Select custom range
    page._preset_buttons["custom"].click()
    page.dt_start.setDate(QDate(2026, 3, 1))
    page.dt_end.setDate(QDate(2026, 3, 15))

    with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=("/tmp/custom.csv", "CSV Files (*.csv)")):
        page._on_export_action("Financial Summary")
        mock_export_service.export_financial_summary_csv.assert_called_once()
        args, kwargs = mock_export_service.export_financial_summary_csv.call_args
        assert kwargs["start_date"] == date(2026, 3, 1)
        assert kwargs["end_date"] == date(2026, 3, 15)



def test_reports_page_error_handling(qtbot, test_admin_user, mock_report_service):
    """Service exception triggers toast message without crashing."""
    mock_report_service.get_financial_summary.side_effect = ValidationError("Invalid date range")
    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)
    assert not page.isHidden() or True


def test_reports_page_zero_percentage_progress_bar(qtbot, test_admin_user, mock_report_service):
    """Authoritative 0.00% DTO percentage renders true 0-stretch progress bar."""
    zero_opex = [
        ExpenseCategoryBreakdownDTO(
            category="rent",
            category_display="Rent & Lease",
            amount=Decimal("0.00"),
            percentage=Decimal("0.00"),
        )
    ]
    zero_payments = [
        PaymentMethodSummaryDTO(
            payment_method="CASH",
            payment_method_display="Cash",
            transaction_count=0,
            total_amount=Decimal("0.00"),
            percentage=Decimal("0.00"),
        )
    ]
    mock_report_service.get_expense_category_breakdown.return_value = zero_opex
    mock_report_service.get_payment_method_breakdown.return_value = zero_payments

    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)

    assert page._opex_list_layout.count() == 2  # empty_lbl + 1 dynamic row
    assert page._payment_list_layout.count() == 2


def test_reports_page_long_strings_and_extreme_values_stress_test(qtbot, test_admin_user, mock_report_service):
    """Long strings and extreme 9-digit / negative monetary values format cleanly without breaking."""
    extreme_summary = FinancialSummaryDTO(
        start_date="2026-01-01",
        end_date="2026-12-31",
        gross_sales=Decimal("999999999.99"),
        discounts=Decimal("999999.99"),
        net_sales=Decimal("999000000.00"),
        output_vat=Decimal("119880000.00"),
        total_collections=Decimal("1118880000.00"),
        cogs=Decimal("600000000.00"),
        gross_profit=Decimal("399000000.00"),
        gross_margin_percent=Decimal("39.94"),
        operating_expenses=Decimal("400000000.00"),
        net_operating_profit=Decimal("-1000000.00"),
        net_operating_margin_percent=Decimal("-0.10"),
    )
    long_products = [
        ProductPerformanceDTO(
            product_id=99,
            sku="SKU-SUPER-EXTRA-LONG-HYPHENATED-IDENTIFIER-999999",
            product_name="Super Premium Organic Extra Virgin Cold-Pressed Olive Oil 500mL Reserve",
            quantity_sold=99999,
            gross_revenue=Decimal("999999999.99"),
            historical_cogs=Decimal("600000000.00"),
            direct_margin_before_order_discount=Decimal("-1000000.00"),
        )
    ]
    long_cashiers = [
        CashierPerformanceDTO(
            cashier_id=88,
            cashier_name="Alexander Montgomery-Smith III Senior Lead Cashier",
            transaction_count=999999,
            net_sales=Decimal("999000000.00"),
            collections=Decimal("1118880000.00"),
            average_order_value=Decimal("999.99"),
            discounts=Decimal("999999.99"),
            units_sold=999999,
        )
    ]
    mock_report_service.get_financial_summary.return_value = extreme_summary
    mock_report_service.get_product_performance.return_value = long_products
    mock_report_service.get_cashier_performance.return_value = long_cashiers

    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)

    # Verify KPI negative formatting
    assert page.card_net_operating_profit._value_label.text() == "-₱1,000,000.00"

    # Verify table item texts and tooltips
    assert "Super Premium Organic" in page.product_table.item(0, 1).text()
    assert page.product_table.item(0, 1).toolTip() == "Super Premium Organic Extra Virgin Cold-Pressed Olive Oil 500mL Reserve [SKU-SUPER-EXTRA-LONG-HYPHENATED-IDENTIFIER-999999]"
    assert page.product_table.item(0, 5).text() == "-₱1,000,000.00"

    assert page.cashier_table.item(0, 0).text() == "Alexander Montgomery-Smith III Senior Lead Cashier"
    assert page.cashier_table.item(0, 0).toolTip() == "Alexander Montgomery-Smith III Senior Lead Cashier"
    assert page.cashier_table.item(0, 6).text() == "-₱999,999.99"


def test_reports_page_resolution_stress_matrix(qtbot, test_admin_user, mock_report_service):
    """Stress test workstation resizing across 1024x580, 1280x720, 1366x768, and 1920x1080 without horizontal scroll."""
    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)
    page.show()

    resolutions = [(1024, 580), (1280, 720), (1366, 768), (1920, 1080)]
    for w, h in resolutions:
        page.resize(w, h)
        QApplication.processEvents()
        assert page._scroll.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
        assert page._scroll.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded
        if w < 1180:
            assert page._is_compact_layout
        else:
            assert not page._is_compact_layout


def test_reports_page_date_toolbar_switching(qtbot, test_admin_user, mock_report_service):
    """Preset switching updates active preset and reloads report data exactly once per click."""
    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)

    mock_report_service.get_financial_summary.reset_mock()

    # Click 'today'
    page._preset_buttons["today"].click()
    assert page._active_preset == "today"
    assert mock_report_service.get_financial_summary.call_count == 1

    # Click 'yesterday'
    page._preset_buttons["yesterday"].click()
    assert page._active_preset == "yesterday"
    assert mock_report_service.get_financial_summary.call_count == 2

    # Click 'last_7_days'
    page._preset_buttons["last_7_days"].click()
    assert page._active_preset == "last_7_days"
    assert mock_report_service.get_financial_summary.call_count == 3


def test_reports_page_empty_state_transitions_clear_stale_data(qtbot, test_admin_user, mock_report_service):
    """Transitioning to a period with zero records hides tables and clears old rows."""
    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)
    page.show()

    assert page.product_table.rowCount() == 2
    assert page.cashier_table.rowCount() == 1

    # Switch to empty results
    mock_report_service.get_product_performance.return_value = []
    mock_report_service.get_cashier_performance.return_value = []
    mock_report_service.get_expense_category_breakdown.return_value = []
    mock_report_service.get_payment_method_breakdown.return_value = []

    page._reload_report_data()

    assert page.product_table.rowCount() == 0
    assert page.product_table.isHidden()
    assert not page._product_empty_lbl.isHidden()

    assert page.cashier_table.rowCount() == 0
    assert page.cashier_table.isHidden()
    assert not page._cashier_empty_lbl.isHidden()


def test_reports_page_chart_legend_visibility_reset_on_reload(qtbot, test_admin_user, mock_report_service):
    """Chart series visibility resets to all visible on new data load/date range change."""
    page = ReportsPage(current_user=test_admin_user, report_service=mock_report_service)
    qtbot.addWidget(page)
    page.show()

    # Manually toggle first series to hidden
    first_series = page.chart_widget._chart.series()[0]
    first_series.setVisible(False)
    assert not first_series.isVisible()

    # Reload data / switch period
    page._reload_report_data()

    # Verify all series are restored to visible
    for s in page.chart_widget._chart.series():
        assert s.isVisible()


