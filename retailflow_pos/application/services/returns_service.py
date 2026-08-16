"""
RetailFlow POS - Returns & Refunds Application Service (Phase 4 Production)
Coordinates customer return validations, approval enforcement, integer centavo allocation,
atomic inventory restoration, non-mutating preview calculation, financial snapshots, audit logging,
idempotency conflict detection, cross-dialect concurrency protection, and derived return metrics.
"""

import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants import (
    DerivedReturnState,
    PaymentMethod,
    RefundMethod,
    ReturnDisposition,
    ReturnReason,
    ReturnStatus,
)
from application.dto.returns_dto import (
    ProcessReturnRequestDTO,
    ReturnableLineItemDTO,
    ReturnItemPreviewDTO,
    ReturnPreviewDTO,
    SaleReturnSummaryDTO,
    SalesReturnDTO,
    SalesReturnItemDTO,
)
from domain.exceptions import AuthorizationError, RetailFlowError, ValidationError
from domain.rules.return_allocation import (
    allocate_sale_discounts,
    allocate_sale_vat,
    calculate_line_return_financials,
)
from infrastructure.database.models.auth import User
from infrastructure.database.models.inventory import Inventory
from infrastructure.database.models.returns import SalesReturn, SalesReturnItem
from infrastructure.database.models.sales import Payment, Sale, SaleLineItem
from infrastructure.database.repositories.auth import AuditLogRepository

logger = logging.getLogger("retailflow.returns")

MANILA_TZ = ZoneInfo("Asia/Manila")

SUPPORTED_ELECTRONIC_METHODS: Set[str] = {
    pm.value.upper()
    for pm in PaymentMethod
    if pm not in (PaymentMethod.CASH, PaymentMethod.SPLIT)
}
SUPPORTED_ELECTRONIC_METHODS.add("CARD")


class ReturnsService:
    """Application service for managing customer returns, inventory restoration, and refund vouchers."""

    def __init__(self, session: Session):
        self._session = session
        self._audit_repo = AuditLogRepository(session)

    # ─── Preview / Read Calculations ───

    def preview_return(
        self, request: ProcessReturnRequestDTO, actor: Optional[User] = None
    ) -> ReturnPreviewDTO:
        """
        Non-mutating preview of return financial calculations, discount/tax reversals, and refund totals.
        Requires 'view_sales' or 'return_sales' permission.
        Does NOT perform any database mutations, stock updates, or audit logs.
        """
        if actor:
            if not actor.is_active:
                raise AuthorizationError(f"User account '{actor.username}' is inactive.")
            if not (actor.is_admin() or actor.has_permission("view_sales") or actor.has_permission("return_sales")):
                raise AuthorizationError("You do not have permission to preview returns.")

        sale = self._session.get(Sale, request.sale_id)
        if not sale:
            raise ValidationError(f"Sale with ID {request.sale_id} not found.")

        if sale.status != "COMPLETED":
            raise ValidationError(
                f"Sale {sale.transaction_number} has status '{sale.status}'. Only COMPLETED sales can be returned."
            )

        breakdowns, totals = self._calculate_return_breakdowns(sale, request.items)

        item_previews = [
            ReturnItemPreviewDTO(
                sale_line_item_id=b["line"].id,
                product_id=b["line"].product_id,
                product_name=b["line"].product_name,
                quantity=b["req_item"].quantity,
                unit_price=b["line"].unit_price,
                unit_cost=b["line"].unit_cost,
                gross_amount_reversal=b["fin"].gross_amount_reversal,
                discount_reversal=b["fin"].discount_reversal,
                taxable_reversal=b["fin"].taxable_reversal,
                tax_reversal=b["fin"].tax_reversal,
                total_refund_amount=b["fin"].total_refund_amount,
                cogs_reversal=b["fin"].cogs_reversal,
                writeoff_cost=b["fin"].writeoff_cost,
                disposition=b["req_item"].disposition,
            )
            for b in breakdowns
        ]

        return ReturnPreviewDTO(
            sale_id=sale.id,
            subtotal_returned=totals["subtotal_returned"],
            discount_reversal=totals["discount_reversal"],
            taxable_reversal=totals["taxable_reversal"],
            tax_reversal=totals["tax_reversal"],
            total_refund_amount=totals["total_refund_amount"],
            cogs_reversal_total=totals["cogs_reversal_total"],
            writeoff_cost_total=totals["writeoff_cost_total"],
            items=item_previews,
        )

    # ─── Command / Mutation Operations ───

    def process_return(
        self,
        request: ProcessReturnRequestDTO,
        actor: Optional[User] = None,
        approver: Optional[User] = None,
        idempotency_key: str = "",
    ) -> SalesReturnDTO:
        """
        Process an atomic customer return voucher with deterministic approval, centavo allocation,
        stock adjustment, idempotency conflict verification, and audit logging.

        Args:
            request: ProcessReturnRequestDTO command payload.
            actor: Active terminal operator processing the return (must have 'return_sales').
            approver: Authorizing Manager/Admin (must have 'refund_approve'). Defaults to actor if self-approved.
            idempotency_key: Mandatory unique client operation key (<= 64 chars) for double-submit protection.

        Returns:
            SalesReturnDTO representing the finalized, immutable return voucher.
        """
        # 1. Mandatory Idempotency Key Validation
        if not idempotency_key or not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValidationError("A valid, non-blank idempotency_key is required.")

        clean_idempotency_key = idempotency_key.strip()
        if len(clean_idempotency_key) > 64:
            raise ValidationError("idempotency_key must not exceed 64 characters.")

        # 2. Authorization & Active Account Checks (Executed before returning existing idempotent voucher)
        self._require_permission(actor, "return_sales")
        final_approver = self._resolve_approver(actor=actor, approver=approver)

        # 3. Idempotency Check & Conflict Verification
        existing = (
            self._session.query(SalesReturn)
            .filter(SalesReturn.idempotency_key == clean_idempotency_key)
            .first()
        )
        if existing:
            self._verify_idempotency_semantics(
                existing=existing,
                request=request,
                actor=actor,
                approver=final_approver,
            )
            logger.info(
                f"Idempotent return request matched existing voucher {existing.return_number} (key: {clean_idempotency_key})"
            )
            return self._to_dto(existing)

        # 4. Dialect-Aware Concurrency Locking & Load Sale
        sale = self._lock_and_load_sale(request.sale_id)
        if not sale:
            raise ValidationError(f"Sale with ID {request.sale_id} not found.")

        if sale.status != "COMPLETED":
            raise ValidationError(
                f"Sale {sale.transaction_number} has status '{sale.status}'. Only COMPLETED sales can be returned."
            )

        # 5. Validate Metadata & Refund Tender
        reason_code = request.reason_code.strip() if request.reason_code else ReturnReason.OTHER.value
        valid_reasons = [r.value for r in ReturnReason]
        if reason_code not in valid_reasons:
            raise ValidationError(f"Invalid return reason code: '{reason_code}'.")

        reason_notes = request.reason_notes.strip() if request.reason_notes else None
        if reason_code == ReturnReason.OTHER.value and not reason_notes:
            raise ValidationError("Reason notes are required when reason code is 'other'.")

        refund_method = request.refund_payment_method.strip() if request.refund_payment_method else RefundMethod.CASH.value
        if refund_method not in [RefundMethod.CASH.value, RefundMethod.ORIGINAL_METHOD.value]:
            raise ValidationError(f"Invalid refund payment method: '{refund_method}'.")

        if not sale.payments:
            raise ValidationError(f"Sale {sale.transaction_number} has no payment records.")

        orig_pm = sale.payments[0].payment_method.upper()
        if refund_method == RefundMethod.ORIGINAL_METHOD.value:
            if orig_pm in ["CASH", PaymentMethod.CASH.value.upper()]:
                raise ValidationError("ORIGINAL_METHOD refund is not allowed when original payment was CASH. Use CASH refund.")
            if orig_pm not in SUPPORTED_ELECTRONIC_METHODS:
                raise ValidationError(f"Original payment method '{orig_pm}' is not eligible for electronic ORIGINAL_METHOD refund.")
            if not request.refund_reference or not request.refund_reference.strip():
                raise ValidationError("Refund reference is required for non-cash ORIGINAL_METHOD refunds.")
            refund_reference = request.refund_reference.strip()
        else:
            refund_reference = request.refund_reference.strip() if request.refund_reference else None

        # 6. Authoritative Financial Breakdown Calculation (Shared Pipeline)
        breakdowns, totals = self._calculate_return_breakdowns(sale, request.items)

        # 7. Apply Stock Restorations and Build Return Items
        return_items: List[SalesReturnItem] = []
        today_date = datetime.now(MANILA_TZ).date()

        try:
            for b in breakdowns:
                line = b["line"]
                req_item = b["req_item"]
                fin = b["fin"]

                # Inventory adjustment for RESTOCK
                if req_item.disposition == ReturnDisposition.RESTOCK.value:
                    inv = (
                        self._session.query(Inventory)
                        .filter(Inventory.product_id == line.product_id)
                        .first()
                    )
                    if not inv:
                        raise ValidationError(
                            f"Inventory record for product '{line.product_name}' (ID: {line.product_id}) not found."
                        )
                    inv.quantity_on_hand += req_item.quantity

                ret_item = SalesReturnItem(
                    sale_line_item_id=line.id,
                    product_id=line.product_id,
                    product_name=line.product_name,
                    quantity=req_item.quantity,
                    unit_price_snapshot=line.unit_price,
                    unit_cost_snapshot=line.unit_cost,
                    gross_amount_reversal=fin.gross_amount_reversal,
                    discount_reversal=fin.discount_reversal,
                    taxable_reversal=fin.taxable_reversal,
                    tax_reversal=fin.tax_reversal,
                    total_refund_amount=fin.total_refund_amount,
                    cogs_reversal=fin.cogs_reversal,
                    writeoff_cost=fin.writeoff_cost,
                    disposition=req_item.disposition,
                )
                return_items.append(ret_item)

            # 8. Bounded Collision-Safe Return Number Generation & Insertion
            sales_return = self._create_return_with_collision_retry(
                today_date=today_date,
                sale_id=sale.id,
                cashier_id=actor.id if actor else final_approver.id,
                approved_by_id=final_approver.id,
                reason_code=reason_code,
                reason_notes=reason_notes,
                refund_method=refund_method,
                orig_pm=orig_pm,
                refund_reference=refund_reference,
                clean_idempotency_key=clean_idempotency_key,
                subtotal_returned=totals["subtotal_returned"],
                discount_reversal=totals["discount_reversal"],
                taxable_reversal=totals["taxable_reversal"],
                tax_reversal=totals["tax_reversal"],
                total_refund_amount=totals["total_refund_amount"],
                cogs_reversal_total=totals["cogs_reversal_total"],
                writeoff_cost_total=totals["writeoff_cost_total"],
                return_items=return_items,
            )

            # 9. Audit Logging
            new_val_json = json.dumps({
                "return_number": sales_return.return_number,
                "sale_transaction_number": sale.transaction_number,
                "total_refund": str(totals["total_refund_amount"]),
                "cashier_id": actor.id if actor else final_approver.id,
                "approved_by_id": final_approver.id,
                "reason_code": reason_code,
                "items_count": len(return_items),
                "idempotency_key": clean_idempotency_key,
            })
            self._audit_repo.log_action(
                user_id=actor.id if actor else final_approver.id,
                username=actor.username if actor else final_approver.username,
                action="RETURN_PROCESSED",
                module="sales",
                record_type="sales_return",
                record_id=sales_return.id,
                previous_value=None,
                new_value=new_val_json,
            )

            self._session.commit()
            self._session.refresh(sales_return)
            logger.info(
                f"Processed return {sales_return.return_number} for sale {sale.transaction_number} (Refund: ₱{totals['total_refund_amount']})"
            )
            return self._to_dto(sales_return)

        except Exception as e:
            self._session.rollback()
            raise e

    # ─── Query Operations ───

    def get_returnable_items(
        self, sale_id: int, actor: Optional[User] = None
    ) -> List[ReturnableLineItemDTO]:
        """
        Retrieve all line items for a sale with remaining returnable quantities and ceiling metrics.
        Requires 'view_sales' permission.
        """
        self._require_permission(actor, "view_sales")

        sale = self._session.get(Sale, sale_id)
        if not sale:
            raise ValidationError(f"Sale with ID {sale_id} not found.")

        prev_returned_map = self._get_previously_returned_quantities(sale.id)

        sorted_lines = sorted(sale.items, key=lambda l: l.id)
        lines_subtotals = [(l.id, l.subtotal) for l in sorted_lines]
        discount_ceilings = allocate_sale_discounts(sale.discount_amount, lines_subtotals)

        lines_taxable = [(l.id, l.subtotal - discount_ceilings[l.id]) for l in sorted_lines]
        vat_ceilings = allocate_sale_vat(sale.tax_amount, lines_taxable)

        result: List[ReturnableLineItemDTO] = []
        for line in sorted_lines:
            prev_qty = prev_returned_map.get(line.id, 0)
            rem_qty = max(0, line.quantity - prev_qty)

            result.append(
                ReturnableLineItemDTO(
                    sale_line_item_id=line.id,
                    product_id=line.product_id,
                    product_name=line.product_name,
                    unit_price=line.unit_price,
                    unit_cost=line.unit_cost,
                    original_quantity=line.quantity,
                    previously_returned_quantity=prev_qty,
                    remaining_returnable_quantity=rem_qty,
                    max_discount_allocable=discount_ceilings.get(line.id, Decimal("0.00")),
                    max_tax_allocable=vat_ceilings.get(line.id, Decimal("0.00")),
                )
            )

        return result

    def get_sale_return_summary(
        self, sale_id: int, actor: Optional[User] = None
    ) -> SaleReturnSummaryDTO:
        """
        Derive dynamic return state (NONE, PARTIAL, FULL) and cumulative refund totals for a sale.
        Requires 'view_sales' permission.
        """
        self._require_permission(actor, "view_sales")

        sale = self._session.get(Sale, sale_id)
        if not sale:
            raise ValidationError(f"Sale with ID {sale_id} not found.")

        tot_orig_qty = sum(item.quantity for item in sale.items)

        returns = (
            self._session.query(SalesReturn)
            .filter(SalesReturn.sale_id == sale.id, SalesReturn.status == ReturnStatus.COMPLETED.value)
            .all()
        )

        tot_ret_qty = sum(item.quantity for ret in returns for item in ret.items)
        tot_refunded = sum(ret.total_refund_amount for ret in returns)

        if tot_ret_qty == 0:
            derived_state = DerivedReturnState.NONE.value
        elif tot_ret_qty < tot_orig_qty:
            derived_state = DerivedReturnState.PARTIAL.value
        else:
            derived_state = DerivedReturnState.FULL.value

        return SaleReturnSummaryDTO(
            sale_id=sale.id,
            transaction_number=sale.transaction_number,
            total_original_quantity=tot_orig_qty,
            total_returned_quantity=tot_ret_qty,
            derived_state=derived_state,
            total_refunded_amount=tot_refunded,
            returns_count=len(returns),
        )

    def get_returns_for_sale(
        self, sale_id: int, actor: Optional[User] = None
    ) -> List[SalesReturnDTO]:
        """
        Retrieve all finalized returns associated with a specific sale.
        Requires 'view_sales' permission.
        """
        self._require_permission(actor, "view_sales")

        returns = (
            self._session.query(SalesReturn)
            .filter(SalesReturn.sale_id == sale_id)
            .order_by(SalesReturn.id.asc())
            .all()
        )
        return [self._to_dto(r) for r in returns]

    def get_return_by_number(
        self, return_number: str, actor: Optional[User] = None
    ) -> Optional[SalesReturnDTO]:
        """
        Retrieve a finalized return voucher by its unique return number.
        Requires 'view_sales' permission.
        """
        self._require_permission(actor, "view_sales")

        ret = (
            self._session.query(SalesReturn)
            .filter(SalesReturn.return_number == return_number)
            .first()
        )
        return self._to_dto(ret) if ret else None

    # ─── Shared Calculation & Validation Pipeline ───

    def _calculate_return_breakdowns(
        self, sale: Sale, request_items: List[Any]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Decimal]]:
        """
        Authoritative calculation of line financial breakdowns and aggregated voucher totals.
        Shared by both preview_return() and process_return().
        """
        if not sale.items:
            raise ValidationError(f"Sale {sale.transaction_number} has no line items.")

        # Financial consistency checks
        if sale.subtotal < sale.discount_amount:
            raise ValidationError("Original sale financial data is inconsistent: discount exceeds subtotal.")

        taxable_original = sale.subtotal - sale.discount_amount
        if taxable_original == Decimal("0.00") and sale.tax_amount != Decimal("0.00"):
            raise ValidationError("Original sale has zero taxable base but non-zero tax recorded.")

        lines_subtotal_sum = sum(item.subtotal for item in sale.items)
        if lines_subtotal_sum != sale.subtotal:
            raise ValidationError(
                f"Original sale line items sum ({lines_subtotal_sum}) does not match sale subtotal ({sale.subtotal})."
            )

        if not request_items:
            raise ValidationError("At least one return item is required.")

        requested_line_ids = [it.sale_line_item_id for it in request_items]
        if len(requested_line_ids) != len(set(requested_line_ids)):
            raise ValidationError("Duplicate line items in return request are not allowed.")

        sale_line_map = {item.id: item for item in sale.items}
        prev_returned_map = self._get_previously_returned_quantities(sale.id)

        # Quantity and disposition validation
        for req_item in request_items:
            line = sale_line_map.get(req_item.sale_line_item_id)
            if not line:
                raise ValidationError(
                    f"Sale line item ID {req_item.sale_line_item_id} does not belong to sale {sale.transaction_number}."
                )

            if req_item.quantity < 1:
                raise ValidationError(f"Return quantity for '{line.product_name}' must be at least 1.")

            prev_qty = prev_returned_map.get(line.id, 0)
            rem_qty = line.quantity - prev_qty
            if rem_qty <= 0:
                raise ValidationError(f"Product '{line.product_name}' has already been fully returned.")

            if req_item.quantity > rem_qty:
                raise ValidationError(
                    f"Requested return quantity ({req_item.quantity}) exceeds remaining returnable quantity ({rem_qty}) for '{line.product_name}'."
                )

            valid_dispositions = [ReturnDisposition.RESTOCK.value, ReturnDisposition.DAMAGED_WRITE_OFF.value]
            if req_item.disposition not in valid_dispositions:
                raise ValidationError(f"Invalid disposition '{req_item.disposition}' for '{line.product_name}'.")

        # Full-sale allocation ceilings
        sorted_lines = sorted(sale.items, key=lambda l: l.id)
        lines_subtotals = [(l.id, l.subtotal) for l in sorted_lines]
        discount_ceilings = allocate_sale_discounts(sale.discount_amount, lines_subtotals)

        lines_taxable = [(l.id, l.subtotal - discount_ceilings[l.id]) for l in sorted_lines]
        vat_ceilings = allocate_sale_vat(sale.tax_amount, lines_taxable)

        breakdowns: List[Dict[str, Any]] = []
        for req_item in request_items:
            line = sale_line_map[req_item.sale_line_item_id]
            prev_qty = prev_returned_map.get(line.id, 0)

            fin = calculate_line_return_financials(
                unit_price=line.unit_price,
                unit_cost=line.unit_cost,
                total_line_qty=line.quantity,
                line_discount_ceiling=discount_ceilings[line.id],
                line_tax_ceiling=vat_ceilings[line.id],
                previously_returned_qty=prev_qty,
                requested_qty=req_item.quantity,
                disposition=req_item.disposition,
            )
            breakdowns.append({
                "line": line,
                "req_item": req_item,
                "fin": fin,
            })

        tot_subtotal_ret = sum(b["fin"].gross_amount_reversal for b in breakdowns)
        tot_discount_rev = sum(b["fin"].discount_reversal for b in breakdowns)
        tot_taxable_rev = sum(b["fin"].taxable_reversal for b in breakdowns)
        tot_tax_rev = sum(b["fin"].tax_reversal for b in breakdowns)
        tot_refund_amount = sum(b["fin"].total_refund_amount for b in breakdowns)
        tot_cogs_rev = sum(b["fin"].cogs_reversal for b in breakdowns)
        tot_writeoff_cost = sum(b["fin"].writeoff_cost for b in breakdowns)

        # Cumulative caps validation
        prev_returns = (
            self._session.query(SalesReturn)
            .filter(SalesReturn.sale_id == sale.id, SalesReturn.status == ReturnStatus.COMPLETED.value)
            .all()
        )
        cum_discount = sum(r.discount_reversal for r in prev_returns) + tot_discount_rev
        cum_tax = sum(r.tax_reversal for r in prev_returns) + tot_tax_rev
        cum_refund = sum(r.total_refund_amount for r in prev_returns) + tot_refund_amount

        if cum_discount > sale.discount_amount:
            raise ValidationError("Cumulative discount reversal exceeds original sale discount amount.")
        if cum_tax > sale.tax_amount:
            raise ValidationError("Cumulative tax reversal exceeds original sale tax amount.")
        if cum_refund > sale.total_amount:
            raise ValidationError("Cumulative refund amount exceeds original sale total amount.")

        totals = {
            "subtotal_returned": tot_subtotal_ret,
            "discount_reversal": tot_discount_rev,
            "taxable_reversal": tot_taxable_rev,
            "tax_reversal": tot_tax_rev,
            "total_refund_amount": tot_refund_amount,
            "cogs_reversal_total": tot_cogs_rev,
            "writeoff_cost_total": tot_writeoff_cost,
        }

        return breakdowns, totals

    # ─── Internal Helper Methods ───

    def _lock_and_load_sale(self, sale_id: int) -> Optional[Sale]:
        """
        Cross-dialect concurrency locking.
        - SQLite: Starts immediate transaction to serialize competing updates.
        - PostgreSQL / others: Uses SELECT ... FOR UPDATE on Sale and its line items.
        """
        dialect_name = self._session.bind.dialect.name if self._session.bind else "sqlite"
        if dialect_name == "sqlite":
            try:
                self._session.execute(text("BEGIN IMMEDIATE"))
            except Exception:
                pass
            return self._session.get(Sale, sale_id)

        sale = (
            self._session.query(Sale)
            .filter(Sale.id == sale_id)
            .with_for_update()
            .first()
        )
        if sale:
            self._session.query(SaleLineItem).filter(SaleLineItem.sale_id == sale.id).with_for_update().all()
        return sale

    def _verify_idempotency_semantics(
        self,
        existing: SalesReturn,
        request: ProcessReturnRequestDTO,
        actor: Optional[User],
        approver: Optional[User] = None,
    ) -> None:
        """
        Ensure the incoming retry request has identical semantics to the existing return.
        Raises ValidationError if request parameters conflict.
        """
        if existing.sale_id != request.sale_id:
            raise ValidationError(
                f"Idempotency conflict: key '{existing.idempotency_key}' was previously used for Sale ID {existing.sale_id}, not {request.sale_id}."
            )

        if actor and existing.cashier_id != actor.id:
            raise ValidationError(
                f"Idempotency conflict: key '{existing.idempotency_key}' was initiated by cashier ID {existing.cashier_id}, not {actor.id}."
            )

        if approver and existing.approved_by_id != approver.id:
            raise ValidationError(
                f"Idempotency conflict: key '{existing.idempotency_key}' was approved by user ID {existing.approved_by_id}, not {approver.id}."
            )

        expected_reason = request.reason_code if request.reason_code else ReturnReason.OTHER.value
        if existing.reason_code != expected_reason:
            raise ValidationError(
                f"Idempotency conflict: key '{existing.idempotency_key}' was previously used with reason '{existing.reason_code}', not '{expected_reason}'."
            )

        expected_notes = (request.reason_notes or "").strip() or None
        existing_notes = (existing.reason_notes or "").strip() or None
        if existing_notes != expected_notes:
            raise ValidationError(
                f"Idempotency conflict: reason notes changed for key '{existing.idempotency_key}'."
            )

        expected_method = request.refund_payment_method if request.refund_payment_method else RefundMethod.CASH.value
        if existing.refund_payment_method != expected_method:
            raise ValidationError(
                f"Idempotency conflict: key '{existing.idempotency_key}' was previously used with refund method '{existing.refund_payment_method}', not '{expected_method}'."
            )

        expected_ref = (request.refund_reference or "").strip() or None
        existing_ref = (existing.refund_reference or "").strip() or None
        if existing_ref != expected_ref:
            raise ValidationError(
                f"Idempotency conflict: refund reference changed for key '{existing.idempotency_key}'."
            )

        existing_items_map = {item.sale_line_item_id: item for item in existing.items}
        if len(existing_items_map) != len(request.items):
            raise ValidationError(
                f"Idempotency conflict: key '{existing.idempotency_key}' had {len(existing_items_map)} line items, but request contains {len(request.items)}."
            )

        for req_item in request.items:
            ex_item = existing_items_map.get(req_item.sale_line_item_id)
            if not ex_item:
                raise ValidationError(
                    f"Idempotency conflict: line item {req_item.sale_line_item_id} was not part of the original return under key '{existing.idempotency_key}'."
                )
            if ex_item.quantity != req_item.quantity:
                raise ValidationError(
                    f"Idempotency conflict: quantity for line item {req_item.sale_line_item_id} changed from {ex_item.quantity} to {req_item.quantity}."
                )
            if ex_item.disposition != req_item.disposition:
                raise ValidationError(
                    f"Idempotency conflict: disposition for line item {req_item.sale_line_item_id} changed from '{ex_item.disposition}' to '{req_item.disposition}'."
                )

    def _create_return_with_collision_retry(
        self,
        today_date: date,
        sale_id: int,
        cashier_id: int,
        approved_by_id: int,
        reason_code: str,
        reason_notes: Optional[str],
        refund_method: str,
        orig_pm: str,
        refund_reference: Optional[str],
        clean_idempotency_key: str,
        subtotal_returned: Decimal,
        discount_reversal: Decimal,
        taxable_reversal: Decimal,
        tax_reversal: Decimal,
        total_refund_amount: Decimal,
        cogs_reversal_total: Decimal,
        writeoff_cost_total: Decimal,
        return_items: List[SalesReturnItem],
        max_retries: int = 5,
    ) -> SalesReturn:
        """Create and flush SalesReturn with bounded sequence collision retries."""
        for attempt in range(max_retries):
            return_number = self._generate_return_number(today_date, sequence_offset=attempt)
            sales_return = SalesReturn(
                return_number=return_number,
                sale_id=sale_id,
                cashier_id=cashier_id,
                approved_by_id=approved_by_id,
                return_date=today_date,
                status=ReturnStatus.COMPLETED.value,
                reason_code=reason_code,
                reason_notes=reason_notes,
                refund_payment_method=refund_method,
                original_payment_method_snapshot=orig_pm,
                refund_reference=refund_reference,
                idempotency_key=clean_idempotency_key,
                subtotal_returned=subtotal_returned,
                discount_reversal=discount_reversal,
                taxable_reversal=taxable_reversal,
                tax_reversal=tax_reversal,
                total_refund_amount=total_refund_amount,
                cogs_reversal_total=cogs_reversal_total,
                writeoff_cost_total=writeoff_cost_total,
                items=return_items,
            )
            self._session.add(sales_return)
            try:
                with self._session.begin_nested():
                    self._session.flush()
                return sales_return
            except IntegrityError as ie:
                if "return_number" in str(ie).lower() and attempt < max_retries - 1:
                    logger.warning(
                        f"Return number collision on {return_number} (attempt {attempt + 1}), retrying next sequence..."
                    )
                    self._session.expunge(sales_return)
                    continue
                raise ie

        raise RuntimeError("Failed to generate a unique return number after multiple attempts.")

    def _get_previously_returned_quantities(self, sale_id: int) -> Dict[int, int]:
        """Query cumulative completed return quantities per sale_line_item_id."""
        rows = (
            self._session.query(
                SalesReturnItem.sale_line_item_id,
                func.sum(SalesReturnItem.quantity).label("total_returned"),
            )
            .join(SalesReturn, SalesReturn.id == SalesReturnItem.sales_return_id)
            .filter(
                SalesReturn.sale_id == sale_id,
                SalesReturn.status == ReturnStatus.COMPLETED.value,
            )
            .group_by(SalesReturnItem.sale_line_item_id)
            .all()
        )
        return {row.sale_line_item_id: int(row.total_returned) for row in rows}

    def _resolve_approver(self, actor: Optional[User], approver: Optional[User]) -> User:
        """
        Determine and validate the authoritative approving user.
        - Verifies active status of actor and approver.
        - If actor is Manager/Admin with 'refund_approve': self-approval permitted.
        - If actor is Cashier without 'refund_approve': active approver with 'refund_approve' mandatory.
        """
        if actor is not None and not actor.is_active:
            raise AuthorizationError(f"User account '{actor.username}' is inactive.")

        if actor is None:
            if approver:
                if not approver.is_active:
                    raise AuthorizationError(f"Approving user '{approver.username}' is inactive.")
                return approver
            raise AuthorizationError("Approving user is required.")

        actor_can_approve = actor.is_admin() or actor.has_permission("refund_approve")

        if actor_can_approve:
            if approver and approver.id != actor.id:
                if not approver.is_active:
                    raise AuthorizationError(f"Approving user '{approver.username}' is inactive.")
                if not (approver.is_admin() or approver.has_permission("refund_approve")):
                    raise AuthorizationError(f"User '{approver.username}' does not have 'refund_approve' permission.")
                return approver
            return actor

        # Actor lacks refund_approve (e.g. Cashier) -> approver is strictly mandatory
        if not approver:
            raise AuthorizationError("Cashier return processing requires Manager or Administrator refund approval.")

        if not approver.is_active:
            raise AuthorizationError(f"Approving user '{approver.username}' is inactive.")

        if not (approver.is_admin() or approver.has_permission("refund_approve")):
            raise AuthorizationError(f"User '{approver.username}' does not have 'refund_approve' permission.")

        return approver

    def _generate_return_number(self, target_date: date, sequence_offset: int = 0) -> str:
        """
        Generate sequential return number based on target business date (RET-YYYYMMDD-XXXX).
        Queries the highest suffix for today's prefix to prevent collisions.
        """
        date_str = target_date.strftime("%Y%m%d")
        prefix = f"RET-{date_str}-"

        last_return = (
            self._session.query(SalesReturn.return_number)
            .filter(SalesReturn.return_number.like(f"{prefix}%"))
            .order_by(SalesReturn.return_number.desc())
            .first()
        )

        if last_return and last_return[0]:
            try:
                seq = int(last_return[0].split("-")[-1]) + 1 + sequence_offset
            except Exception:
                seq = 1 + sequence_offset
        else:
            seq = 1 + sequence_offset

        return f"{prefix}{seq:04d}"

    def _require_permission(self, actor: Optional[User], permission: str) -> None:
        """Enforce role/permission authorization and active account checks."""
        if actor is None:
            return
        if not actor.is_active:
            raise AuthorizationError(f"User account '{actor.username}' is inactive.")
        if actor.is_admin():
            return
        if not actor.has_permission(permission):
            raise AuthorizationError(f"You do not have permission: '{permission}'.")

    def _to_dto(self, ret: SalesReturn) -> SalesReturnDTO:
        """Convert ORM entity to immutable SalesReturnDTO."""
        item_dtos = [
            SalesReturnItemDTO(
                id=item.id,
                sales_return_id=item.sales_return_id,
                sale_line_item_id=item.sale_line_item_id,
                product_id=item.product_id,
                product_name=item.product_name,
                quantity=item.quantity,
                unit_price_snapshot=item.unit_price_snapshot,
                unit_cost_snapshot=item.unit_cost_snapshot,
                gross_amount_reversal=item.gross_amount_reversal,
                discount_reversal=item.discount_reversal,
                taxable_reversal=item.taxable_reversal,
                tax_reversal=item.tax_reversal,
                total_refund_amount=item.total_refund_amount,
                cogs_reversal=item.cogs_reversal,
                writeoff_cost=item.writeoff_cost,
                disposition=item.disposition,
            )
            for item in ret.items
        ]

        cashier_name = ret.cashier.full_name if ret.cashier else "Unknown"
        approver_name = ret.approved_by.full_name if ret.approved_by else "Unknown"
        created_at_str = ret.created_at.strftime("%Y-%m-%d %H:%M:%S") if ret.created_at else ""

        return SalesReturnDTO(
            id=ret.id,
            return_number=ret.return_number,
            sale_id=ret.sale_id,
            sale_transaction_number=ret.sale.transaction_number if ret.sale else "",
            cashier_id=ret.cashier_id,
            cashier_name=cashier_name,
            approved_by_id=ret.approved_by_id,
            approver_name=approver_name,
            return_date=ret.return_date.strftime("%Y-%m-%d") if ret.return_date else "",
            status=ret.status,
            reason_code=ret.reason_code,
            reason_notes=ret.reason_notes,
            refund_payment_method=ret.refund_payment_method,
            original_payment_method_snapshot=ret.original_payment_method_snapshot,
            refund_reference=ret.refund_reference,
            subtotal_returned=ret.subtotal_returned,
            discount_reversal=ret.discount_reversal,
            taxable_reversal=ret.taxable_reversal,
            tax_reversal=ret.tax_reversal,
            total_refund_amount=ret.total_refund_amount,
            cogs_reversal_total=ret.cogs_reversal_total,
            writeoff_cost_total=ret.writeoff_cost_total,
            created_at=created_at_str,
            items=item_dtos,
        )
