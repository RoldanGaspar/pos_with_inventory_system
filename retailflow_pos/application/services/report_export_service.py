"""
RetailFlow POS - Report Export Service (Phase 5B Production)
Permission-aware, injection-safe CSV export service for financial, product, cashier, and refund reports.
Operates strictly on authoritative ReportService DTO contracts with UTF-8-SIG encoding
and standard machine-readable numeric formats.
"""

import csv
from datetime import date, datetime
from decimal import Decimal
import io
import os
import re
from typing import Optional

from application.services.report_service import ReportService
from domain.exceptions import AuthorizationError, ValidationError
from infrastructure.database.models.auth import User


def sanitize_csv_text(val: Optional[str]) -> str:
    """
    Sanitize text cells to prevent CSV formula injection in spreadsheet applications.
    Prefixes cell with a single quote if the first character is an executable symbol (=, +, -, @, tab, cr).
    """
    if val is None:
        return ""
    s = str(val)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{s}"
    return s


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to remove illegal filesystem characters."""
    return re.sub(r'[\\/*?:"<>|]', "_", filename)


class ReportExportService:
    """
    Application service for generating standardized CSV exports of financial reports.
    Enforces authorization, generates Excel-friendly UTF-8-SIG encoded files,
    and protects against spreadsheet formula injection.
    """

    def __init__(self, report_service: ReportService):
        self._report_service = report_service

    def _check_export_permission(self, actor: User) -> None:
        """Enforce export_reports permission."""
        if not actor:
            raise AuthorizationError("Actor is required for export operations")
        if hasattr(actor, "is_admin") and actor.is_admin():
            return
        if not actor.has_permission("export_reports"):
            raise AuthorizationError(f"User '{actor.username}' does not have permission 'export_reports'")

    @staticmethod
    def _get_timestamp_header() -> str:
        """Get canonical timestamp string in Asia/Manila context."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " (Asia/Manila)"

    @staticmethod
    def get_default_filename(export_type: str, start_date: date, end_date: date) -> str:
        """Generate predictable, clean export filename."""
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        clean_type = sanitize_filename(export_type.lower().replace(" ", "_"))
        return f"retailflow_{clean_type}_{start_str}_to_{end_str}.csv"

    # ── 1. Executive Financial Summary Export ─────────────────────────

    def export_financial_summary_csv(
        self,
        start_date: date,
        end_date: date,
        actor: User,
        target_path: Optional[str] = None,
    ) -> str:
        """
        Export Executive Financial Summary to CSV (UTF-8-SIG).
        Returns CSV string content or writes to target_path if provided.
        """
        self._check_export_permission(actor)
        summary = self._report_service.get_financial_summary(start_date, end_date, actor)

        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        # Metadata block
        writer.writerow(["Report", "RetailFlow POS - Executive Financial Summary"])
        writer.writerow(["Period Start", summary.start_date])
        writer.writerow(["Period End", summary.end_date])
        writer.writerow(["Generated At", self._get_timestamp_header()])
        writer.writerow([
            "Note",
            "Output VAT and Total Collections are operational tax & tender reconciliation metrics and excluded from operating revenue.",
        ])
        writer.writerow([])

        # Table Header
        writer.writerow(["Financial Metric", "Amount (PHP)", "Margin (%)"])

        # P&L Waterfall Rows (Numeric cells formatted with 2 decimal places, no currency symbols)
        writer.writerow(["Gross Sales", f"{summary.gross_sales:.2f}", ""])
        writer.writerow(["Less: Discounts Granted", f"-{summary.discounts:.2f}", ""])
        writer.writerow(["Less: Customer Returns", f"-{summary.sales_returns:.2f}", ""])
        writer.writerow(["Net Sales", f"{summary.net_sales:.2f}", ""])
        writer.writerow(["Less: Cost of Goods Sold (COGS)", f"-{summary.cogs:.2f}", ""])
        writer.writerow(["Gross Profit", f"{summary.gross_profit:.2f}", ""])
        writer.writerow(["Gross Margin (%)", "", f"{summary.gross_margin_percent:.2f}"])
        writer.writerow(["Less: Store Operating Expenses (OPEX)", f"-{summary.operating_expenses:.2f}", ""])
        writer.writerow(["Net Operating Profit", f"{summary.net_operating_profit:.2f}", ""])
        writer.writerow(["Net Operating Margin (%)", "", f"{summary.net_operating_margin_percent:.2f}"])
        writer.writerow([])

        # Tax & Tender Reconciliation Block
        writer.writerow(["--- Tax & Tender Reconciliation ---", "", ""])
        writer.writerow(["Gross Output VAT", f"{summary.gross_output_vat:.2f}", ""])
        writer.writerow(["Less: Output VAT Reversals", f"-{summary.vat_reversals:.2f}", ""])
        writer.writerow(["Net Output VAT", f"{summary.net_output_vat:.2f}", ""])
        writer.writerow(["Gross Collections (Total Tendered)", f"{summary.total_collections:.2f}", ""])
        writer.writerow(["Less: Refunds Issued", f"-{summary.refunds_issued:.2f}", ""])
        writer.writerow(["Net Collections", f"{summary.net_collections:.2f}", ""])

        content = output.getvalue()
        if target_path:
            with open(target_path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(content)

        return content

    # ── 2. Product Performance Export ────────────────────────────────

    def export_product_performance_csv(
        self,
        start_date: date,
        end_date: date,
        actor: User,
        limit: Optional[int] = None,
        target_path: Optional[str] = None,
    ) -> str:
        """Export Product Contribution Leaderboard to CSV (UTF-8-SIG)."""
        self._check_export_permission(actor)
        products = self._report_service.get_product_performance(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            actor=actor,
        )

        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        writer.writerow(["Report", "RetailFlow POS - Product Contribution Leaderboard"])
        writer.writerow(["Period Start", start_date.strftime("%Y-%m-%d")])
        writer.writerow(["Period End", end_date.strftime("%Y-%m-%d")])
        writer.writerow(["Generated At", self._get_timestamp_header()])
        writer.writerow([
            "Note",
            "Direct Contribution Margin reflects pre-order-discount product performance (Net Gross Revenue - Net Historical COGS).",
        ])
        writer.writerow([])

        writer.writerow([
            "Rank",
            "SKU",
            "Product Name",
            "Units Sold (Gross)",
            "Units Returned",
            "Net Units",
            "Gross Revenue (PHP)",
            "Revenue Reversals (PHP)",
            "Net Gross Revenue (PHP)",
            "Net COGS (PHP)",
            "Direct Contribution Margin (PHP)",
        ])

        for idx, p in enumerate(products, 1):
            writer.writerow([
                idx,
                sanitize_csv_text(p.sku),
                sanitize_csv_text(p.product_name),
                p.quantity_sold,
                p.quantity_returned,
                p.net_units_sold,
                f"{p.gross_revenue:.2f}",
                f"{p.gross_revenue_reversal:.2f}",
                f"{p.net_gross_revenue:.2f}",
                f"{p.net_historical_cogs:.2f}",
                f"{p.direct_margin:.2f}",
            ])

        content = output.getvalue()
        if target_path:
            with open(target_path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(content)

        return content

    # ── 3. Cashier Performance Export ────────────────────────────────

    def export_cashier_performance_csv(
        self,
        start_date: date,
        end_date: date,
        actor: User,
        target_path: Optional[str] = None,
    ) -> str:
        """Export Cashier Operational Performance to CSV (UTF-8-SIG)."""
        self._check_export_permission(actor)
        cashiers = self._report_service.get_cashier_performance(start_date, end_date, actor)

        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        writer.writerow(["Report", "RetailFlow POS - Cashier Operational Performance"])
        writer.writerow(["Period Start", start_date.strftime("%Y-%m-%d")])
        writer.writerow(["Period End", end_date.strftime("%Y-%m-%d")])
        writer.writerow(["Generated At", self._get_timestamp_header()])
        writer.writerow([
            "Note",
            "Net Sales represents recognized store revenue net of return reversals. Collections represents net tender.",
        ])
        writer.writerow([])

        writer.writerow([
            "Cashier",
            "Completed Orders",
            "Gross Units",
            "Units Returned",
            "Net Units",
            "Net Sales (PHP)",
            "Gross Collections (PHP)",
            "Refunds Issued (PHP)",
            "Net Collections (PHP)",
            "Net AOV (PHP)",
            "Discounts Handled (PHP)",
        ])

        for c in cashiers:
            writer.writerow([
                sanitize_csv_text(c.cashier_name),
                c.transaction_count,
                c.units_sold,
                c.units_returned,
                c.net_units,
                f"{c.net_sales:.2f}",
                f"{c.collections:.2f}",
                f"{c.refunds_issued:.2f}",
                f"{c.net_collections:.2f}",
                f"{c.average_order_value:.2f}",
                f"{c.discounts:.2f}",
            ])

        content = output.getvalue()
        if target_path:
            with open(target_path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(content)

        return content

    # ── 4. Store OPEX Breakdown Export ───────────────────────────────

    def export_opex_breakdown_csv(
        self,
        start_date: date,
        end_date: date,
        actor: User,
        target_path: Optional[str] = None,
    ) -> str:
        """Export Store Operating Expenses Breakdown to CSV (UTF-8-SIG)."""
        self._check_export_permission(actor)
        breakdown = self._report_service.get_expense_category_breakdown(start_date, end_date, actor)

        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        writer.writerow(["Report", "RetailFlow POS - Store Operating Expenses Breakdown"])
        writer.writerow(["Period Start", start_date.strftime("%Y-%m-%d")])
        writer.writerow(["Period End", end_date.strftime("%Y-%m-%d")])
        writer.writerow(["Generated At", self._get_timestamp_header()])
        writer.writerow([])

        writer.writerow(["Expense Category", "Total Amount (PHP)", "Allocation (%)"])

        for item in breakdown:
            writer.writerow([
                sanitize_csv_text(item.category_display),
                f"{item.amount:.2f}",
                f"{item.percentage:.2f}",
            ])

        total_opex = sum((item.amount for item in breakdown), Decimal("0.00"))
        writer.writerow(["TOTAL OPERATING EXPENSES", f"{total_opex:.2f}", "100.00"])

        content = output.getvalue()
        if target_path:
            with open(target_path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(content)

        return content

    # ── 5. Payment Methods & Refunds Export ───────────────────────────

    def export_payment_methods_csv(
        self,
        start_date: date,
        end_date: date,
        actor: User,
        target_path: Optional[str] = None,
    ) -> str:
        """Export Collections by Payment Method and Refunds by Method to CSV (UTF-8-SIG)."""
        self._check_export_permission(actor)
        pm_breakdown = self._report_service.get_payment_method_breakdown(start_date, end_date, actor)
        ref_breakdown = self._report_service.get_refund_method_breakdown(start_date, end_date, actor)

        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        writer.writerow(["Report", "RetailFlow POS - Collections & Refunds by Channel"])
        writer.writerow(["Period Start", start_date.strftime("%Y-%m-%d")])
        writer.writerow(["Period End", end_date.strftime("%Y-%m-%d")])
        writer.writerow(["Generated At", self._get_timestamp_header()])
        writer.writerow([])

        # Section 1: Gross Collections by Payment Method
        writer.writerow(["--- Gross Collections by Payment Method ---", "", "", ""])
        writer.writerow(["Payment Method", "Transactions", "Total Collected (PHP)", "Share (%)"])
        for item in pm_breakdown:
            writer.writerow([
                sanitize_csv_text(item.payment_method_display),
                item.transaction_count,
                f"{item.total_amount:.2f}",
                f"{item.percentage:.2f}",
            ])

        total_txns = sum((item.transaction_count for item in pm_breakdown), 0)
        total_coll = sum((item.total_amount for item in pm_breakdown), Decimal("0.00"))
        writer.writerow(["TOTAL COLLECTIONS", total_txns, f"{total_coll:.2f}", "100.00"])

        writer.writerow([])

        # Section 2: Refunds Disbursed by Method Channel
        writer.writerow(["--- Customer Refunds Disbursed by Method ---", "", "", ""])
        writer.writerow(["Refund Channel", "Return Vouchers", "Total Refunded (PHP)", "Share (%)"])
        for ref in ref_breakdown:
            writer.writerow([
                sanitize_csv_text(ref.refund_method_display),
                ref.return_count,
                f"{ref.total_refund_amount:.2f}",
                f"{ref.percentage:.2f}",
            ])

        if ref_breakdown:
            total_ret_count = sum((r.return_count for r in ref_breakdown), 0)
            total_ref_amt = sum((r.total_refund_amount for r in ref_breakdown), Decimal("0.00"))
            writer.writerow(["TOTAL REFUNDS", total_ret_count, f"{total_ref_amt:.2f}", "100.00"])

        content = output.getvalue()
        if target_path:
            with open(target_path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(content)

        return content

    # ── 6. Inventory Valuation Snapshot Export ────────────────────────

    def export_inventory_valuation_csv(
        self,
        actor: User,
        target_path: Optional[str] = None,
    ) -> str:
        """Export Current Working Capital Inventory Valuation to CSV (UTF-8-SIG)."""
        self._check_export_permission(actor)
        inv = self._report_service.get_inventory_value(actor)

        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        writer.writerow(["Report", "RetailFlow POS - Current Working Capital Inventory Valuation"])
        writer.writerow(["Snapshot Date", datetime.now().strftime("%Y-%m-%d")])
        writer.writerow(["Generated At", self._get_timestamp_header()])
        writer.writerow([
            "Note",
            "Valuation is based on active inventory on hand at current replacement cost and retail selling price.",
        ])
        writer.writerow([])

        writer.writerow(["Valuation Metric", "Value"])
        writer.writerow(["Active Products Monitored", inv.total_products])
        writer.writerow(["Total Units on Hand", inv.total_units_on_hand])
        writer.writerow(["Total Asset Value (Cost Basis PHP)", f"{inv.current_cost_value:.2f}"])
        writer.writerow(["Total Retail Value (Selling Price PHP)", f"{inv.current_retail_value:.2f}"])
        writer.writerow(["Potential Unrealized Margin (PHP)", f"{inv.potential_unrealized_margin:.2f}"])

        content = output.getvalue()
        if target_path:
            with open(target_path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(content)

        return content

    # ── 7. Received Purchasing Intake Export ───────────────────────────

    def export_purchasing_summary_csv(
        self,
        start_date: date,
        end_date: date,
        actor: User,
        target_path: Optional[str] = None,
    ) -> str:
        """Export Received Purchasing Intake Summary to CSV (UTF-8-SIG)."""
        self._check_export_permission(actor)
        po_summary = self._report_service.get_received_purchase_value(start_date, end_date, actor)

        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        writer.writerow(["Report", "RetailFlow POS - Received Purchasing Intake Summary"])
        writer.writerow(["Period Start", po_summary.start_date])
        writer.writerow(["Period End", po_summary.end_date])
        writer.writerow(["Generated At", self._get_timestamp_header()])
        writer.writerow([
            "Note",
            "Inventory procurement is a balance-sheet working capital asset addition, not an operational expense.",
        ])
        writer.writerow([])

        writer.writerow(["Procurement Metric", "Value"])
        writer.writerow(["Received Purchase Orders", po_summary.received_order_count])
        writer.writerow(["Total Inventory Units Received", po_summary.total_units_received])
        writer.writerow(["Total Procurement Intake Value (PHP)", f"{po_summary.received_purchase_value:.2f}"])

        content = output.getvalue()
        if target_path:
            with open(target_path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(content)

        return content
