"""
RetailFlow POS - Expense Application Service
Coordinates store operating expense recording, metadata updates, soft-voiding,
voucher sequence generation, KPI metrics, and reporting contracts.
"""

import calendar
import logging
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants import (
    EXPENSE_CATEGORY_LABELS,
    ExpenseCategory,
    ExpenseSource,
    ExpenseStatus,
    PaymentMethod,
)
from application.dto.expense_dto import (
    CreateExpenseDTO,
    ExpenseFilterDTO,
    ExpenseMetricsDTO,
    ExpenseResponseDTO,
    ExpenseSearchResultDTO,
    UpdateExpenseMetadataDTO,
    VoidExpenseDTO,
)
from domain.exceptions import AuthorizationError, RetailFlowError, ValidationError
from infrastructure.database.models.auth import User
from infrastructure.database.models.expense import Expense
from infrastructure.database.repositories.auth import AuditLogRepository

logger = logging.getLogger("retailflow.expenses")

MAX_EXPENSE_AMOUNT = Decimal("999999999.99")
MIN_EXPENSE_AMOUNT = Decimal("0.01")


class ExpenseService:
    """Application service for managing store operational expenses and disbursement vouchers."""

    def __init__(self, session: Session):
        self._session = session
        self._audit_repo = AuditLogRepository(session)

    # ─── Command / Mutation Operations ───

    def create_expense(
        self,
        dto: CreateExpenseDTO,
        actor: Optional[User] = None,
    ) -> ExpenseResponseDTO:
        """
        Record a new store operating expense and generate an audit trail entry atomically.
        Enforces business rules: amount > 0, expense_date <= today, valid category, and voucher sequence generation.
        """
        self._require_permission(actor, "create_expenses")

        # 1. Validation
        if not dto.title or not dto.title.strip():
            raise ValidationError("Expense title is required.")

        if not dto.payee or not dto.payee.strip():
            raise ValidationError("Payee / Vendor name is required.")

        try:
            amount = Decimal(str(dto.amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception:
            raise ValidationError("Invalid monetary amount format.")

        if amount < MIN_EXPENSE_AMOUNT:
            raise ValidationError("Expense amount must be greater than ₱0.00.")

        if amount > MAX_EXPENSE_AMOUNT:
            raise ValidationError(f"Expense amount exceeds allowable maximum of ₱{MAX_EXPENSE_AMOUNT:,.2f}.")

        exp_date = dto.expense_date if isinstance(dto.expense_date, date) else date.fromisoformat(str(dto.expense_date))
        today = date.today()
        if exp_date > today:
            raise ValidationError(f"Expense date cannot be in the future (recorded: {exp_date}, today: {today}).")

        category_val = dto.category.lower().strip()
        if category_val not in ExpenseCategory._value2member_map_:
            raise ValidationError(f"Invalid expense category '{dto.category}'.")

        if category_val == ExpenseCategory.OTHER and (not dto.description or not dto.description.strip()):
            raise ValidationError("Description is required when category is 'other'.")

        payment_method_raw = dto.payment_method.strip().lower()
        if payment_method_raw not in PaymentMethod._value2member_map_:
            raise ValidationError(f"Invalid payment method '{dto.payment_method}'.")
        payment_method_val = payment_method_raw.upper()

        # 2. Sequential Voucher Generation with Retry Protection
        for attempt in range(3):
            voucher_number = self._generate_voucher_number()
            try:
                expense = Expense(
                    voucher_number=voucher_number,
                    category=category_val,
                    title=dto.title.strip(),
                    description=dto.description.strip() if dto.description else None,
                    payee=dto.payee.strip(),
                    amount=amount,
                    payment_method=payment_method_val,
                    reference_number=dto.reference_number.strip() if dto.reference_number else None,
                    expense_date=exp_date,
                    status=ExpenseStatus.PAID,
                    source=ExpenseSource.MANUAL,
                    notes=dto.notes.strip() if dto.notes else None,
                    created_by_id=actor.id if actor else None,
                )
                self._session.add(expense)
                self._session.flush()

                # Audit Log Write (within same atomic transaction)
                self._audit_repo.log_action(
                    user_id=actor.id if actor else None,
                    username=actor.username if actor else "system",
                    action="CREATE_EXPENSE",
                    module="expenses",
                    record_type="expense",
                    record_id=expense.id,
                    new_value=f"Created voucher {voucher_number}: ₱{amount:,.2f} ({category_val.upper()} - {dto.payee.strip()})",
                )
                self._session.commit()
                self._session.refresh(expense)

                logger.info(f"Created expense voucher: {voucher_number} (₱{amount:,.2f} to {dto.payee})")
                return self._to_dto(expense)

            except IntegrityError as e:
                self._session.rollback()
                logger.warning(f"Voucher collision on {voucher_number} (attempt {attempt + 1}/3): {e}")
                if attempt == 2:
                    raise RetailFlowError("Failed to generate unique voucher number after multiple attempts.")
            except Exception as e:
                self._session.rollback()
                raise e

        raise RetailFlowError("Failed to create expense.")

    def update_expense_metadata(
        self,
        expense_id: int,
        dto: UpdateExpenseMetadataDTO,
        actor: Optional[User] = None,
    ) -> ExpenseResponseDTO:
        """
        Update non-financial metadata (payee, description, reference_number, notes).
        Strictly preserves the immutability of financial fields (amount, category, date, payment_method, status).
        """
        self._require_permission(actor, "edit_expenses")

        expense = self._session.get(Expense, expense_id)
        if not expense:
            raise ValidationError(f"Expense with ID {expense_id} not found.")

        if expense.status == ExpenseStatus.VOID:
            raise ValidationError("Cannot edit a voided expense voucher.")

        if not dto.payee or not dto.payee.strip():
            raise ValidationError("Payee / Vendor name cannot be empty.")

        new_payee = dto.payee.strip()
        new_desc = dto.description.strip() if dto.description else None
        new_ref = dto.reference_number.strip() if dto.reference_number else None
        new_notes = dto.notes.strip() if dto.notes else None

        # Check for no-op update
        if (
            expense.payee == new_payee
            and expense.description == new_desc
            and expense.reference_number == new_ref
            and expense.notes == new_notes
        ):
            return self._to_dto(expense)

        prev_snapshot = (
            f"Payee: '{expense.payee}', Ref: '{expense.reference_number}', "
            f"Desc: '{expense.description}', Notes: '{expense.notes}'"
        )
        new_snapshot = (
            f"Payee: '{new_payee}', Ref: '{new_ref}', "
            f"Desc: '{new_desc}', Notes: '{new_notes}'"
        )

        try:
            expense.payee = new_payee
            expense.description = new_desc
            expense.reference_number = new_ref
            expense.notes = new_notes

            self._session.flush()

            self._audit_repo.log_action(
                user_id=actor.id if actor else None,
                username=actor.username if actor else "system",
                action="UPDATE_EXPENSE",
                module="expenses",
                record_type="expense",
                record_id=expense.id,
                previous_value=prev_snapshot,
                new_value=new_snapshot,
            )
            self._session.commit()
            self._session.refresh(expense)

            logger.info(f"Updated metadata for expense voucher {expense.voucher_number}")
            return self._to_dto(expense)
        except Exception as e:
            self._session.rollback()
            raise e

    def void_expense(
        self,
        dto: VoidExpenseDTO,
        actor: Optional[User] = None,
    ) -> ExpenseResponseDTO:
        """
        Soft-cancel/void an active expense voucher.
        Requires a valid cancellation reason (>= 5 chars) and logs an audit trail entry.
        """
        self._require_permission(actor, "void_expenses")

        expense = self._session.get(Expense, dto.expense_id)
        if not expense:
            raise ValidationError(f"Expense with ID {dto.expense_id} not found.")

        if expense.status == ExpenseStatus.VOID:
            raise ValidationError(f"Expense voucher {expense.voucher_number} is already voided.")

        if not dto.void_reason or len(dto.void_reason.strip()) < 5:
            raise ValidationError("A valid void reason is required (minimum 5 characters).")

        reason_clean = dto.void_reason.strip()

        try:
            expense.status = ExpenseStatus.VOID
            expense.void_reason = reason_clean
            expense.voided_at = datetime.now()
            expense.voided_by_id = actor.id if actor else None

            self._session.flush()

            self._audit_repo.log_action(
                user_id=actor.id if actor else None,
                username=actor.username if actor else "system",
                action="VOID_EXPENSE",
                module="expenses",
                record_type="expense",
                record_id=expense.id,
                previous_value=f"Status: PAID (₱{expense.amount:,.2f})",
                new_value="Status: VOID",
                reason=reason_clean,
            )
            self._session.commit()
            self._session.refresh(expense)

            logger.info(f"Voided expense voucher {expense.voucher_number}: reason='{reason_clean}'")
            return self._to_dto(expense)
        except Exception as e:
            self._session.rollback()
            raise e

    # ─── Query Operations ───

    def get_expense(
        self,
        expense_id: int,
        actor: Optional[User] = None,
    ) -> ExpenseResponseDTO:
        """Fetch an individual expense by ID."""
        self._require_permission(actor, "view_expenses")
        expense = self._session.get(Expense, expense_id)
        if not expense:
            raise ValidationError(f"Expense with ID {expense_id} not found.")
        return self._to_dto(expense)

    def search_expenses(
        self,
        filters: ExpenseFilterDTO,
        actor: Optional[User] = None,
    ) -> ExpenseSearchResultDTO:
        """Search and filter expense vouchers with pagination and deterministic sorting."""
        self._require_permission(actor, "view_expenses")

        query = self._session.query(Expense)

        if filters.keyword:
            kw = f"%{filters.keyword.strip()}%"
            query = query.filter(
                (Expense.voucher_number.ilike(kw))
                | (Expense.title.ilike(kw))
                | (Expense.payee.ilike(kw))
                | (Expense.reference_number.ilike(kw))
                | (Expense.description.ilike(kw))
            )

        if filters.category:
            query = query.filter(Expense.category == filters.category.lower().strip())

        if filters.payment_method:
            query = query.filter(Expense.payment_method.ilike(filters.payment_method.strip()))

        if filters.status:
            query = query.filter(Expense.status == filters.status.lower().strip())

        if filters.start_date:
            query = query.filter(Expense.expense_date >= filters.start_date)

        if filters.end_date:
            query = query.filter(Expense.expense_date <= filters.end_date)

        total = query.count()

        offset = (filters.page - 1) * filters.page_size
        items = (
            query.order_by(
                Expense.expense_date.desc(),
                Expense.created_at.desc(),
                Expense.id.desc(),
            )
            .offset(offset)
            .limit(filters.page_size)
            .all()
        )

        return ExpenseSearchResultDTO(
            items=[self._to_dto(e) for e in items],
            total=total,
            page=filters.page,
            page_size=filters.page_size,
        )

    def get_expense_metrics(
        self,
        actor: Optional[User] = None,
    ) -> ExpenseMetricsDTO:
        """
        Compute aggregate KPI metrics for active expenses.
        Excludes VOID records from all financial calculations.
        """
        self._require_permission(actor, "view_expenses")

        # 1. Total Lifetime Active Expenses
        total_opex = self._session.query(
            func.coalesce(func.sum(Expense.amount), 0)
        ).filter(Expense.status == ExpenseStatus.PAID).scalar()

        # 2. Current Calendar Month Spend
        today = date.today()
        month_start = date(today.year, today.month, 1)
        _, last_day = calendar.monthrange(today.year, today.month)
        month_end = date(today.year, today.month, last_day)

        month_spend = self._session.query(
            func.coalesce(func.sum(Expense.amount), 0)
        ).filter(
            Expense.status == ExpenseStatus.PAID,
            Expense.expense_date.between(month_start, month_end),
        ).scalar()

        # 3. Top Expense Category This Month
        top_cat_row = (
            self._session.query(Expense.category, func.sum(Expense.amount).label("cat_total"))
            .filter(
                Expense.status == ExpenseStatus.PAID,
                Expense.expense_date.between(month_start, month_end),
            )
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())
            .first()
        )

        if top_cat_row and top_cat_row[0]:
            top_cat_code = top_cat_row[0]
            top_cat_display = EXPENSE_CATEGORY_LABELS.get(
                top_cat_code, top_cat_code.replace("_", " ").title()
            )
        else:
            top_cat_display = "No Spend This Month"

        # 4. Active Vouchers Count
        active_count = (
            self._session.query(Expense)
            .filter(Expense.status == ExpenseStatus.PAID)
            .count()
        )

        return ExpenseMetricsDTO(
            total_expenses=Decimal(total_opex),
            this_month_spend=Decimal(month_spend),
            top_category_display=top_cat_display,
            active_vouchers_count=active_count,
        )

    # ─── Financial Reporting Contracts (For Future Reports / P&L Module) ───

    def get_total_opex(self, start_date: date, end_date: date) -> Decimal:
        """
        Authoritative contract for P&L calculations.
        Returns total active operating expenses within inclusive date range.
        Excludes VOID records.
        """
        val = (
            self._session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.status == ExpenseStatus.PAID,
                Expense.expense_date.between(start_date, end_date),
            )
            .scalar()
        )
        return Decimal(val)

    def get_category_breakdown(self, start_date: date, end_date: date) -> dict[str, Decimal]:
        """
        Authoritative contract for P&L category breakdown charts.
        Returns mapping of category code -> sum of active expenses within date range.
        """
        rows = (
            self._session.query(Expense.category, func.sum(Expense.amount))
            .filter(
                Expense.status == ExpenseStatus.PAID,
                Expense.expense_date.between(start_date, end_date),
            )
            .group_by(Expense.category)
            .all()
        )
        return {cat: Decimal(tot) for cat, tot in rows}

    # ─── Internal Helper Methods ───

    def _generate_voucher_number(self) -> str:
        """
        Generate sequential voucher number based on local system date (EXP-YYYYMMDD-XXXX).
        Queries the highest suffix for today's prefix to prevent collisions.
        """
        today_str = datetime.now().strftime("%Y%m%d")
        prefix = f"EXP-{today_str}-"

        last_voucher = (
            self._session.query(Expense.voucher_number)
            .filter(Expense.voucher_number.like(f"{prefix}%"))
            .order_by(Expense.voucher_number.desc())
            .first()
        )

        if last_voucher and last_voucher[0]:
            try:
                seq = int(last_voucher[0].split("-")[-1]) + 1
            except Exception:
                seq = 1
        else:
            seq = 1

        return f"{prefix}{seq:04d}"

    def _require_permission(self, actor: Optional[User], permission: str) -> None:
        """Enforce role/permission authorization checks."""
        if actor is None:
            return  # Allow internal system calls if actor is omitted
        if actor.is_admin():
            return
        if not actor.has_permission(permission):
            raise AuthorizationError(f"You do not have permission: '{permission}'.")

    def _to_dto(self, expense: Expense) -> ExpenseResponseDTO:
        """Convert ORM entity to view model DTO."""
        cat_display = EXPENSE_CATEGORY_LABELS.get(
            expense.category, expense.category.replace("_", " ").title()
        )
        exp_date_str = expense.expense_date.strftime("%b %d, %Y") if expense.expense_date else "N/A"
        void_at_str = expense.voided_at.strftime("%b %d, %Y · %I:%M %p") if expense.voided_at else None

        return ExpenseResponseDTO(
            id=expense.id,
            voucher_number=expense.voucher_number,
            category=expense.category,
            category_display=cat_display,
            title=expense.title,
            description=expense.description,
            payee=expense.payee,
            amount=expense.amount,
            payment_method=expense.payment_method,
            payment_method_display=expense.payment_method.replace("_", " ").title(),
            reference_number=expense.reference_number,
            expense_date=exp_date_str,
            status=expense.status,
            source=expense.source,
            notes=expense.notes,
            void_reason=expense.void_reason,
            voided_at=void_at_str,
            created_by_username=expense.created_by.username if expense.created_by else "system",
        )
