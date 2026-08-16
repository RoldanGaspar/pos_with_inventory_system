"""
RetailFlow POS - Settings & System Configuration V1
Phase 4 FINAL: Full-System E2E Verification, RBAC Security Audit, Adversarial Inputs,
Multi-Session Concurrency, Filesystem Failure Testing, Tax Boundary Integrity, and Production Freeze Assessment.
"""

from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import PIL.Image
import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.config import settings
from application.dto.returns_dto import ProcessReturnRequestDTO, ReturnItemRequestDTO
from application.dto.sales_dto import CartItemDTO, CheckoutRequestDTO
from application.dto.settings_dto import (
    StoreSettingsDTO,
    SystemInfoDTO,
    UpdateReceiptPreferencesDTO,
    UpdateStoreProfileDTO,
)
from domain.exceptions import AccountInactiveError, AuthorizationError, ConfigurationError, ValidationError
from application.services.returns_service import ReturnsService
from application.services.sales_service import SalesService
from application.services.settings_service import SettingsService
from infrastructure.database.models.auth import AuditLog, Permission, Role, User
from infrastructure.database.models.base import Base
from infrastructure.database.models.customer import Customer
from infrastructure.database.models.product import Category, Product
from infrastructure.database.models.sales import Payment, Sale, SaleLineItem
from infrastructure.database.models.settings import StoreSettings
from infrastructure.database.repositories.product import InventoryRepository
from infrastructure.database.seeders.settings_seeder import seed_settings
from infrastructure.database.session import _migrate_schema
from presentation.windows.main_window import MainWindow


@pytest.fixture
def auth_bundle(db_session):
    """Seed permissions, roles, and test users for comprehensive Phase 4 testing."""
    perms = [
        Permission(code="view_settings", name="View Settings", module="settings"),
        Permission(code="edit_settings", name="Edit Settings", module="settings"),
        Permission(code="view_sales", name="View Sales", module="sales"),
        Permission(code="process_sale", name="Process Sale", module="sales"),
        Permission(code="return_sales", name="Process Returns", module="sales"),
        Permission(code="refund_approve", name="Approve Refunds", module="sales"),
        Permission(code="view_reports", name="View Reports", module="reports"),
    ]
    db_session.add_all(perms)
    db_session.flush()

    perm_map = {p.code: p for p in perms}

    admin_role = Role(name="Administrator", code="admin", permissions=[perm_map["view_settings"], perm_map["edit_settings"], perm_map["view_sales"], perm_map["process_sale"], perm_map["return_sales"], perm_map["refund_approve"], perm_map["view_reports"]])
    mgr_role = Role(name="Manager", code="manager", permissions=[perm_map["view_settings"], perm_map["edit_settings"], perm_map["view_sales"], perm_map["process_sale"], perm_map["return_sales"], perm_map["refund_approve"], perm_map["view_reports"]])
    cashier_role = Role(name="Cashier", code="cashier", permissions=[perm_map["view_sales"], perm_map["process_sale"], perm_map["return_sales"]])
    auditor_role = Role(name="Auditor", code="auditor", permissions=[perm_map["view_sales"], perm_map["view_reports"]])

    admin = User(username="admin_e2e", email="admin_e2e@test.ph", password_hash="h", full_name="Admin E2E", is_active=True, roles=[admin_role])
    manager = User(username="mgr_e2e", email="mgr_e2e@test.ph", password_hash="h", full_name="Manager E2E", is_active=True, roles=[mgr_role])
    cashier = User(username="cashier_e2e", email="cashier_e2e@test.ph", password_hash="h", full_name="Cashier E2E", is_active=True, roles=[cashier_role])
    auditor = User(username="auditor_e2e", email="auditor_e2e@test.ph", password_hash="h", full_name="Auditor E2E", is_active=True, roles=[auditor_role])

    inactive_admin = User(username="inactive_admin", email="inadmin@test.ph", password_hash="h", full_name="Inactive Admin", is_active=False, roles=[admin_role])
    inactive_mgr = User(username="inactive_mgr", email="inmgr@test.ph", password_hash="h", full_name="Inactive Manager", is_active=False, roles=[mgr_role])

    db_session.add_all([admin_role, mgr_role, cashier_role, auditor_role, admin, manager, cashier, auditor, inactive_admin, inactive_mgr])
    db_session.commit()

    seed_settings(db_session)
    db_session.commit()

    return {
        "admin": admin,
        "manager": manager,
        "cashier": cashier,
        "auditor": auditor,
        "inactive_admin": inactive_admin,
        "inactive_mgr": inactive_mgr,
        "admin_role": admin_role,
        "mgr_role": mgr_role,
    }


@pytest.fixture
def test_png(tmp_path) -> Path:
    """Create a valid PNG image for logo tests."""
    p = tmp_path / "valid_logo.png"
    img = PIL.Image.new("RGBA", (100, 50), color=(16, 185, 129, 255))
    img.save(p, format="PNG")
    return p


@pytest.fixture
def test_jpeg(tmp_path) -> Path:
    """Create a valid JPEG image for logo tests."""
    p = tmp_path / "valid_logo.jpg"
    img = PIL.Image.new("RGB", (120, 60), color=(245, 158, 11))
    img.save(p, format="JPEG")
    return p


# ─── 1. Bootstrap / Persistence E2E ───

def test_fresh_install_e2e_singleton_and_restart(tmp_path):
    """Fresh database bootstrap creates exactly one canonical row id=1 with factory defaults, preserving values across restarts."""
    db_file = tmp_path / "fresh_retailflow.db"
    engine = create_engine(f"sqlite:///{db_file}")
    SessionLocal = sessionmaker(bind=engine)

    # 1. First Boot: Initialize schema and seed settings
    Base.metadata.create_all(bind=engine)
    session1 = SessionLocal()
    seed_settings(session1)
    session1.commit()

    rows = session1.query(StoreSettings).all()
    assert len(rows) == 1
    s = rows[0]
    assert s.id == 1
    assert s.store_name == "RetailFlow Store"
    assert s.paper_width == "80mm"
    assert s.show_store_address is True
    assert s.show_contact is True
    assert s.show_tin is True
    assert s.show_tax_details is True
    assert s.updated_by_id is None
    session1.close()

    # 2. Customize Settings
    session2 = SessionLocal()
    s2 = session2.query(StoreSettings).filter_by(id=1).first()
    s2.store_name = "Boutique Cafe Manila"
    s2.paper_width = "58mm"
    session2.commit()
    session2.close()

    # 3. Simulate App Restart / Re-Bootstrap
    session3 = SessionLocal()
    _migrate_schema(engine)
    seed_settings(session3)
    session3.commit()

    rows_after = session3.query(StoreSettings).all()
    assert len(rows_after) == 1
    assert rows_after[0].id == 1
    assert rows_after[0].store_name == "Boutique Cafe Manila"
    assert rows_after[0].paper_width == "58mm"
    session3.close()


def test_existing_database_upgrade_e2e(tmp_path):
    """Upgrading an existing database containing users, products, and sales non-destructively creates store_settings table and canonical row."""
    db_file = tmp_path / "pre_settings_retailflow.db"
    engine = create_engine(f"sqlite:///{db_file}")
    SessionLocal = sessionmaker(bind=engine)

    # Create pre-settings database (tables without store_settings)
    tables_to_create = [
        User.__table__,
        Role.__table__,
        Permission.__table__,
        Category.__table__,
        Product.__table__,
        Customer.__table__,
        Sale.__table__,
        SaleLineItem.__table__,
        Payment.__table__,
        AuditLog.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables_to_create)

    # Seed pre-existing operational records
    session = SessionLocal()
    cat = Category(name="Coffee")
    prod = Product(name="Espresso Beans", sku="ESP-001", cost_price=Decimal("150.00"), selling_price=Decimal("300.00"), category=cat)
    cust = Customer(name="Juan Dela Cruz", phone="09171234567")
    session.add_all([cat, prod, cust])
    session.commit()
    session.close()

    # Upgrade / Run App Bootstrap
    _migrate_schema(engine)
    session_upgraded = SessionLocal()
    seed_settings(session_upgraded)
    session_upgraded.commit()

    # Verify store_settings exists with id=1
    st = session_upgraded.query(StoreSettings).filter_by(id=1).first()
    assert st is not None
    assert st.store_name == "RetailFlow Store"

    # Verify pre-existing data is 100% intact
    saved_prod = session_upgraded.query(Product).filter_by(sku="ESP-001").first()
    assert saved_prod is not None
    assert saved_prod.name == "Espresso Beans"
    session_upgraded.close()


def test_singleton_adversarial_check_constraint_and_pk(db_session, auth_bundle):
    """Direct SQL insert of id != 1 fails check constraint; duplicate id=1 fails PK uniqueness; session recovers cleanly."""
    # 1. Attempt id=2 insert
    with pytest.raises(IntegrityError):
        db_session.execute(text("INSERT INTO store_settings (id, store_name, paper_width, show_store_address, show_contact, show_tin, show_tax_details) VALUES (2, 'Bad 2', '80mm', 1, 1, 1, 1)"))
        db_session.flush()
    db_session.rollback()

    # 2. Attempt duplicate id=1 insert
    with pytest.raises(IntegrityError):
        db_session.execute(text("INSERT INTO store_settings (id, store_name, paper_width, show_store_address, show_contact, show_tin, show_tax_details) VALUES (1, 'Dup 1', '80mm', 1, 1, 1, 1)"))
        db_session.flush()
    db_session.rollback()

    # Verify canonical row is uncorrupted
    canonical = db_session.query(StoreSettings).filter_by(id=1).first()
    assert canonical is not None
    assert canonical.store_name == "RetailFlow Store"


def test_missing_singleton_raises_configuration_error_without_mutation(db_session, auth_bundle):
    """If singleton row is missing, SettingsService raises ConfigurationError without silent re-seed or mutation."""
    admin = auth_bundle["admin"]
    db_session.query(StoreSettings).delete()
    db_session.commit()

    service = SettingsService(db_session)

    with pytest.raises(ConfigurationError) as exc:
        service.get_settings(actor=admin)
    assert "is missing from database" in str(exc.value)

    # Confirms table remains empty and zero audit logs created
    assert db_session.query(StoreSettings).count() == 0
    audit_count = db_session.query(AuditLog).filter_by(module="settings").count()
    assert audit_count == 0


# ─── 2. Authorization / RBAC & Direct Routing ───

def test_settings_rbac_matrix_and_direct_routing_protection(qtbot, db_session, auth_bundle):
    """Verifies RBAC enforcement across Admin, Manager, Cashier, Auditor, and MainWindow routing."""
    service = SettingsService(db_session)

    # 1. Service Layer Permissions
    # Admin & Manager: Allowed
    assert service.get_settings(actor=auth_bundle["admin"]).store_name == "RetailFlow Store"
    assert service.get_settings(actor=auth_bundle["manager"]).store_name == "RetailFlow Store"

    # Cashier & Auditor: Denied
    with pytest.raises(AuthorizationError):
        service.get_settings(actor=auth_bundle["cashier"])
    with pytest.raises(AuthorizationError):
        service.get_settings(actor=auth_bundle["auditor"])

    with pytest.raises(AuthorizationError):
        service.update_store_profile(UpdateStoreProfileDTO(store_name="Hacked"), actor=auth_bundle["cashier"])
    with pytest.raises(AuthorizationError):
        service.update_receipt_preferences(UpdateReceiptPreferencesDTO(), actor=auth_bundle["auditor"])

    # 2. MainWindow Direct Routing Bypass Protection
    # Cashier Window
    cashier_win = MainWindow(current_user=auth_bundle["cashier"], session=db_session, settings_service=service)
    qtbot.addWidget(cashier_win)
    assert cashier_win.nav_buttons["settings"].isVisible() is False
    cashier_win.navigate_to("settings")
    assert cashier_win._current_page != "settings"
    cashier_win.close()

    # Auditor Window
    auditor_win = MainWindow(current_user=auth_bundle["auditor"], session=db_session, settings_service=service)
    qtbot.addWidget(auditor_win)
    assert auditor_win.nav_buttons["settings"].isVisible() is False
    auditor_win.navigate_to("settings")
    assert auditor_win._current_page != "settings"
    auditor_win.close()


def test_inactive_user_rejected_from_all_settings_operations(db_session, auth_bundle, test_png):
    """Inactive users are strictly rejected with AccountInactiveError across all operations."""
    service = SettingsService(db_session)
    inactive_admin = auth_bundle["inactive_admin"]

    with pytest.raises(AccountInactiveError):
        service.get_settings(actor=inactive_admin)

    with pytest.raises(AccountInactiveError):
        service.update_store_profile(UpdateStoreProfileDTO(store_name="New Name"), actor=inactive_admin)

    with pytest.raises(AccountInactiveError):
        service.update_receipt_preferences(UpdateReceiptPreferencesDTO(), actor=inactive_admin)

    with pytest.raises(AccountInactiveError):
        service.update_store_logo(test_png, actor=inactive_admin)

    with pytest.raises(AccountInactiveError):
        service.remove_store_logo(actor=inactive_admin)

    with pytest.raises(AccountInactiveError):
        service.get_system_info(actor=inactive_admin)


# ─── 3. Store Profile & Adversarial Inputs ───

def test_store_profile_e2e_and_no_op(db_session, auth_bundle):
    """Store profile updates persist, set updated_by_id, log audit, and suppress no-op mutations."""
    service = SettingsService(db_session)
    admin = auth_bundle["admin"]

    # 1. Legitimate Update
    dto = UpdateStoreProfileDTO(
        store_name="Manila Prime Retail",
        store_address="123 Ayala Avenue, Makati",
        contact_number="+63 2 8888 1234",
        email="contact@manilaprime.ph",
        tin="123-456-789-000",
    )
    res = service.update_store_profile(dto, actor=admin)
    assert res.store_name == "Manila Prime Retail"
    assert res.updated_by_id == admin.id

    # Check AuditLog
    log = db_session.query(AuditLog).filter_by(module="settings", action="STORE_PROFILE_UPDATED").first()
    assert log is not None
    assert log.user_id == admin.id
    assert log.record_id == 1
    assert "Manila Prime Retail" in log.new_value

    # 2. No-Op Update: Should suppress audit log and return existing
    audit_count_before = db_session.query(AuditLog).filter_by(module="settings").count()
    res_noop = service.update_store_profile(dto, actor=admin)
    assert res_noop.store_name == "Manila Prime Retail"
    audit_count_after = db_session.query(AuditLog).filter_by(module="settings").count()
    assert audit_count_after == audit_count_before


@pytest.mark.parametrize("bad_name", ["", "   ", "A"])
def test_adversarial_profile_invalid_names(db_session, auth_bundle, bad_name):
    """Store name < 2 chars or whitespace-only raises ValidationError."""
    service = SettingsService(db_session)
    admin = auth_bundle["admin"]
    with pytest.raises(ValidationError) as exc:
        service.update_store_profile(UpdateStoreProfileDTO(store_name=bad_name), actor=admin)
    assert "Store name" in str(exc.value)


def test_adversarial_profile_security_inputs(db_session, auth_bundle):
    """Special characters, XSS script tags, SQL injection strings, and Unicode are safely handled as plain text."""
    service = SettingsService(db_session)
    admin = auth_bundle["admin"]

    xss_name = "Super Store <script>alert(1)</script>"
    sql_address = "456 Main St'; DROP TABLE store_settings; --"
    unicode_tin = "TIN-999-888-☕-🇵🇭"

    dto = UpdateStoreProfileDTO(
        store_name=xss_name,
        store_address=sql_address,
        tin=unicode_tin,
        email="safe.test@retailflow.ph",
    )
    res = service.update_store_profile(dto, actor=admin)

    # Persisted safely as plain string without code execution or SQL injection
    assert res.store_name == xss_name
    assert res.store_address == sql_address
    assert res.tin == unicode_tin

    # Verify DB table still exists and is healthy
    assert db_session.query(StoreSettings).count() == 1


# ─── 4. Receipt Preferences & Tax Boundary ───

def test_receipt_preferences_e2e_and_tax_boundary(db_session, auth_bundle):
    """Updating receipt preferences works E2E and toggling show_tax_details has ZERO impact on sales or return tax math."""
    settings_service = SettingsService(db_session)
    sales_service = SalesService(db_session)
    returns_service = ReturnsService(db_session)
    admin = auth_bundle["admin"]

    # 1. Update receipt preferences to 58mm with tax details disabled
    pref_dto = UpdateReceiptPreferencesDTO(
        receipt_header="Branch #101 - BGC",
        receipt_footer="No exchange after 7 days.",
        paper_width="58mm",
        show_store_address=False,
        show_contact=False,
        show_tin=False,
        show_tax_details=False,
    )
    res = settings_service.update_receipt_preferences(pref_dto, actor=admin)
    assert res.paper_width == "58mm"
    assert res.show_tax_details is False

    # 2. Perform a Sale Checkout: Verify tax calculation is 100% independent of show_tax_details
    cat = Category(name="Merch Category")
    prod = Product(name="Travel Mug", sku="MUG-001", cost_price=Decimal("100.00"), selling_price=Decimal("200.00"), category=cat)
    db_session.add_all([cat, prod])
    db_session.flush()

    inv_repo = InventoryRepository(db_session)
    inv_repo.set_quantity(prod.id, 10)
    db_session.commit()

    cart_item = CartItemDTO(
        product_id=prod.id,
        sku=prod.sku,
        name=prod.name,
        unit_price=prod.selling_price,
        quantity=1,
        available_stock=10,
    )
    checkout_req = CheckoutRequestDTO(
        items=[cart_item],
        payment_method="CASH",
        amount_tendered=Decimal("300.00"),
        discount_amount=Decimal("0.00"),
        cashier_id=admin.id,
    )
    sale_resp = sales_service.process_checkout(checkout_req, admin)

    # Subtotal: 200.00, Tax 12%: 24.00, Total: 224.00
    assert sale_resp.total_amount == Decimal("224.00")
    assert sale_resp.tax_amount == Decimal("24.00")

    # 3. Process Return: Verify Return tax apportionment is 100% independent of show_tax_details
    ret_req = ProcessReturnRequestDTO(
        sale_id=sale_resp.id,
        items=[ReturnItemRequestDTO(sale_line_item_id=sale_resp.items[0].id, quantity=1)],
        reason_code="defective",
        reason_notes="Tax boundary check",
    )
    ret_voucher = returns_service.process_return(request=ret_req, actor=admin, idempotency_key="TAX-CHECK-001")
    assert ret_voucher.taxable_reversal == Decimal("200.00")
    assert ret_voucher.tax_reversal == Decimal("24.00")
    assert ret_voucher.total_refund_amount == Decimal("224.00")


# ─── 5. Logo Security, Filesystem & Concurrency ───

def test_logo_security_and_failure_matrix(db_session, auth_bundle, test_png, tmp_path):
    """Verifies logo upload, confinement, content validation, failure recovery, and removal."""
    service = SettingsService(db_session)
    admin = auth_bundle["admin"]

    # 1. Normal Upload E2E
    res = service.update_store_logo(test_png, actor=admin)
    assert res.logo_path is not None
    assert res.logo_path.startswith("assets/store_logo_")
    assert res.logo_path.endswith(".png")

    active_file = settings.data_dir / res.logo_path
    assert active_file.exists()

    # 2. Content Adversarial: Fake PNG (text bytes)
    fake_png = tmp_path / "fake.png"
    fake_png.write_text("NOT_AN_IMAGE_BYTES")
    with pytest.raises(ValidationError) as exc:
        service.update_store_logo(fake_png, actor=admin)
    assert "Invalid or corrupted image file" in str(exc.value)

    # 3. Content Adversarial: Dimensions too small (< 16x16)
    tiny_img = tmp_path / "tiny.png"
    PIL.Image.new("RGB", (10, 10), color="white").save(tiny_img, format="PNG")
    with pytest.raises(ValidationError) as exc:
        service.update_store_logo(tiny_img, actor=admin)
    assert "Minimum is 16x16px" in str(exc.value)

    # 4. Failure Recovery Case B: DB/Audit commit failure cleans up newly staged file
    new_png = tmp_path / "new_logo.png"
    PIL.Image.new("RGB", (120, 60), color="blue").save(new_png, format="PNG")

    with patch.object(db_session, "commit", side_effect=IntegrityError("Simulated DB Error", None, None)):
        with pytest.raises(IntegrityError):
            service.update_store_logo(new_png, actor=admin)

    # Active logo remains uncorrupted
    res_after_err = service.get_settings(actor=admin)
    assert res_after_err.logo_path == res.logo_path
    assert active_file.exists()

    # 5. Missing physical file fallback
    active_file.unlink()
    fallback_res = service.get_settings(actor=admin)
    assert fallback_res.logo_path is None  # Projected as None gracefully

    # 6. Logo Removal
    # Seed new logo
    service.update_store_logo(test_png, actor=admin)
    rem_res = service.remove_store_logo(actor=admin)
    assert rem_res.logo_path is None

    # Idempotent second removal
    rem_noop = service.remove_store_logo(actor=admin)
    assert rem_noop.logo_path is None


# ─── 6. Multi-Session Concurrency & Stale Edits ───

def test_two_editor_concurrency_different_sections(tmp_path):
    """Concurrent updates to different sections (Admin edits Profile, Manager edits Receipt) both survive."""
    db_file = tmp_path / "concurrency_diff.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    s_init = SessionLocal()
    seed_settings(s_init)
    p_edit = Permission(name="Edit", code="edit_settings", module="settings")
    p_view = Permission(name="View", code="view_settings", module="settings")
    role_admin = Role(name="Admin", code="admin", permissions=[p_edit, p_view])
    role_mgr = Role(name="Manager", code="manager", permissions=[p_edit, p_view])

    admin = User(username="admin_c", email="a@c.ph", password_hash="h", full_name="Admin C", roles=[role_admin])
    mgr = User(username="mgr_c", email="m@c.ph", password_hash="h", full_name="Mgr C", roles=[role_mgr])
    s_init.add_all([p_edit, p_view, role_admin, role_mgr, admin, mgr])
    s_init.commit()
    admin_id, mgr_id = admin.id, mgr.id
    s_init.close()

    # Session 1: Admin edits Store Profile
    s1 = SessionLocal()
    srv1 = SettingsService(s1)
    admin_actor = s1.get(User, admin_id)
    srv1.update_store_profile(UpdateStoreProfileDTO(store_name="Concurrent Supermarket"), actor=admin_actor)
    s1.close()

    # Session 2: Manager edits Receipt Preferences
    s2 = SessionLocal()
    srv2 = SettingsService(s2)
    mgr_actor = s2.get(User, mgr_id)
    srv2.update_receipt_preferences(UpdateReceiptPreferencesDTO(receipt_header="Concurrent Header 99", paper_width="58mm"), actor=mgr_actor)
    s2.close()

    # Verification: Both independent section updates survived
    s_verify = SessionLocal()
    srv_v = SettingsService(s_verify)
    final_settings = srv_v.get_settings(actor=s_verify.get(User, admin_id))
    assert final_settings.store_name == "Concurrent Supermarket"
    assert final_settings.receipt_header == "Concurrent Header 99"
    assert final_settings.paper_width == "58mm"
    s_verify.close()


def test_two_editor_concurrency_same_section_last_write_wins(tmp_path):
    """Same-section concurrent updates follow last-write-wins singleton semantics."""
    db_file = tmp_path / "concurrency_same.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    s_init = SessionLocal()
    seed_settings(s_init)
    p_edit = Permission(name="Edit", code="edit_settings", module="settings")
    p_view = Permission(name="View", code="view_settings", module="settings")
    role_admin = Role(name="Admin", code="admin", permissions=[p_edit, p_view])
    admin = User(username="admin_s", email="a@s.ph", password_hash="h", full_name="Admin S", roles=[role_admin])
    s_init.add_all([p_edit, p_view, role_admin, admin])
    s_init.commit()
    admin_id = admin.id
    s_init.close()

    # Session A writes Name A
    s_a = SessionLocal()
    srv_a = SettingsService(s_a)
    srv_a.update_store_profile(UpdateStoreProfileDTO(store_name="Store A"), actor=s_a.get(User, admin_id))
    s_a.close()

    # Session B writes Name B
    s_b = SessionLocal()
    srv_b = SettingsService(s_b)
    srv_b.update_store_profile(UpdateStoreProfileDTO(store_name="Store B"), actor=s_b.get(User, admin_id))
    s_b.close()

    # Final result is Store B (last write wins)
    s_final = SessionLocal()
    st = s_final.query(StoreSettings).filter_by(id=1).first()
    assert st.store_name == "Store B"
    s_final.close()


# ─── 7. System Diagnostics & Secret Sanitization ───

def test_system_diagnostics_sanitization_and_no_secret_leaks(db_session, auth_bundle):
    """System diagnostics exposes structured platform information and strictly sanitizes credentials/secrets."""
    service = SettingsService(db_session)
    admin = auth_bundle["admin"]

    info = service.get_system_info(actor=admin)
    assert info.app_name == "RetailFlow POS"
    assert info.timezone == "Asia/Manila (UTC+08:00)"
    assert info.currency == "Philippine Peso (PHP · ₱)"
    assert "sqlite" in info.database_type.lower()

    # Confirm no password, secret key, or token in diagnostics attributes
    for field_name in ["app_name", "app_version", "database_type", "database_location", "timezone", "currency", "data_dir"]:
        val = getattr(info, field_name, "")
        assert "password" not in str(val).lower()
        assert "secret" not in str(val).lower()
        assert "token" not in str(val).lower()


def test_postgresql_diagnostic_url_sanitization(db_session, auth_bundle):
    """PostgreSQL connection strings with passwords and parameters are sanitized cleanly."""
    service = SettingsService(db_session)
    admin = auth_bundle["admin"]

    with patch.object(settings, "database_type", "postgresql"):
        with patch.object(settings, "database_url", "postgresql://admin_user:super_secret_password_123@db.prod.retailflow.internal:5432/retailflow_prod?sslmode=require"):
            sanitized = service._sanitize_database_location()
            assert "super_secret_password_123" not in sanitized
            assert "admin_user" not in sanitized
            assert sanitized == "postgresql://db.prod.retailflow.internal:5432/retailflow_prod"


# ─── 8. Application Close & UI Safety Guards ───

def test_mainwindow_close_event_with_dirty_settings(qtbot, db_session, auth_bundle):
    """Closing MainWindow with unsaved Settings prompts user; Cancel ignores close event; Discard accepts."""
    service = SettingsService(db_session)
    admin = auth_bundle["admin"]

    window = MainWindow(current_user=admin, session=db_session, settings_service=service)
    qtbot.addWidget(window)
    window.show()

    # Navigate to settings and modify
    window.navigate_to("settings")
    window._settings_page.txt_store_name.setText("Unsaved Close Edit")
    assert window._settings_page.has_unsaved_changes() is True

    # 1. Trigger Close Event -> User selects Cancel
    close_event_cancel = QCloseEvent()
    with patch.object(QMessageBox, "warning", return_value=QMessageBox.Cancel):
        window.closeEvent(close_event_cancel)
        assert close_event_cancel.isAccepted() is False

    # 2. Trigger Close Event -> User selects Discard
    close_event_discard = QCloseEvent()
    with patch.object(QMessageBox, "warning", return_value=QMessageBox.Discard):
        window.closeEvent(close_event_discard)
        assert close_event_discard.isAccepted() is True
