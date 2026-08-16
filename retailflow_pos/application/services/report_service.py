"""
RetailFlow POS - Financial & Reporting Application Service (Phase 5B Production)
Coordinates Profit & Loss calculations, revenue, returns, Output VAT reversals, COGS adjustments,
daily trend sequences, cashier performance metrics, product sales analytics, and operational inventory valuation.
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

MANILA_TZ = ZoneInfo("Asia/Manila")

from app.constants import EXPENSE_CATEGORY_LABELS, ReturnStatus
from application.dto.report_dto import (
    CashierPerformanceDTO,
    DailyFinancialPointDTO,
    ExpenseCategoryBreakdownDTO,
    FinancialSummaryDTO,
    InventoryValueDTO,
    PaymentMethodSummaryDTO,
    ProductPerformanceDTO,
    PurchaseIntakeSummaryDTO,
    RefundMethodSummaryDTO,
)
from application.services.expense_service import ExpenseService
from domain.exceptions import AuthorizationError, ValidationError
from infrastructure.database.models.auth import User
from infrastructure.database.models.expense import Expense
from infrastructure.database.models.inventory import Inventory
from infrastructure.database.models.product import Product
from infrastructure.database.models.purchasing import PurchaseOrder, PurchaseOrderItem
from infrastructure.database.models.returns import SalesReturn, SalesReturnItem
from infrastructure.database.models.sales import Sale, SaleLineItem

logger = logging.getLogger("retailflow.reports")


class ReportService:
    """Application service for generating business intelligence and financial performance reports."""

    def __init__(self, session: Session, expense_service: Optional[ExpenseService] = None):
        self._session = session
        self._expense_service = expense_service or ExpenseService(session)

    # ─── 1. Executive Financial Summary & P&L ───

    def get_financial_summary(
        self,
        start_date: date,
        end_date: date,
        actor: Optional[User] = None,
    ) -> FinancialSummaryDTO:
        """
        Generate authoritative Profit & Loss statement and financial KPIs for a date range.
        Integrates customer sales return taxable reversals, Output VAT reversals, and COGS adjustments.
        """
        self._require_permission(actor, "view_reports")
        self._validate_date_range(start_date, end_date)

        start_dt, end_exclusive_dt = self._get_datetime_bounds(start_date, end_date)

        # 1. Gross Sales, Discounts, Tax, and Collections
        sales_totals = (
            self._session.query(
                func.coalesce(func.sum(Sale.subtotal), 0).label("gross_sales"),
                func.coalesce(func.sum(Sale.discount_amount), 0).label("discounts"),
                func.coalesce(func.sum(Sale.tax_amount), 0).label("gross_output_vat"),
                func.coalesce(func.sum(Sale.total_amount), 0).label("total_collections"),
            )
            .filter(
                Sale.status == "COMPLETED",
                Sale.created_at >= start_dt,
                Sale.created_at < end_exclusive_dt,
            )
            .first()
        )

        gross_sales = Decimal(str(sales_totals[0])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        discounts = Decimal(str(sales_totals[1])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        gross_output_vat = Decimal(str(sales_totals[2])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_collections = Decimal(str(sales_totals[3])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # 2. Return Reversals (Recognized on SalesReturn.return_date)
        returns_totals = (
            self._session.query(
                func.coalesce(func.sum(SalesReturn.taxable_reversal), 0).label("sales_returns"),
                func.coalesce(func.sum(SalesReturn.tax_reversal), 0).label("vat_reversals"),
                func.coalesce(func.sum(SalesReturn.total_refund_amount), 0).label("refunds_issued"),
                func.coalesce(func.sum(SalesReturn.cogs_reversal_total), 0).label("cogs_reversals"),
            )
            .filter(
                SalesReturn.status == ReturnStatus.COMPLETED.value,
                SalesReturn.return_date.between(start_date, end_date),
            )
            .first()
        )

        sales_returns = Decimal(str(returns_totals[0])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        vat_reversals = Decimal(str(returns_totals[1])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        refunds_issued = Decimal(str(returns_totals[2])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cogs_reversals = Decimal(str(returns_totals[3])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # 3. Net Metrics
        net_sales = (gross_sales - discounts - sales_returns).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        net_output_vat = (gross_output_vat - vat_reversals).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        output_vat = gross_output_vat  # Preserved legacy compatibility alias
        net_collections = (total_collections - refunds_issued).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # 4. Historical COGS & Profitability
        cogs_val = (
            self._session.query(
                func.coalesce(func.sum(SaleLineItem.quantity * SaleLineItem.unit_cost), 0)
            )
            .join(Sale, Sale.id == SaleLineItem.sale_id)
            .filter(
                Sale.status == "COMPLETED",
                Sale.created_at >= start_dt,
                Sale.created_at < end_exclusive_dt,
            )
            .scalar()
        )
        original_cogs = Decimal(str(cogs_val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cogs = (original_cogs - cogs_reversals).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        gross_profit = (net_sales - cogs).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if net_sales > Decimal("0.00"):
            gross_margin_percent = ((gross_profit / net_sales) * Decimal("100.00")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            gross_margin_percent = Decimal("0.00")

        # 5. Operating Expenses & Net Operating Profit
        opex = self._expense_service.get_total_opex(start_date, end_date)
        net_operating_profit = (gross_profit - opex).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if net_sales > Decimal("0.00"):
            net_operating_margin_percent = ((net_operating_profit / net_sales) * Decimal("100.00")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            net_operating_margin_percent = Decimal("0.00")

        return FinancialSummaryDTO(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            gross_sales=gross_sales,
            discounts=discounts,
            sales_returns=sales_returns,
            net_sales=net_sales,
            gross_output_vat=gross_output_vat,
            vat_reversals=vat_reversals,
            net_output_vat=net_output_vat,
            output_vat=output_vat,
            total_collections=total_collections,
            refunds_issued=refunds_issued,
            net_collections=net_collections,
            original_cogs=original_cogs,
            cogs_reversals=cogs_reversals,
            cogs=cogs,
            gross_profit=gross_profit,
            gross_margin_percent=gross_margin_percent,
            operating_expenses=opex,
            net_operating_profit=net_operating_profit,
            net_operating_margin_percent=net_operating_margin_percent,
        )

    # ─── 2. Daily Financial Trend (with Continuous Zero-Filling) ───

    def get_daily_financial_trend(
        self,
        start_date: date,
        end_date: date,
        actor: Optional[User] = None,
    ) -> List[DailyFinancialPointDTO]:
        """
        Generate continuous daily financial time-series net of customer return reversals.
        Guarantees that missing activity dates in the requested range are zero-filled.
        """
        self._require_permission(actor, "view_reports")
        self._validate_date_range(start_date, end_date)

        start_dt, end_exclusive_dt = self._get_datetime_bounds(start_date, end_date)

        # 1. Fetch sales transactions in range
        sales = (
            self._session.query(
                Sale.created_at,
                Sale.subtotal,
                Sale.discount_amount,
            )
            .filter(
                Sale.status == "COMPLETED",
                Sale.created_at >= start_dt,
                Sale.created_at < end_exclusive_dt,
            )
            .all()
        )

        # 2. Fetch line items for COGS in range
        line_items = (
            self._session.query(
                Sale.created_at,
                SaleLineItem.quantity,
                SaleLineItem.unit_cost,
            )
            .join(Sale, Sale.id == SaleLineItem.sale_id)
            .filter(
                Sale.status == "COMPLETED",
                Sale.created_at >= start_dt,
                Sale.created_at < end_exclusive_dt,
            )
            .all()
        )

        # 3. Fetch returns in range (grouped on return_date)
        returns = (
            self._session.query(
                SalesReturn.return_date,
                SalesReturn.taxable_reversal,
                SalesReturn.cogs_reversal_total,
            )
            .filter(
                SalesReturn.status == ReturnStatus.COMPLETED.value,
                SalesReturn.return_date.between(start_date, end_date),
            )
            .all()
        )

        # 4. Fetch paid expenses in range
        expenses = (
            self._session.query(
                Expense.expense_date,
                Expense.amount,
            )
            .filter(
                Expense.status == "paid",
                Expense.expense_date.between(start_date, end_date),
            )
            .all()
        )

        # Initialize full calendar grid
        daily_gross: Dict[str, Decimal] = {}
        daily_disc: Dict[str, Decimal] = {}
        daily_ret_taxable: Dict[str, Decimal] = {}
        daily_orig_cogs: Dict[str, Decimal] = {}
        daily_cogs_rev: Dict[str, Decimal] = {}
        daily_opex: Dict[str, Decimal] = {}

        curr = start_date
        while curr <= end_date:
            d_str = curr.isoformat()
            daily_gross[d_str] = Decimal("0.00")
            daily_disc[d_str] = Decimal("0.00")
            daily_ret_taxable[d_str] = Decimal("0.00")
            daily_orig_cogs[d_str] = Decimal("0.00")
            daily_cogs_rev[d_str] = Decimal("0.00")
            daily_opex[d_str] = Decimal("0.00")
            curr += timedelta(days=1)

        # Populate sales
        for created_at, subtotal, discount in sales:
            if created_at:
                d_str = self._utc_to_manila_date(created_at).isoformat()
                if d_str in daily_gross:
                    daily_gross[d_str] += Decimal(str(subtotal))
                    daily_disc[d_str] += Decimal(str(discount))

        # Populate original COGS
        for created_at, qty, unit_cost in line_items:
            if created_at:
                d_str = self._utc_to_manila_date(created_at).isoformat()
                if d_str in daily_orig_cogs:
                    daily_orig_cogs[d_str] += Decimal(str(qty)) * Decimal(str(unit_cost))

        # Populate returns
        for ret_date, taxable_rev, cogs_rev in returns:
            if ret_date:
                d_str = ret_date.isoformat()
                if d_str in daily_ret_taxable:
                    daily_ret_taxable[d_str] += Decimal(str(taxable_rev))
                    daily_cogs_rev[d_str] += Decimal(str(cogs_rev))

        # Populate OPEX
        for exp_date, amount in expenses:
            if exp_date:
                d_str = exp_date.isoformat()
                if d_str in daily_opex:
                    daily_opex[d_str] += Decimal(str(amount))

        # Assemble final continuous sequence
        points: List[DailyFinancialPointDTO] = []
        curr = start_date
        while curr <= end_date:
            d_str = curr.isoformat()
            gs = daily_gross[d_str].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            ds = daily_disc[d_str].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            sr = daily_ret_taxable[d_str].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            ns = (gs - ds - sr).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            orig_cg = daily_orig_cogs[d_str].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            rev_cg = daily_cogs_rev[d_str].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cg = (orig_cg - rev_cg).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            gp = (ns - cg).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            ox = daily_opex[d_str].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            np = (gp - ox).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            points.append(
                DailyFinancialPointDTO(
                    date=d_str,
                    gross_sales=gs,
                    discounts=ds,
                    sales_returns=sr,
                    net_sales=ns,
                    cogs=cg,
                    gross_profit=gp,
                    opex=ox,
                    net_operating_profit=np,
                )
            )
            curr += timedelta(days=1)

        return points

    # ─── 3. Store Operating Expenses Breakdown ───

    def get_expense_category_breakdown(
        self,
        start_date: date,
        end_date: date,
        actor: Optional[User] = None,
    ) -> List[ExpenseCategoryBreakdownDTO]:
        """
        Store operating expenses breakdown by category with authoritative percentages.
        Excludes VOID records and calculates percentage using pure Decimal math.
        """
        self._require_permission(actor, "view_reports")
        self._validate_date_range(start_date, end_date)

        rows = (
            self._session.query(
                Expense.category,
                func.coalesce(func.sum(Expense.amount), 0).label("cat_total"),
            )
            .filter(
                Expense.status == "paid",
                Expense.expense_date.between(start_date, end_date),
            )
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())
            .all()
        )

        total_opex = sum((Decimal(str(r[1])) for r in rows), Decimal("0.00"))

        results: List[ExpenseCategoryBreakdownDTO] = []
        for cat_code, amt in rows:
            amt_dec = Decimal(str(amt)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            display_name = EXPENSE_CATEGORY_LABELS.get(
                cat_code, cat_code.replace("_", " ").title()
            )
            if total_opex > Decimal("0.00"):
                pct = ((amt_dec / total_opex) * Decimal("100.00")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            else:
                pct = Decimal("0.00")

            results.append(
                ExpenseCategoryBreakdownDTO(
                    category=cat_code,
                    category_display=display_name,
                    amount=amt_dec,
                    percentage=pct,
                )
            )

        return results

    # ─── 4. Collections by Payment Method Channel ───

    def get_payment_method_breakdown(
        self,
        start_date: date,
        end_date: date,
        actor: Optional[User] = None,
    ) -> List[PaymentMethodSummaryDTO]:
        """Distribution of gross collections by incoming payment method channel."""
        self._require_permission(actor, "view_reports")
        self._validate_date_range(start_date, end_date)

        start_dt, end_exclusive_dt = self._get_datetime_bounds(start_date, end_date)

        rows = (
            self._session.query(
                Sale.payment_method,
                func.count(Sale.id).label("txn_count"),
                func.coalesce(func.sum(Sale.total_amount), 0).label("total_amount"),
            )
            .filter(
                Sale.status == "COMPLETED",
                Sale.created_at >= start_dt,
                Sale.created_at < end_exclusive_dt,
            )
            .group_by(Sale.payment_method)
            .order_by(func.sum(Sale.total_amount).desc())
            .all()
        )

        grand_total = sum((Decimal(str(r[2])) for r in rows), Decimal("0.00"))

        results: List[PaymentMethodSummaryDTO] = []
        for pm, count, amt in rows:
            amt_dec = Decimal(str(amt)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if grand_total > Decimal("0.00"):
                pct = ((amt_dec / grand_total) * Decimal("100.00")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            else:
                pct = Decimal("0.00")

            results.append(
                PaymentMethodSummaryDTO(
                    payment_method=pm,
                    payment_method_display=pm.replace("_", " ").title(),
                    transaction_count=int(count),
                    total_amount=amt_dec,
                    percentage=pct,
                )
            )

        return results

    # ─── 5. Refunds Disbursed by Method Channel ───

    def get_refund_method_breakdown(
        self,
        start_date: date,
        end_date: date,
        actor: Optional[User] = None,
    ) -> List[RefundMethodSummaryDTO]:
        """Distribution of customer refund disbursements by refund payment method channel."""
        self._require_permission(actor, "view_reports")
        self._validate_date_range(start_date, end_date)

        returns = (
            self._session.query(
                SalesReturn.refund_payment_method,
                SalesReturn.original_payment_method_snapshot,
                SalesReturn.total_refund_amount,
            )
            .filter(
                SalesReturn.status == ReturnStatus.COMPLETED.value,
                SalesReturn.return_date.between(start_date, end_date),
            )
            .all()
        )

        channel_totals: Dict[str, Decimal] = {}
        channel_counts: Dict[str, int] = {}
        grand_total = Decimal("0.00")

        for ref_pm, orig_pm, amt in returns:
            amt_dec = Decimal(str(amt))
            grand_total += amt_dec

            if ref_pm.lower() == "cash":
                channel = "CASH"
            else:
                channel = (orig_pm or "ORIGINAL_METHOD").upper()

            channel_totals[channel] = channel_totals.get(channel, Decimal("0.00")) + amt_dec
            channel_counts[channel] = channel_counts.get(channel, 0) + 1

        results: List[RefundMethodSummaryDTO] = []
        for channel, total_amt in sorted(channel_totals.items(), key=lambda x: x[1], reverse=True):
            amt_dec = total_amt.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if grand_total > Decimal("0.00"):
                pct = ((amt_dec / grand_total) * Decimal("100.00")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            else:
                pct = Decimal("0.00")

            disp_name = f"{channel.title()} Refund"

            results.append(
                RefundMethodSummaryDTO(
                    refund_method=channel.lower(),
                    refund_method_display=disp_name,
                    return_count=channel_counts[channel],
                    total_refund_amount=amt_dec,
                    percentage=pct,
                )
            )

        return results

    # ─── 6. Cashier Performance (Cross-Period Return Attribution) ───

    def get_cashier_performance(
        self,
        start_date: date,
        end_date: date,
        actor: Optional[User] = None,
    ) -> List[CashierPerformanceDTO]:
        """
        Sales and collections performance metrics grouped per original Sale cashier.
        Integrates cross-period return reversals against original cashier sales.
        """
        self._require_permission(actor, "view_reports")
        self._validate_date_range(start_date, end_date)

        start_dt, end_exclusive_dt = self._get_datetime_bounds(start_date, end_date)

        # 1. Sales aggregates per cashier in period
        sales_rows = (
            self._session.query(
                Sale.cashier_id,
                func.count(Sale.id).label("txn_count"),
                func.coalesce(func.sum(Sale.subtotal), 0).label("gross_sales"),
                func.coalesce(func.sum(Sale.discount_amount), 0).label("discounts"),
                func.coalesce(func.sum(Sale.total_amount), 0).label("collections"),
            )
            .filter(
                Sale.status == "COMPLETED",
                Sale.created_at >= start_dt,
                Sale.created_at < end_exclusive_dt,
            )
            .group_by(Sale.cashier_id)
            .all()
        )
        sales_data = {
            r[0]: {
                "txn_count": int(r[1]),
                "gross_sales": Decimal(str(r[2])),
                "discounts": Decimal(str(r[3])),
                "collections": Decimal(str(r[4])),
            }
            for r in sales_rows
        }

        # 2. Units sold per cashier in period
        units_rows = (
            self._session.query(
                Sale.cashier_id,
                func.coalesce(func.sum(SaleLineItem.quantity), 0),
            )
            .join(Sale, Sale.id == SaleLineItem.sale_id)
            .filter(
                Sale.status == "COMPLETED",
                Sale.created_at >= start_dt,
                Sale.created_at < end_exclusive_dt,
            )
            .group_by(Sale.cashier_id)
            .all()
        )
        units_map = {r[0]: int(r[1]) for r in units_rows}

        # 3. Returns attributable to original Sale cashier recognized in period
        returns_rows = (
            self._session.query(
                Sale.cashier_id,
                func.coalesce(func.sum(SalesReturn.taxable_reversal), 0).label("sales_returns"),
                func.coalesce(func.sum(SalesReturn.total_refund_amount), 0).label("refunds_issued"),
            )
            .select_from(SalesReturn)
            .join(Sale, Sale.id == SalesReturn.sale_id)
            .filter(
                SalesReturn.status == ReturnStatus.COMPLETED.value,
                SalesReturn.return_date.between(start_date, end_date),
            )
            .group_by(Sale.cashier_id)
            .all()
        )
        returns_data = {
            r[0]: {
                "sales_returns": Decimal(str(r[1])),
                "refunds_issued": Decimal(str(r[2])),
            }
            for r in returns_rows
        }

        # 4. Units returned attributable to original Sale cashier recognized in period
        ret_units_rows = (
            self._session.query(
                Sale.cashier_id,
                func.coalesce(func.sum(SalesReturnItem.quantity), 0),
            )
            .select_from(SalesReturn)
            .join(Sale, Sale.id == SalesReturn.sale_id)
            .join(SalesReturnItem, SalesReturnItem.sales_return_id == SalesReturn.id)
            .filter(
                SalesReturn.status == ReturnStatus.COMPLETED.value,
                SalesReturn.return_date.between(start_date, end_date),
            )
            .group_by(Sale.cashier_id)
            .all()
        )
        ret_units_map = {r[0]: int(r[1]) for r in ret_units_rows}

        # 5. Union of all relevant original cashier IDs
        all_cashier_ids: Set[Optional[int]] = set(sales_data.keys()) | set(returns_data.keys())

        results: List[CashierPerformanceDTO] = []
        for cashier_id in all_cashier_ids:
            s_info = sales_data.get(cashier_id, {"txn_count": 0, "gross_sales": Decimal("0.00"), "discounts": Decimal("0.00"), "collections": Decimal("0.00")})
            r_info = returns_data.get(cashier_id, {"sales_returns": Decimal("0.00"), "refunds_issued": Decimal("0.00")})

            txn_count = s_info["txn_count"]
            gross_sales = s_info["gross_sales"]
            discounts = s_info["discounts"]
            sales_returns = r_info["sales_returns"]

            net_sales = (gross_sales - discounts - sales_returns).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            collections = s_info["collections"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            refunds_issued = r_info["refunds_issued"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            net_collections = (collections - refunds_issued).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            units_sold = units_map.get(cashier_id, 0)
            units_returned = ret_units_map.get(cashier_id, 0)
            net_units = units_sold - units_returned

            if txn_count > 0:
                aov = (net_sales / Decimal(txn_count)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                aov = Decimal("0.00")

            if cashier_id is not None:
                user = self._session.get(User, cashier_id)
                name = user.full_name or user.username if user else f"User #{cashier_id}"
            else:
                name = "Unassigned / System"

            results.append(
                CashierPerformanceDTO(
                    cashier_id=cashier_id,
                    cashier_name=name,
                    transaction_count=txn_count,
                    net_sales=net_sales,
                    collections=collections,
                    refunds_issued=refunds_issued,
                    net_collections=net_collections,
                    average_order_value=aov,
                    discounts=discounts.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                    units_sold=units_sold,
                    units_returned=units_returned,
                    net_units=net_units,
                )
            )

        # Sort descending by Net Sales
        results.sort(key=lambda c: c.net_sales, reverse=True)
        return results

    # ─── 7. Product Sales Performance (Cross-Period Return Union) ───

    def get_product_performance(
        self,
        start_date: date,
        end_date: date,
        limit: Optional[int] = None,
        actor: Optional[User] = None,
    ) -> List[ProductPerformanceDTO]:
        """
        Sales volume and direct product gross contribution leaderboard.
        Integrates cross-period return reversals and outputs net merchandise contribution.
        """
        self._require_permission(actor, "view_reports")
        self._validate_date_range(start_date, end_date)

        start_dt, end_exclusive_dt = self._get_datetime_bounds(start_date, end_date)

        # 1. Sales query grouped by product
        sales_rows = (
            self._session.query(
                SaleLineItem.product_id,
                Product.sku,
                SaleLineItem.product_name,
                func.sum(SaleLineItem.quantity).label("quantity_sold"),
                func.sum(SaleLineItem.subtotal).label("gross_revenue"),
                func.sum(SaleLineItem.quantity * SaleLineItem.unit_cost).label("historical_cogs"),
            )
            .join(Sale, Sale.id == SaleLineItem.sale_id)
            .outerjoin(Product, Product.id == SaleLineItem.product_id)
            .filter(
                Sale.status == "COMPLETED",
                Sale.created_at >= start_dt,
                Sale.created_at < end_exclusive_dt,
            )
            .group_by(SaleLineItem.product_id, Product.sku, SaleLineItem.product_name)
            .all()
        )

        sales_map = {
            r[0]: {
                "sku": r[1],
                "name": r[2],
                "qty_sold": int(r[3] or 0),
                "gross_rev": Decimal(str(r[4] or 0)),
                "hist_cogs": Decimal(str(r[5] or 0)),
            }
            for r in sales_rows
        }

        # 2. Returns query grouped by product
        returns_rows = (
            self._session.query(
                SalesReturnItem.product_id,
                Product.sku,
                SalesReturnItem.product_name,
                func.sum(SalesReturnItem.quantity).label("quantity_returned"),
                func.sum(SalesReturnItem.gross_amount_reversal).label("gross_rev_reversal"),
                func.sum(SalesReturnItem.cogs_reversal).label("cogs_reversals"),
            )
            .join(SalesReturn, SalesReturn.id == SalesReturnItem.sales_return_id)
            .outerjoin(Product, Product.id == SalesReturnItem.product_id)
            .filter(
                SalesReturn.status == ReturnStatus.COMPLETED.value,
                SalesReturn.return_date.between(start_date, end_date),
            )
            .group_by(SalesReturnItem.product_id, Product.sku, SalesReturnItem.product_name)
            .all()
        )

        returns_map = {
            r[0]: {
                "sku": r[1],
                "name": r[2],
                "qty_ret": int(r[3] or 0),
                "rev_rev": Decimal(str(r[4] or 0)),
                "cogs_rev": Decimal(str(r[5] or 0)),
            }
            for r in returns_rows
        }

        # 3. Union of all active product IDs in date range
        all_pids: Set[int] = set(sales_map.keys()) | set(returns_map.keys())

        results: List[ProductPerformanceDTO] = []
        for pid in all_pids:
            s = sales_map.get(pid, {"sku": None, "name": None, "qty_sold": 0, "gross_rev": Decimal("0.00"), "hist_cogs": Decimal("0.00")})
            r = returns_map.get(pid, {"sku": None, "name": None, "qty_ret": 0, "rev_rev": Decimal("0.00"), "cogs_rev": Decimal("0.00")})

            sku = s["sku"] or r["sku"] or f"PRD-{pid:04d}"
            name = s["name"] or r["name"] or f"Product #{pid}"

            qty_sold = s["qty_sold"]
            qty_ret = r["qty_ret"]
            net_units = qty_sold - qty_ret

            gross_rev = s["gross_rev"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            rev_reversal = r["rev_rev"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            net_gross_rev = (gross_rev - rev_reversal).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            hist_cogs = s["hist_cogs"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cogs_reversal = r["cogs_rev"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            net_hist_cogs = (hist_cogs - cogs_reversal).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            direct_margin = (net_gross_rev - net_hist_cogs).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            results.append(
                ProductPerformanceDTO(
                    product_id=int(pid),
                    sku=sku,
                    product_name=name,
                    quantity_sold=qty_sold,
                    quantity_returned=qty_ret,
                    net_units_sold=net_units,
                    gross_revenue=gross_rev,
                    gross_revenue_reversal=rev_reversal,
                    net_gross_revenue=net_gross_rev,
                    historical_cogs=hist_cogs,
                    cogs_reversals=cogs_reversal,
                    net_historical_cogs=net_hist_cogs,
                    direct_margin=direct_margin,
                )
            )

        # 4. Deterministic Sort: Net Gross Revenue DESC, then product_id ASC
        results.sort(key=lambda p: (p.net_gross_revenue, -p.product_id), reverse=True)

        if limit is not None and limit > 0:
            results = results[:limit]

        return results

    # ─── 8. Inventory Valuation (Operational Replacement Cost Basis) ───

    def get_inventory_value(self, actor: Optional[User] = None) -> InventoryValueDTO:
        """
        Compute current working capital inventory asset value at replacement cost and retail value.
        Note: Uses current standard cost_price basis across active stock on hand.
        """
        self._require_permission(actor, "view_reports")

        rows = (
            self._session.query(
                Product.id,
                func.coalesce(Inventory.quantity_on_hand, 0),
                Product.cost_price,
                Product.selling_price,
            )
            .outerjoin(Inventory, Inventory.product_id == Product.id)
            .filter(Product.status == "active")
            .all()
        )

        total_products = len(rows)
        total_units = sum(int(r[1]) for r in rows)
        total_cost = sum((Decimal(str(r[1])) * Decimal(str(r[2])) for r in rows), Decimal("0.00")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total_retail = sum((Decimal(str(r[1])) * Decimal(str(r[3])) for r in rows), Decimal("0.00")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        unrealized_margin = (total_retail - total_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return InventoryValueDTO(
            total_products=total_products,
            total_units_on_hand=total_units,
            current_cost_value=total_cost,
            current_retail_value=total_retail,
            potential_unrealized_margin=unrealized_margin,
        )

    # ─── 9. Received Purchasing Summary (Asset Acquisition) ───

    def get_received_purchase_value(
        self,
        start_date: date,
        end_date: date,
        actor: Optional[User] = None,
    ) -> PurchaseIntakeSummaryDTO:
        """
        Procurement summary of received purchase orders within a date range.
        Note: Inventory purchases are Balance Sheet asset additions, not P&L operating expenses.
        """
        self._require_permission(actor, "view_reports")
        self._validate_date_range(start_date, end_date)

        start_dt, end_exclusive_dt = self._get_datetime_bounds(start_date, end_date)

        pos = (
            self._session.query(PurchaseOrder)
            .filter(
                PurchaseOrder.status == "RECEIVED",
                PurchaseOrder.received_at >= start_dt,
                PurchaseOrder.received_at < end_exclusive_dt,
            )
            .all()
        )

        total_val = sum((po.total_amount for po in pos), Decimal("0.00")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total_units = sum(
            sum(item.quantity_received for item in po.items) for po in pos
        )

        return PurchaseIntakeSummaryDTO(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            received_order_count=len(pos),
            received_purchase_value=total_val,
            total_units_received=total_units,
        )

    # ─── Canonical Helper Methods ───

    def _get_datetime_bounds(self, start_date: date, end_date: date) -> Tuple[datetime, datetime]:
        """
        Convert inclusive store-local Asia/Manila calendar date range [start_date, end_date] to
        canonical UTC half-open datetime interval [start_utc_naive, end_exclusive_utc_naive)
        matching the database timestamp storage convention.
        """
        start_manila = datetime.combine(start_date, time.min, tzinfo=MANILA_TZ)
        start_utc_naive = start_manila.astimezone(timezone.utc).replace(tzinfo=None)

        end_exclusive_manila = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=MANILA_TZ)
        end_exclusive_utc_naive = end_exclusive_manila.astimezone(timezone.utc).replace(tzinfo=None)

        return start_utc_naive, end_exclusive_utc_naive

    def _utc_to_manila_date(self, dt: datetime) -> date:
        """Convert naive UTC timestamp from database to store-local Asia/Manila calendar date."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(MANILA_TZ).date()

    def _validate_date_range(self, start_date: date, end_date: date) -> None:
        """Validate date ordering."""
        if start_date > end_date:
            raise ValidationError(
                f"Start date ({start_date}) cannot be after end date ({end_date})."
            )

    def _require_permission(self, actor: Optional[User], permission: str) -> None:
        """Enforce role/permission authorization checks."""
        if actor is None:
            return  # Allow internal system calls if actor is omitted
        if actor.is_admin():
            return
        if not actor.has_permission(permission):
            raise AuthorizationError(f"You do not have permission: '{permission}'.")
