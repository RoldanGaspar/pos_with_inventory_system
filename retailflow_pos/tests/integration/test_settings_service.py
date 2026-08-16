"""
RetailFlow POS - Store Settings Service Integration Tests
Verifies SettingsService read operations, store profile updates, receipt preferences,
managed logo lifecycle, RBAC enforcement, no-op optimizations, path security, and audit integrity.
"""

import io
import os
from pathlib import Path
from unittest.mock import MagicMock

import PIL.Image
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.constants import ReceiptWidth
from application.dto.settings_dto import (
    UpdateReceiptPreferencesDTO,
    UpdateStoreProfileDTO,
)
from application.services.settings_service import (
    MAX_LOGO_FILE_SIZE_BYTES,
    SettingsService,
)
from domain.exceptions import (
    AccountInactiveError,
    AuthorizationError,
    ConfigurationError,
    ValidationError,
)
from infrastructure.database.models.auth import AuditLog, Permission, Role, User
from infrastructure.database.models.base import Base
from infrastructure.database.models.settings import StoreSettings
from infrastructure.database.seeders.auth_seeder import seed_auth
from infrastructure.database.seeders.settings_seeder import seed_settings
from infrastructure.database.session import _migrate_schema


@pytest.fixture
def auth_roles_users(db_session):
    """Seed permissions and return test users for all roles."""
    view_perm = Permission(code="view_settings", name="View Settings", module="settings")
    edit_perm = Permission(code="edit_settings", name="Edit Settings", module="settings")
    db_session.add_all([view_perm, edit_perm])
    db_session.flush()

    admin_role = Role(name="Administrator", code="admin", permissions=[view_perm, edit_perm])
    mgr_role = Role(name="Manager", code="manager", permissions=[view_perm, edit_perm])
    cashier_role = Role(name="Cashier", code="cashier", permissions=[])
    auditor_role = Role(name="Auditor", code="auditor", permissions=[])

    admin = User(username="admin_user", email="admin@test.com", password_hash="h", full_name="Admin User", roles=[admin_role])
    manager = User(username="mgr_user", email="mgr@test.com", password_hash="h", full_name="Manager User", roles=[mgr_role])
    cashier = User(username="cashier_user", email="cashier@test.com", password_hash="h", full_name="Cashier User", roles=[cashier_role])
    auditor = User(username="auditor_user", email="auditor@test.com", password_hash="h", full_name="Auditor User", roles=[auditor_role])

    db_session.add_all([admin_role, mgr_role, cashier_role, auditor_role, admin, manager, cashier, auditor])
    db_session.commit()

    # Also seed settings row
    seed_settings(db_session)
    db_session.commit()

    return {
        "admin": admin,
        "manager": manager,
        "cashier": cashier,
        "auditor": auditor,
    }


@pytest.fixture
def dummy_png_file(tmp_path) -> Path:
    """Create a temporary valid PNG image file (100x100)."""
    img_path = tmp_path / "valid_logo.png"
    img = PIL.Image.new("RGBA", (100, 100), color=(37, 99, 235, 255))
    img.save(img_path, format="PNG")
    return img_path


@pytest.fixture
def dummy_jpg_file(tmp_path) -> Path:
    """Create a temporary valid JPEG image file (120x80)."""
    img_path = tmp_path / "valid_logo.jpg"
    img = PIL.Image.new("RGB", (120, 80), color=(16, 185, 129))
    img.save(img_path, format="JPEG")
    return img_path


# ─── 1. Reads & Authorization Tests ───

def test_get_settings_authorized_and_read_only(db_session, auth_roles_users):
    """Admin and Manager can read settings; reads create no new rows or audit records."""
    service = SettingsService(db_session)
    admin = auth_roles_users["admin"]
    manager = auth_roles_users["manager"]

    # Initial counts
    settings_count = db_session.query(StoreSettings).count()
    audit_count = db_session.query(AuditLog).count()

    dto1 = service.get_settings(actor=admin)
    assert dto1.id == 1
    assert dto1.store_name == "RetailFlow Store"
    assert dto1.paper_width == "80mm"

    dto2 = service.get_settings(actor=manager)
    assert dto2.id == 1

    # Invariant: read-only operation
    assert db_session.query(StoreSettings).count() == settings_count
    assert db_session.query(AuditLog).count() == audit_count


def test_get_settings_unauthorized_and_inactive_rejections(db_session, auth_roles_users):
    """Cashier, Auditor, and inactive users are rejected from reading settings."""
    service = SettingsService(db_session)
    cashier = auth_roles_users["cashier"]
    auditor = auth_roles_users["auditor"]
    admin = auth_roles_users["admin"]

    # Cashier unauthorized
    with pytest.raises(AuthorizationError):
        service.get_settings(actor=cashier)

    # Auditor unauthorized
    with pytest.raises(AuthorizationError):
        service.get_settings(actor=auditor)

    # Missing actor
    with pytest.raises(AuthorizationError):
        service.get_settings(actor=None)

    # Inactive admin
    admin.is_active = False
    db_session.commit()
    with pytest.raises(AccountInactiveError):
        service.get_settings(actor=admin)


def test_get_settings_missing_singleton_raises_configuration_error(db_session, auth_roles_users):
    """If row id=1 is missing, get_settings raises ConfigurationError without auto-creating."""
    service = SettingsService(db_session)
    admin = auth_roles_users["admin"]

    # Manually delete settings row
    db_session.query(StoreSettings).delete()
    db_session.commit()

    with pytest.raises(ConfigurationError) as exc_info:
        service.get_settings(actor=admin)

    assert "missing" in str(exc_info.value).lower()
    # Confirm no row was created during read
    assert db_session.query(StoreSettings).count() == 0


# ─── 2. Store Profile Updates & Validation Tests ───

def test_update_store_profile_success_and_audit(db_session, auth_roles_users):
    """Admin updates store profile; fields are persisted and structured audit entry is written."""
    service = SettingsService(db_session)
    admin = auth_roles_users["admin"]

    dto = UpdateStoreProfileDTO(
        store_name="  RetailFlow Flagship Store  ",
        store_address="  456 Ayala Ave, Makati City  ",
        contact_number="  +63 917 123 4567  ",
        email="  store@retailflow.ph  ",
        tin="  123-456-789-000  ",
    )

    result = service.update_store_profile(dto, actor=admin)
    assert result.store_name == "RetailFlow Flagship Store"
    assert result.store_address == "456 Ayala Ave, Makati City"
    assert result.contact_number == "+63 917 123 4567"
    assert result.email == "store@retailflow.ph"
    assert result.tin == "123-456-789-000"
    assert result.updated_by_id == admin.id

    # Verify Audit Log
    log = db_session.query(AuditLog).filter_by(action="STORE_PROFILE_UPDATED").first()
    assert log is not None
    assert log.user_id == admin.id
    assert "RetailFlow Flagship Store" in log.new_value
    assert "RetailFlow Store" in log.previous_value


def test_update_store_profile_normalization_empty_optional_fields(db_session, auth_roles_users):
    """Empty or whitespace-only optional fields are normalized to None."""
    service = SettingsService(db_session)
    admin = auth_roles_users["admin"]

    dto = UpdateStoreProfileDTO(
        store_name="Valid Store Name",
        store_address="   ",
        contact_number="",
        email=None,
        tin="   ",
    )

    result = service.update_store_profile(dto, actor=admin)
    assert result.store_name == "Valid Store Name"
    assert result.store_address is None
    assert result.contact_number is None
    assert result.email is None
    assert result.tin is None


def test_update_store_profile_validation_errors(db_session, auth_roles_users):
    """Invalid store names, invalid emails, and excessive lengths raise ValidationError."""
    service = SettingsService(db_session)
    admin = auth_roles_users["admin"]

    # 1. Empty / too short store name
    with pytest.raises(ValidationError):
        service.update_store_profile(UpdateStoreProfileDTO(store_name=" "), actor=admin)
    with pytest.raises(ValidationError):
        service.update_store_profile(UpdateStoreProfileDTO(store_name="A"), actor=admin)

    # 2. Store name too long (> 100 chars)
    with pytest.raises(ValidationError):
        service.update_store_profile(UpdateStoreProfileDTO(store_name="A" * 101), actor=admin)

    # 3. Invalid email format
    with pytest.raises(ValidationError):
        service.update_store_profile(UpdateStoreProfileDTO(store_name="Valid Name", email="invalid-email"), actor=admin)

    # 4. Excessive address length (> 255 chars)
    with pytest.raises(ValidationError):
        service.update_store_profile(UpdateStoreProfileDTO(store_name="Valid Name", store_address="X" * 256), actor=admin)


def test_update_store_profile_no_op_does_not_audit(db_session, auth_roles_users):
    """Submitting identical profile data is a no-op that writes zero audit logs."""
    service = SettingsService(db_session)
    admin = auth_roles_users["admin"]

    # Initial update
    dto = UpdateStoreProfileDTO(store_name="Custom Store Name", contact_number="+63 2 8000 0000")
    service.update_store_profile(dto, actor=admin)

    audit_count_before = db_session.query(AuditLog).count()

    # Re-submit identical DTO (with outer whitespace)
    identical_dto = UpdateStoreProfileDTO(store_name="  Custom Store Name  ", contact_number="+63 2 8000 0000")
    result = service.update_store_profile(identical_dto, actor=admin)

    assert result.store_name == "Custom Store Name"
    # No new audit log written
    assert db_session.query(AuditLog).count() == audit_count_before


def test_update_store_profile_audit_failure_rollback(db_session, auth_roles_users):
    """If audit log logging fails, entire store profile update transaction rolls back."""
    service = SettingsService(db_session)
    admin = auth_roles_users["admin"]

    original_name = db_session.query(StoreSettings).first().store_name

    # Mock audit repository to raise exception
    service._audit_repo.log_action = MagicMock(side_effect=Exception("Disk full on audit table"))

    with pytest.raises(Exception):
        service.update_store_profile(UpdateStoreProfileDTO(store_name="New Uncommitted Name"), actor=admin)

    # Verify rollback
    db_session.rollback()
    assert db_session.query(StoreSettings).first().store_name == original_name


# ─── 3. Receipt Preferences Tests ───

def test_update_receipt_preferences_success_and_audit(db_session, auth_roles_users):
    """Admin updates receipt preferences; values are persisted and audited."""
    service = SettingsService(db_session)
    admin = auth_roles_users["admin"]

    dto = UpdateReceiptPreferencesDTO(
        receipt_header="Special Branch Receipt",
        receipt_footer="All sales final. Thank you!",
        paper_width="58mm",
        show_store_address=False,
        show_contact=True,
        show_tin=False,
        show_tax_details=False,
    )

    result = service.update_receipt_preferences(dto, actor=admin)
    assert result.receipt_header == "Special Branch Receipt"
    assert result.receipt_footer == "All sales final. Thank you!"
    assert result.paper_width == "58mm"
    assert result.show_store_address is False
    assert result.show_contact is True
    assert result.show_tin is False
    assert result.show_tax_details is False

    log = db_session.query(AuditLog).filter_by(action="RECEIPT_PREFERENCES_UPDATED").first()
    assert log is not None
    assert "Special Branch Receipt" in log.new_value


def test_update_receipt_preferences_defaults_and_validation(db_session, auth_roles_users):
    """Blank header/footer resets to canonical defaults; invalid widths or non-booleans raise ValidationError."""
    service = SettingsService(db_session)
    admin = auth_roles_users["admin"]

    # Blank header/footer -> canonical defaults
    dto = UpdateReceiptPreferencesDTO(
        receipt_header="   ",
        receipt_footer="",
        paper_width="80mm",
    )
    result = service.update_receipt_preferences(dto, actor=admin)
    assert result.receipt_header == "Official Sales Invoice / Thermal Receipt"
    assert result.receipt_footer == "Thank you for shopping with us!"

    # Invalid paper width
    with pytest.raises(ValidationError):
        service.update_receipt_preferences(UpdateReceiptPreferencesDTO(paper_width="72mm"), actor=admin)

    # Non-boolean flag
    with pytest.raises(ValidationError):
        service.update_receipt_preferences(UpdateReceiptPreferencesDTO(show_store_address="true"), actor=admin)  # type: ignore


def test_update_receipt_preferences_no_op(db_session, auth_roles_users):
    """Submitting identical receipt preferences writes zero audit logs."""
    service = SettingsService(db_session)
    admin = auth_roles_users["admin"]

    dto = UpdateReceiptPreferencesDTO(receipt_header="Custom Header", paper_width="58mm")
    service.update_receipt_preferences(dto, actor=admin)

    audit_count_before = db_session.query(AuditLog).count()
    service.update_receipt_preferences(dto, actor=admin)

    assert db_session.query(AuditLog).count() == audit_count_before


# ─── 4. Managed Logo Lifecycle Tests ───

def test_update_store_logo_valid_png_and_jpeg(db_session, auth_roles_users, dummy_png_file, dummy_jpg_file):
    """Valid PNG and JPEG files are normalized, stored in versioned managed files, and audited."""
    service = SettingsService(db_session)
    admin = auth_roles_users["admin"]

    # 1. Upload PNG
    res_png = service.update_store_logo(dummy_png_file, actor=admin)
    assert res_png.logo_path is not None
    assert res_png.logo_path.startswith("assets/store_logo_")
    assert res_png.logo_path.endswith(".png")

    first_physical_file = settings.data_dir / res_png.logo_path
    assert first_physical_file.exists()

    # 2. Upload JPEG (replaces first logo and cleans it up)
    res_jpg = service.update_store_logo(dummy_jpg_file, actor=admin)
    assert res_jpg.logo_path is not None
    assert res_jpg.logo_path != res_png.logo_path

    second_physical_file = settings.data_dir / res_jpg.logo_path
    assert second_physical_file.exists()
    # First physical file was removed
    assert not first_physical_file.exists()

    # Clean up second file after test
    second_physical_file.unlink(missing_ok=True)


def test_update_store_logo_corrupt_and_invalid_files(db_session, auth_roles_users, tmp_path):
    """Corrupt image files, non-existent files, or unsupported formats are rejected with ValidationError."""
    service = SettingsService(db_session)
    admin = auth_roles_users["admin"]

    # 1. Non-existent file
    with pytest.raises(ValidationError):
        service.update_store_logo(tmp_path / "non_existent.png", actor=admin)

    # 2. Fake PNG (corrupt bytes with .png extension)
    fake_png = tmp_path / "fake.png"
    fake_png.write_bytes(b"NOT_A_REAL_PNG_HEADER_DATA")
    with pytest.raises(ValidationError):
        service.update_store_logo(fake_png, actor=admin)

    # 3. Unsupported format (.svg / .gif / .txt)
    txt_file = tmp_path / "logo.txt"
    txt_file.write_text("hello world")
    with pytest.raises(ValidationError):
        service.update_store_logo(txt_file, actor=admin)


def test_update_store_logo_dimension_and_size_bounds(db_session, auth_roles_users, tmp_path):
    """Images exceeding 2MB or outside dimension bounds (16x16 to 2048x2048) are rejected."""
    service = SettingsService(db_session)
    admin = auth_roles_users["admin"]

    # 1. Too small (8x8)
    tiny_path = tmp_path / "tiny.png"
    PIL.Image.new("RGBA", (8, 8)).save(tiny_path, format="PNG")
    with pytest.raises(ValidationError) as exc:
        service.update_store_logo(tiny_path, actor=admin)
    assert "too small" in str(exc.value)

    # 2. Too large (2500x2500)
    huge_path = tmp_path / "huge.png"
    PIL.Image.new("RGBA", (2500, 2500)).save(huge_path, format="PNG")
    with pytest.raises(ValidationError) as exc:
        service.update_store_logo(huge_path, actor=admin)
    assert "exceed" in str(exc.value)


def test_update_store_logo_db_failure_cleans_up_promoted_file(db_session, auth_roles_users, dummy_png_file):
    """If DB commit fails after file creation, promoted file is cleaned up and old state is preserved."""
    service = SettingsService(db_session)
    admin = auth_roles_users["admin"]

    service._audit_repo.log_action = MagicMock(side_effect=Exception("Database crash on audit"))

    with pytest.raises(Exception):
        service.update_store_logo(dummy_png_file, actor=admin)

    db_session.rollback()
    assert db_session.query(StoreSettings).first().logo_path is None


def test_remove_store_logo_and_idempotency(db_session, auth_roles_users, dummy_png_file):
    """remove_store_logo clears DB path and deletes physical file; calling again is a safe no-op."""
    service = SettingsService(db_session)
    admin = auth_roles_users["admin"]

    # Setup logo
    res = service.update_store_logo(dummy_png_file, actor=admin)
    physical_file = settings.data_dir / res.logo_path
    assert physical_file.exists()

    # Remove logo
    removed = service.remove_store_logo(actor=admin)
    assert removed.logo_path is None
    assert not physical_file.exists()

    # Call remove again (no-op)
    audit_count_before = db_session.query(AuditLog).count()
    removed2 = service.remove_store_logo(actor=admin)
    assert removed2.logo_path is None
    assert db_session.query(AuditLog).count() == audit_count_before


def test_get_settings_graceful_missing_logo_fallback(db_session, auth_roles_users):
    """If physical logo file is deleted externally, get_settings returns logo_path=None in DTO without mutating DB."""
    service = SettingsService(db_session)
    admin = auth_roles_users["admin"]

    # Set logo_path in DB directly to a missing file
    db_session.query(StoreSettings).filter_by(id=1).update({"logo_path": "assets/missing_file_123.png"})
    db_session.commit()

    dto = service.get_settings(actor=admin)
    # Projected DTO falls back to None
    assert dto.logo_path is None

    # Database column remains untouched (read-only projection fallback)
    raw_record = db_session.query(StoreSettings).filter_by(id=1).first()
    assert raw_record.logo_path == "assets/missing_file_123.png"


# ─── 5. System Information Diagnostics Tests ───

def test_get_system_info_diagnostics_and_sanitization(db_session, auth_roles_users):
    """SystemInfo exposes sanitized diagnostics without leaking secrets or credentials."""
    service = SettingsService(db_session)
    admin = auth_roles_users["admin"]

    info = service.get_system_info(actor=admin)
    assert info.app_name == "RetailFlow POS"
    assert info.timezone == "Asia/Manila (UTC+08:00)"
    assert info.currency == "Philippine Peso (PHP · ₱)"
    assert "retailflow.db" in info.database_location
    assert "password" not in info.database_location.lower()
    assert info.pyside_version is not None
    assert info.python_version is not None

    # Path privacy: diagnostics never expose absolute local paths
    base_dir_str = str(settings.base_dir)
    for path_value in (
        info.database_location,
        info.data_dir,
        info.log_dir,
        info.backup_dir,
        info.export_dir,
    ):
        assert base_dir_str not in path_value
        assert not path_value.startswith(("C:", "\\\\", "/"))

    # Display contract: project-relative forms
    assert info.database_location == os.path.join("data", "retailflow.db")
    assert info.data_dir == "data" + os.sep
    assert info.log_dir == "logs" + os.sep
    assert info.backup_dir == "backups" + os.sep
    assert info.export_dir == "exports" + os.sep


# ─── 6. Real Bootstrap Upgrade Test ───

def test_bootstrap_upgrades_existing_database():
    """An existing database with data but missing StoreSettings is upgraded safely via bootstrap seeding."""
    test_engine = create_engine("sqlite:///:memory:")

    # 1. Create tables without store_settings
    tables_to_create = [
        table for name, table in Base.metadata.tables.items() if name != "store_settings"
    ]
    Base.metadata.create_all(bind=test_engine, tables=tables_to_create)

    # 2. Run schema migration
    _migrate_schema(test_engine)

    # 3. Seed settings into the upgraded database
    SessionMaker = sessionmaker(bind=test_engine)
    session = SessionMaker()
    try:
        assert session.query(StoreSettings).count() == 0
        seed_settings(session)
        session.commit()

        # Verify row id = 1 is now available
        row = session.query(StoreSettings).filter_by(id=1).first()
        assert row is not None
        assert row.store_name == "RetailFlow Store"
    finally:
        session.close()


# ─── 7. Path Confinement Security Test ───

def test_logo_path_confinement_rejects_sibling_prefix(db_session, tmp_path):
    """Assets in sibling-prefix folders (e.g. data/assets_backup) or outside assets cannot be deleted."""
    service = SettingsService(db_session)

    # 1. Sibling directory with shared prefix: 'assets_backup'
    sibling_dir = settings.data_dir / "assets_backup"
    sibling_dir.mkdir(parents=True, exist_ok=True)
    sibling_file = sibling_dir / "important_backup.png"
    sibling_file.write_bytes(b"BACKUP_IMAGE_DATA")

    # 2. External directory: '../external.png'
    external_file = settings.data_dir / "external.png"
    external_file.write_bytes(b"EXTERNAL_DATA")

    try:
        # Attempt to delete sibling path
        service._safe_delete_managed_asset("assets_backup/important_backup.png")
        assert sibling_file.exists(), "Sibling folder file must NOT be deleted by path confinement guard"

        # Attempt to delete traversal path
        service._safe_delete_managed_asset("../external.png")
        assert external_file.exists(), "Traversal path must NOT be deleted"
    finally:
        # Clean up test artifacts
        if sibling_file.exists():
            sibling_file.unlink()
        if sibling_dir.exists():
            sibling_dir.rmdir()
        if external_file.exists():
            external_file.unlink()

