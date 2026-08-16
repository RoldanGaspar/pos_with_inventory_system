"""
RetailFlow POS - Store Operating Expenses Seeder
Populates a realistic demo dataset of Philippine store operational disbursements
across multiple categories, payment methods, and historical date ranges.
Idempotent and safe across multiple bootstrap executions.
"""

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.constants import ExpenseCategory, ExpenseSource, ExpenseStatus, PaymentMethod
from infrastructure.database.models.auth import User
from infrastructure.database.models.expense import Expense
from infrastructure.database.repositories.auth import AuditLogRepository

logger = logging.getLogger("retailflow.database")


def seed_expenses(session: Session) -> None:
    """Seed realistic Philippine store operating expenses."""
    admin_user = session.query(User).filter(User.username == "admin").first()
    if not admin_user:
        admin_user = session.query(User).first()

    if not admin_user:
        logger.warning("Cannot seed expenses: No admin user found in database.")
        return

    manager_user = session.query(User).filter(User.username == "manager").first() or admin_user

    # Fetch existing voucher numbers to guarantee idempotency
    existing_vouchers = {v[0] for v in session.query(Expense.voucher_number).all()}

    today = date.today()
    now_dt = datetime.now()

    # Raw demo records with relative dates to ensure historical integrity
    demo_expenses_raw = [
        # 1. Utilities (Electric) - 12 days ago
        {
            "category": ExpenseCategory.UTILITIES,
            "title": "Meralco Commercial Electric Bill",
            "description": "Electric utility charges for main store sales floor and storage refrigeration.",
            "payee": "Manila Electric Company (Meralco)",
            "amount": Decimal("14850.75"),
            "payment_method": PaymentMethod.BANK_TRANSFER.upper(),
            "reference_number": "MERALCO-2026-088192",
            "expense_date": today - timedelta(days=12),
            "status": ExpenseStatus.PAID,
            "source": ExpenseSource.MANUAL,
            "notes": "Auto-debited via BDO Corporate Online banking.",
            "created_by_id": admin_user.id,
        },
        # 2. Utilities (Water) - 8 days ago
        {
            "category": ExpenseCategory.UTILITIES,
            "title": "Maynilad Commercial Water Utility",
            "description": "Monthly water consumption for store restrooms and daily sanitation.",
            "payee": "Maynilad Water Services Inc.",
            "amount": Decimal("1650.00"),
            "payment_method": PaymentMethod.GCASH.upper(),
            "reference_number": "MAY-9988231",
            "expense_date": today - timedelta(days=8),
            "status": ExpenseStatus.PAID,
            "source": ExpenseSource.MANUAL,
            "notes": "Paid via GCash Cashier register account.",
            "created_by_id": manager_user.id,
        },
        # 3. Utilities (Internet) - 4 days ago
        {
            "category": ExpenseCategory.UTILITIES,
            "title": "PLDT Enterprise Fiber Internet",
            "description": "100Mbps dedicated fiber connection for POS terminals and cloud CCTV.",
            "payee": "PLDT Inc.",
            "amount": Decimal("3134.88"),
            "payment_method": PaymentMethod.BANK_TRANSFER.upper(),
            "reference_number": "PLDT-ACC-4009128",
            "expense_date": today - timedelta(days=4),
            "status": ExpenseStatus.PAID,
            "source": ExpenseSource.MANUAL,
            "notes": "Monthly billing statement for August 2026.",
            "created_by_id": admin_user.id,
        },
        # 4. Store Rent - 14 days ago
        {
            "category": ExpenseCategory.RENT,
            "title": "Store & Warehouse Monthly Lease",
            "description": "Ground floor commercial retail unit 102 and mezzanine warehouse rental.",
            "payee": "Ayala Land Commercial Properties Inc.",
            "amount": Decimal("35000.00"),
            "payment_method": PaymentMethod.BANK_TRANSFER.upper(),
            "reference_number": "OR-AYL-202608-019",
            "expense_date": today - timedelta(days=14),
            "status": ExpenseStatus.PAID,
            "source": ExpenseSource.MANUAL,
            "notes": "Wire transfer payment with 5% withholding tax deducted.",
            "created_by_id": admin_user.id,
        },
        # 5. Staff Wages & Allowances - 2 days ago
        {
            "category": ExpenseCategory.SALARIES,
            "title": "Weekend Casual Store Staff Allowance",
            "description": "Daily stipend for 2 temporary stock replenishment clerks (2-day shift).",
            "payee": "Store Crew Weekly Allowance",
            "amount": Decimal("3200.00"),
            "payment_method": PaymentMethod.CASH.upper(),
            "reference_number": "VCH-STF-0813",
            "expense_date": today - timedelta(days=2),
            "status": ExpenseStatus.PAID,
            "source": ExpenseSource.MANUAL,
            "notes": "Disbursed from petty cash drawer with signed worker acknowledgement slips.",
            "created_by_id": manager_user.id,
        },
        # 6. Store Supplies - 6 days ago
        {
            "category": ExpenseCategory.SUPPLIES,
            "title": "Store Sando Bags & Thermal Paper Rolls",
            "description": "5 bundles large biodegradable sando bags and 50 rolls 80mm thermal receipt paper.",
            "payee": "GreenPack Packaging Supply Corp.",
            "amount": Decimal("4650.00"),
            "payment_method": PaymentMethod.CASH.upper(),
            "reference_number": "SI-GP-58491",
            "expense_date": today - timedelta(days=6),
            "status": ExpenseStatus.PAID,
            "source": ExpenseSource.MANUAL,
            "notes": "Official sales invoice issued upon delivery.",
            "created_by_id": manager_user.id,
        },
        # 7. Repairs & Maintenance - 3 days ago
        {
            "category": ExpenseCategory.MAINTENANCE,
            "title": "POS Barcode Scanner & Printer Calibration",
            "description": "Quarterly calibration, laser cleaning, and thermal printhead maintenance for 2 stations.",
            "payee": "TechServ POS Solutions",
            "amount": Decimal("2400.00"),
            "payment_method": PaymentMethod.MAYA.upper(),
            "reference_number": "MAYA-TXN-881902",
            "expense_date": today - timedelta(days=3),
            "status": ExpenseStatus.PAID,
            "source": ExpenseSource.MANUAL,
            "notes": "Includes 30-day service warranty.",
            "created_by_id": admin_user.id,
        },
        # 8. Taxes, Permits & Licenses - 25 days ago (Previous Month)
        {
            "category": ExpenseCategory.TAXES_LICENSES,
            "title": "Q3 Local Barangay Clearance & Sanitary Permit",
            "description": "Quarterly barangay business renewal and annual sanitary inspection fees.",
            "payee": "Barangay Treasurer Office",
            "amount": Decimal("1850.00"),
            "payment_method": PaymentMethod.CASH.upper(),
            "reference_number": "OR-BRGY-77129",
            "expense_date": today - timedelta(days=25),
            "status": ExpenseStatus.PAID,
            "source": ExpenseSource.MANUAL,
            "notes": "Official government receipt filed in store compliance binder.",
            "created_by_id": admin_user.id,
        },
        # 9. Marketing & Promotion - 5 days ago
        {
            "category": ExpenseCategory.MARKETING,
            "title": "Facebook Local Store Promotion Boost",
            "description": "Targeted local advertising campaign for mid-month payday shopping weekend.",
            "payee": "Meta Platforms Inc. (FB Ads)",
            "amount": Decimal("1500.00"),
            "payment_method": PaymentMethod.CREDIT_CARD.upper(),
            "reference_number": "CC-META-81920",
            "expense_date": today - timedelta(days=5),
            "status": ExpenseStatus.PAID,
            "source": ExpenseSource.MANUAL,
            "notes": "Charged to store corporate Mastercard.",
            "created_by_id": admin_user.id,
        },
        # 10. Miscellaneous / VOID Example - 7 days ago
        {
            "category": ExpenseCategory.OTHER,
            "title": "Emergency Electrical Wiring Check (Duplicate Entry)",
            "description": "Emergency breaker inspection by freelance technician.",
            "payee": "Spark Electrical Services",
            "amount": Decimal("1200.00"),
            "payment_method": PaymentMethod.CASH.upper(),
            "reference_number": "RCPT-SPK-001",
            "expense_date": today - timedelta(days=7),
            "status": ExpenseStatus.VOID,
            "source": ExpenseSource.MANUAL,
            "notes": "Accidentally entered twice by opening and closing cashiers.",
            "created_by_id": admin_user.id,
            "void_reason": "Duplicate billing voucher entered by mistake. Correct voucher paid under maintenance.",
            "voided_at": now_dt - timedelta(days=6),
            "voided_by_id": manager_user.id,
        },
    ]

    # Assign deterministic daily sequence numbers
    daily_counters = defaultdict(int)
    seeded_count = 0

    for item in demo_expenses_raw:
        exp_d = item["expense_date"]
        d_str = exp_d.strftime("%Y%m%d")
        daily_counters[d_str] += 1
        voucher_no = f"EXP-{d_str}-{daily_counters[d_str]:04d}"

        if voucher_no in existing_vouchers:
            continue

        expense = Expense(
            voucher_number=voucher_no,
            category=item["category"],
            title=item["title"],
            description=item["description"],
            payee=item["payee"],
            amount=item["amount"],
            payment_method=item["payment_method"],
            reference_number=item["reference_number"],
            expense_date=item["expense_date"],
            status=item["status"],
            source=item["source"],
            notes=item["notes"],
            created_by_id=item["created_by_id"],
            void_reason=item.get("void_reason"),
            voided_at=item.get("voided_at"),
            voided_by_id=item.get("voided_by_id"),
        )
        session.add(expense)
        session.flush()

        # Write audit logs for seeded records
        audit_repo = AuditLogRepository(session)
        audit_repo.log_action(
            user_id=item["created_by_id"],
            username=admin_user.username if item["created_by_id"] == admin_user.id else manager_user.username,
            action="CREATE_EXPENSE",
            module="expenses",
            record_type="expense",
            record_id=expense.id,
            new_value=f"Seeded voucher {voucher_no}: ₱{item['amount']:,.2f} ({item['category'].upper()} - {item['payee']})",
        )

        if item["status"] == ExpenseStatus.VOID:
            audit_repo.log_action(
                user_id=item.get("voided_by_id"),
                username=manager_user.username,
                action="VOID_EXPENSE",
                module="expenses",
                record_type="expense",
                record_id=expense.id,
                previous_value=f"Status: PAID (₱{item['amount']:,.2f})",
                new_value="Status: VOID",
                reason=item.get("void_reason"),
            )

        existing_vouchers.add(voucher_no)
        seeded_count += 1

    if seeded_count > 0:
        session.flush()
        logger.info(f"Seeded {seeded_count} demo store operating expense records with audit trails.")
    else:
        logger.info("Demo expense records already exist. Skipping seeder.")
