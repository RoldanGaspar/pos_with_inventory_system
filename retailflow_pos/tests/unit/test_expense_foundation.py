"""
RetailFlow POS - Expense Foundation Tests (Phase 1)
Tests constants, ORM model persistence, unique constraints, DTO immutability, and permissions.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.constants import (
    EXPENSE_CATEGORY_LABELS,
    ExpenseCategory,
    ExpenseSource,
    ExpenseStatus,
    UserRole,
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
from infrastructure.database.models.auth import User
from infrastructure.database.models.expense import Expense
from infrastructure.database.seeders.auth_seeder import (
    DEFAULT_PERMISSIONS,
    ROLE_PERMISSIONS,
    seed_auth,
)


# ─── 1. Constants Tests ───

def test_expense_constants_values():
    assert ExpenseCategory.UTILITIES == "utilities"
    assert ExpenseCategory.RENT == "rent"
    assert ExpenseCategory.SALARIES == "salaries"
    assert ExpenseCategory.SUPPLIES == "supplies"
    assert ExpenseCategory.MAINTENANCE == "maintenance"
    assert ExpenseCategory.TAXES_LICENSES == "taxes_licenses"
    assert ExpenseCategory.MARKETING == "marketing"
    assert ExpenseCategory.OTHER == "other"

    assert ExpenseStatus.PAID == "paid"
    assert ExpenseStatus.VOID == "void"

    assert ExpenseSource.MANUAL == "manual"
    assert ExpenseSource.PAYROLL == "payroll"


def test_expense_category_labels_mapping():
    assert len(EXPENSE_CATEGORY_LABELS) == 8
    assert EXPENSE_CATEGORY_LABELS[ExpenseCategory.UTILITIES] == "Utilities (Power, Water, Internet)"
    assert EXPENSE_CATEGORY_LABELS[ExpenseCategory.RENT] == "Store & Warehouse Rent"
    assert EXPENSE_CATEGORY_LABELS[ExpenseCategory.SALARIES] == "Staff Wages & Allowances"
    assert EXPENSE_CATEGORY_LABELS[ExpenseCategory.OTHER] == "Other Miscellaneous"


# ─── 2. ORM Model Tests ───

def test_expense_orm_persistence(db_session):
    user = User(
        username="test_admin_exp",
        email="admin_exp@example.com",
        password_hash="fakehash",
        full_name="Admin Exp",
    )
    db_session.add(user)
    db_session.flush()

    exp = Expense(
        voucher_number="EXP-20260815-0001",
        category=ExpenseCategory.UTILITIES,
        title="Meralco Electric Bill",
        description="Electricity for store and storage area",
        payee="Meralco",
        amount=Decimal("4520.75"),
        payment_method="CASH",
        reference_number="OR-998877",
        expense_date=date(2026, 8, 15),
        status=ExpenseStatus.PAID,
        source=ExpenseSource.MANUAL,
        notes="Paid from petty cash drawer",
        created_by_id=user.id,
    )
    db_session.add(exp)
    db_session.commit()

    saved = db_session.query(Expense).filter(Expense.voucher_number == "EXP-20260815-0001").first()
    assert saved is not None
    assert saved.id is not None
    assert saved.amount == Decimal("4520.75")
    assert saved.category == ExpenseCategory.UTILITIES
    assert saved.status == ExpenseStatus.PAID
    assert saved.created_by.username == "test_admin_exp"
    assert saved.void_reason is None
    assert saved.voided_at is None


def test_expense_orm_unique_voucher_constraint(db_session):
    exp1 = Expense(
        voucher_number="EXP-UNIQUE-001",
        category=ExpenseCategory.RENT,
        title="Store Rent",
        payee="Landlord",
        amount=Decimal("15000.00"),
        expense_date=date(2026, 8, 1),
    )
    exp2 = Expense(
        voucher_number="EXP-UNIQUE-001",
        category=ExpenseCategory.SUPPLIES,
        title="Paper Bags",
        payee="Packaging Co",
        amount=Decimal("2000.00"),
        expense_date=date(2026, 8, 2),
    )
    db_session.add(exp1)
    db_session.commit()

    db_session.add(exp2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_expense_orm_void_relationship(db_session):
    admin = User(username="admin_void", email="av@example.com", password_hash="h", full_name="Admin")
    mgr = User(username="mgr_void", email="mv@example.com", password_hash="h", full_name="Manager")
    db_session.add_all([admin, mgr])
    db_session.flush()

    exp = Expense(
        voucher_number="EXP-VOID-001",
        category=ExpenseCategory.MAINTENANCE,
        title="Aircon Repair",
        payee="Cooling Services",
        amount=Decimal("1200.00"),
        expense_date=date(2026, 8, 10),
        status=ExpenseStatus.VOID,
        created_by_id=admin.id,
        void_reason="Duplicate bill recorded in error",
        voided_at=datetime.now(),
        voided_by_id=mgr.id,
    )
    db_session.add(exp)
    db_session.commit()

    saved = db_session.query(Expense).filter(Expense.voucher_number == "EXP-VOID-001").first()
    assert saved.status == ExpenseStatus.VOID
    assert saved.created_by.username == "admin_void"
    assert saved.voided_by.username == "mgr_void"
    assert saved.void_reason == "Duplicate bill recorded in error"


# ─── 3. DTO Contracts Tests ───

def test_dto_contracts_immutability():
    create_dto = CreateExpenseDTO(
        category="utilities",
        title="PLDT Fiber",
        payee="PLDT",
        amount=Decimal("2899.00"),
        expense_date=date(2026, 8, 15),
    )
    assert create_dto.category == "utilities"
    assert create_dto.amount == Decimal("2899.00")

    # Verify frozen
    with pytest.raises(Exception):
        create_dto.amount = Decimal("3000.00")  # type: ignore

    update_dto = UpdateExpenseMetadataDTO(
        payee="PLDT Enterprise",
        description="Updated account number",
        reference_number="OR-12345",
        notes="Corrected payee name",
    )
    assert update_dto.payee == "PLDT Enterprise"
    assert not hasattr(update_dto, "amount")
    assert not hasattr(update_dto, "category")
    assert not hasattr(update_dto, "expense_date")
    assert not hasattr(update_dto, "voucher_number")

    void_dto = VoidExpenseDTO(expense_id=1, void_reason="Wrong amount entered")
    assert void_dto.expense_id == 1
    assert void_dto.void_reason == "Wrong amount entered"


# ─── 4. Permissions Tests ───

def test_expense_permissions_registered():
    assert "expenses" in DEFAULT_PERMISSIONS
    codes = [p[0] for p in DEFAULT_PERMISSIONS["expenses"]]
    assert "view_expenses" in codes
    assert "create_expenses" in codes
    assert "edit_expenses" in codes
    assert "void_expenses" in codes

    manager_perms = ROLE_PERMISSIONS[UserRole.MANAGER]
    assert "view_expenses" in manager_perms
    assert "create_expenses" in manager_perms
    assert "edit_expenses" in manager_perms
    assert "void_expenses" in manager_perms

    cashier_perms = ROLE_PERMISSIONS[UserRole.CASHIER]
    assert "view_expenses" in cashier_perms
    assert "create_expenses" in cashier_perms
    assert "edit_expenses" not in cashier_perms
    assert "void_expenses" not in cashier_perms


def test_seed_auth_idempotent_with_expenses(db_session):
    seed_auth(db_session)
    first_count = db_session.query(User).count()
    assert first_count >= 1

    # Run again to ensure no duplicate key errors
    seed_auth(db_session)
    assert db_session.query(User).count() == first_count
