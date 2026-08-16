"""
RetailFlow POS - Store Settings Foundation Unit Tests
Verifies StoreSettings ORM model defaults, singleton check constraints,
paper width constraints, foreign key integrity, schema migration, and seeder idempotency.
"""

from datetime import datetime
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.constants import ReceiptWidth
from infrastructure.database.models.auth import User
from infrastructure.database.models.base import Base
from infrastructure.database.models.settings import StoreSettings
from infrastructure.database.seeders.settings_seeder import seed_settings
from infrastructure.database.session import _migrate_schema


def test_store_settings_model_defaults(db_session):
    """StoreSettings ORM entity populates canonical factory defaults."""
    settings = StoreSettings(id=1)
    db_session.add(settings)
    db_session.commit()

    saved = db_session.query(StoreSettings).filter_by(id=1).first()
    assert saved is not None
    assert saved.id == 1
    assert saved.store_name == "RetailFlow Store"
    assert saved.receipt_header == "Official Sales Invoice / Thermal Receipt"
    assert saved.receipt_footer == "Thank you for shopping with us!"
    assert saved.paper_width == ReceiptWidth.MM_80.value
    assert saved.show_store_address is True
    assert saved.show_contact is True
    assert saved.show_tin is True
    assert saved.show_tax_details is True

    # Optional fields default to None
    assert saved.store_address is None
    assert saved.contact_number is None
    assert saved.email is None
    assert saved.tin is None
    assert saved.logo_path is None
    assert saved.updated_by_id is None
    assert isinstance(saved.created_at, datetime)
    assert isinstance(saved.updated_at, datetime)


def test_store_settings_optional_fields_persistence(db_session):
    """StoreSettings accepts all optional profile fields."""
    settings = StoreSettings(
        id=1,
        store_name="Makati Supermarket",
        store_address="123 Ayala Avenue, Makati City, Metro Manila",
        contact_number="+63 2 8123 4567",
        email="support@makatisupermarket.ph",
        tin="123-456-789-000",
        logo_path="assets/makati_logo.png",
        receipt_header="Makati Supermarket - Official Receipt",
        receipt_footer="Returns accepted within 7 days with receipt.",
        paper_width=ReceiptWidth.MM_58.value,
        show_store_address=False,
        show_contact=False,
        show_tin=False,
        show_tax_details=False,
    )
    db_session.add(settings)
    db_session.commit()

    saved = db_session.query(StoreSettings).filter_by(id=1).first()
    assert saved.store_name == "Makati Supermarket"
    assert saved.store_address == "123 Ayala Avenue, Makati City, Metro Manila"
    assert saved.contact_number == "+63 2 8123 4567"
    assert saved.email == "support@makatisupermarket.ph"
    assert saved.tin == "123-456-789-000"
    assert saved.logo_path == "assets/makati_logo.png"
    assert saved.paper_width == "58mm"
    assert saved.show_store_address is False
    assert saved.show_tax_details is False


def test_singleton_invariant_check_constraint(db_session):
    """StoreSettings rejects any row where id != 1 via ck_store_settings_single_row."""
    invalid_settings = StoreSettings(
        id=2,
        store_name="Second Store",
    )
    db_session.add(invalid_settings)

    with pytest.raises(IntegrityError) as exc_info:
        db_session.commit()
    db_session.rollback()

    assert "ck_store_settings_single_row" in str(exc_info.value) or "CHECK constraint failed" in str(exc_info.value)


def test_singleton_invariant_primary_key_uniqueness(db_session):
    """StoreSettings rejects multiple rows with id = 1 via PK uniqueness."""
    from sqlalchemy import text

    row1 = StoreSettings(id=1, store_name="Primary Store")
    db_session.add(row1)
    db_session.commit()

    # Attempt to insert duplicate id = 1 directly into DB
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO store_settings (id, store_name, paper_width, show_store_address, show_contact, show_tin, show_tax_details, created_at, updated_at) "
                "VALUES (1, 'Duplicate Store', '80mm', 1, 1, 1, 1, '2026-08-16 00:00:00', '2026-08-16 00:00:00')"
            )
        )
        db_session.commit()
    db_session.rollback()


def test_paper_width_check_constraint(db_session):
    """StoreSettings accepts '58mm' and '80mm', and rejects invalid paper widths."""
    # 1. 58mm valid
    s58 = StoreSettings(id=1, paper_width="58mm")
    db_session.add(s58)
    db_session.commit()
    assert db_session.query(StoreSettings).first().paper_width == "58mm"

    # 2. 80mm valid
    db_session.query(StoreSettings).filter_by(id=1).update({"paper_width": "80mm"})
    db_session.commit()
    assert db_session.query(StoreSettings).first().paper_width == "80mm"

    # 3. Invalid paper width rejected
    with pytest.raises(IntegrityError) as exc_info:
        db_session.query(StoreSettings).filter_by(id=1).update({"paper_width": "72mm"})
        db_session.commit()
    db_session.rollback()

    assert "ck_store_settings_paper_width" in str(exc_info.value) or "CHECK constraint failed" in str(exc_info.value)


def test_updated_by_foreign_key_relationship(db_session):
    """StoreSettings updated_by_id links to User and supports null bootstrap values."""
    # 1. Null updated_by_id (bootstrap)
    settings = StoreSettings(id=1, updated_by_id=None)
    db_session.add(settings)
    db_session.commit()
    assert settings.updated_by is None

    # 2. Valid User updated_by_id
    admin = User(
        username="settings_admin",
        email="admin@example.com",
        password_hash="hash",
        full_name="Settings Admin",
    )
    db_session.add(admin)
    db_session.flush()

    settings.updated_by = admin
    db_session.commit()

    reloaded = db_session.query(StoreSettings).filter_by(id=1).first()
    assert reloaded.updated_by_id == admin.id
    assert reloaded.updated_by is not None
    assert reloaded.updated_by.username == "settings_admin"


def test_settings_seeder_idempotent_and_creates_canonical_row(db_session):
    """seed_settings creates row id=1 on first run and is idempotent on repeat runs."""
    assert db_session.query(StoreSettings).count() == 0

    # 1. First run creates row
    seed_settings(db_session)
    db_session.commit()

    assert db_session.query(StoreSettings).count() == 1
    row = db_session.query(StoreSettings).filter_by(id=1).first()
    assert row.store_name == "RetailFlow Store"
    assert row.paper_width == "80mm"

    # 2. Second run is a no-op
    seed_settings(db_session)
    db_session.commit()
    assert db_session.query(StoreSettings).count() == 1


def test_settings_seeder_preserves_customized_settings_on_restart(db_session):
    """Customized settings must survive application restart/seeding without resetting."""
    seed_settings(db_session)
    db_session.commit()

    # User customizes store settings
    row = db_session.query(StoreSettings).filter_by(id=1).first()
    row.store_name = "ABC Supermart"
    row.paper_width = "58mm"
    row.receipt_header = "Welcome to ABC Supermart"
    db_session.commit()

    # Re-run seeder (simulating subsequent bootstrap on restart)
    seed_settings(db_session)
    db_session.commit()

    # Verify customized settings remain completely preserved
    saved = db_session.query(StoreSettings).filter_by(id=1).first()
    assert saved.store_name == "ABC Supermart"
    assert saved.paper_width == "58mm"
    assert saved.receipt_header == "Welcome to ABC Supermart"


def test_schema_migration_pre_settings_database():
    """Existing databases without store_settings receive the table during _migrate_schema."""
    test_engine = create_engine("sqlite:///:memory:")

    # Create all tables EXCEPT store_settings
    tables_to_create = [
        table for name, table in Base.metadata.tables.items() if name != "store_settings"
    ]
    Base.metadata.create_all(bind=test_engine, tables=tables_to_create)

    inspector = inspect(test_engine)
    assert "store_settings" not in inspector.get_table_names()
    assert "products" in inspector.get_table_names()
    assert "sales" in inspector.get_table_names()

    # Run migration
    _migrate_schema(test_engine)

    inspector_after = inspect(test_engine)
    assert "store_settings" in inspector_after.get_table_names()

    # Verify table structure
    columns = {col["name"]: col for col in inspector_after.get_columns("store_settings")}
    assert "store_name" in columns
    assert "paper_width" in columns
    assert "receipt_header" in columns
    assert "show_tax_details" in columns
    assert "updated_by_id" in columns
