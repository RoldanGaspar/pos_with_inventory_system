"""
RetailFlow POS - Expense Seeder Tests (Phase 3)
Tests deterministic demo dataset creation, idempotency, foreign key integrity,
VOID data consistency, P&L reporting accuracy, and runtime sequence compatibility.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.constants import ExpenseCategory, ExpenseStatus
from application.dto.expense_dto import CreateExpenseDTO
from application.services.expense_service import ExpenseService
from infrastructure.database.models.auth import User
from infrastructure.database.models.expense import Expense
from infrastructure.database.seeders.auth_seeder import seed_auth
from infrastructure.database.seeders.expense_seeder import seed_expenses


@pytest.fixture(autouse=True)
def setup_auth(db_session):
    """Seed authentication tables before running seeder tests."""
    seed_auth(db_session)
    db_session.commit()


def test_seed_expenses_creates_records(db_session):
    """Verify seed_expenses populates the expected demo operating expenses."""
    seed_expenses(db_session)
    db_session.commit()

    expenses = db_session.query(Expense).all()
    assert len(expenses) == 10

    paid = [e for e in expenses if e.status == ExpenseStatus.PAID]
    voided = [e for e in expenses if e.status == ExpenseStatus.VOID]
    assert len(paid) == 9
    assert len(voided) == 1

    # Verify categories covered
    categories = {e.category for e in expenses}
    assert ExpenseCategory.UTILITIES in categories
    assert ExpenseCategory.RENT in categories
    assert ExpenseCategory.SALARIES in categories
    assert ExpenseCategory.SUPPLIES in categories
    assert ExpenseCategory.MAINTENANCE in categories
    assert ExpenseCategory.TAXES_LICENSES in categories
    assert ExpenseCategory.MARKETING in categories
    assert ExpenseCategory.OTHER in categories

    # Verify all expense dates <= today
    today = date.today()
    for e in expenses:
        assert e.expense_date <= today
        assert isinstance(e.amount, Decimal)
        assert e.amount > Decimal("0.00")
        assert e.created_by_id is not None
        assert e.voucher_number.startswith("EXP-")


def test_seed_expenses_idempotent(db_session):
    """Verify running seed_expenses multiple times creates no duplicates."""
    seed_expenses(db_session)
    db_session.commit()
    count_first = db_session.query(Expense).count()
    assert count_first == 10

    # Run second time
    seed_expenses(db_session)
    db_session.commit()
    assert db_session.query(Expense).count() == count_first


def test_seed_expenses_coexists_with_manual_records(db_session):
    """Verify pre-existing manual expenses do not block demo data seeding."""
    admin = db_session.query(User).filter(User.username == "admin").first()
    manual = Expense(
        voucher_number="EXP-MANUAL-001",
        category=ExpenseCategory.OTHER,
        title="Pre-existing Manual Expense",
        description="Manual entry before seeding",
        payee="Manual Vendor",
        amount=Decimal("500.00"),
        expense_date=date.today() - timedelta(days=1),
        status=ExpenseStatus.PAID,
        created_by_id=admin.id,
    )
    db_session.add(manual)
    db_session.commit()

    # Seed demo expenses
    seed_expenses(db_session)
    db_session.commit()

    all_expenses = db_session.query(Expense).all()
    # 1 manual + 10 seeded = 11 total
    assert len(all_expenses) == 11
    assert any(e.voucher_number == "EXP-MANUAL-001" for e in all_expenses)


def test_seeded_void_record_integrity(db_session):
    """Verify the seeded VOID record has complete audit-compliant metadata."""
    seed_expenses(db_session)
    db_session.commit()

    void_rec = db_session.query(Expense).filter(Expense.status == ExpenseStatus.VOID).first()
    assert void_rec is not None
    assert void_rec.category == ExpenseCategory.OTHER
    assert void_rec.void_reason is not None
    assert len(void_rec.void_reason) >= 5
    assert void_rec.voided_at is not None
    assert void_rec.voided_by_id is not None
    assert void_rec.voided_by is not None


def test_seeded_data_kpi_and_reporting_calculations(db_session):
    """Verify seeded dataset calculates accurate P&L metrics with VOID exclusion."""
    seed_expenses(db_session)
    db_session.commit()

    service = ExpenseService(db_session)
    admin = db_session.query(User).filter(User.username == "admin").first()

    # Expected sums:
    # 1. Utilities: 14850.75 + 1650.00 + 3134.88 = 19635.63
    # 2. Rent: 35000.00
    # 3. Salaries: 3200.00
    # 4. Supplies: 4650.00
    # 5. Maintenance: 2400.00
    # 6. Taxes/Licenses: 1850.00
    # 7. Marketing: 1500.00
    # Voided Other (1200.00) is excluded
    expected_total_opex = Decimal("68235.63")

    metrics = service.get_expense_metrics(actor=admin)
    assert metrics.total_expenses == expected_total_opex
    assert metrics.active_vouchers_count == 9  # 10 total - 1 VOID = 9
    assert metrics.top_category_display == "Store & Warehouse Rent"  # Rent (35k) is top

    # Test reporting contract for wide date range
    total_opex = service.get_total_opex(date.today() - timedelta(days=60), date.today())
    assert total_opex == expected_total_opex

    breakdown = service.get_category_breakdown(date.today() - timedelta(days=60), date.today())
    assert breakdown["utilities"] == Decimal("19635.63")
    assert breakdown["rent"] == Decimal("35000.00")
    assert breakdown["salaries"] == Decimal("3200.00")
    assert breakdown["supplies"] == Decimal("4650.00")
    assert breakdown["maintenance"] == Decimal("2400.00")
    assert breakdown["taxes_licenses"] == Decimal("1850.00")
    assert breakdown["marketing"] == Decimal("1500.00")
    assert "other" not in breakdown  # Voided only category excluded from active breakdown


def test_runtime_voucher_generation_after_seeding(db_session):
    """Verify runtime ExpenseService.create_expense() generates valid unique vouchers after seeding."""
    seed_expenses(db_session)
    db_session.commit()

    service = ExpenseService(db_session)
    admin = db_session.query(User).filter(User.username == "admin").first()

    dto = CreateExpenseDTO(
        category="utilities",
        title="Runtime Electricity Adjustment",
        payee="Meralco",
        amount=Decimal("550.00"),
        expense_date=date.today(),
    )

    resp = service.create_expense(dto, actor=admin)
    assert resp.id is not None
    assert resp.voucher_number.startswith("EXP-")

    # Verify total vouchers count is now 11
    assert db_session.query(Expense).count() == 11
