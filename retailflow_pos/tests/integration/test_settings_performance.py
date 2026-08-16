"""
RetailFlow POS - Settings Performance Smoke Tests
Development benchmarks for Settings read/write latencies.
"""

import time
from decimal import Decimal
from pathlib import Path

import PIL.Image
import pytest

from application.dto.settings_dto import UpdateReceiptPreferencesDTO, UpdateStoreProfileDTO
from application.services.settings_service import SettingsService
from infrastructure.database.models.auth import Permission, Role, User
from infrastructure.database.seeders.settings_seeder import seed_settings


def test_settings_performance_smoke(db_session, tmp_path):
    """Measures execution latency for core Settings service workflows."""
    p_edit = Permission(name="Edit", code="edit_settings", module="settings")
    p_view = Permission(name="View", code="view_settings", module="settings")
    role_admin = Role(name="Admin", code="admin", permissions=[p_edit, p_view])
    admin = User(username="perf_admin", email="perf@test.ph", password_hash="h", full_name="Perf Admin", roles=[role_admin])
    db_session.add_all([p_edit, p_view, role_admin, admin])
    db_session.commit()

    seed_settings(db_session)
    db_session.commit()

    service = SettingsService(db_session)

    # 1. get_settings() latency
    t0 = time.perf_counter()
    for _ in range(20):
        s = service.get_settings(actor=admin)
    t_get_settings_avg_ms = ((time.perf_counter() - t0) / 20) * 1000

    # 2. get_system_info() latency
    t0 = time.perf_counter()
    for _ in range(20):
        info = service.get_system_info(actor=admin)
    t_get_info_avg_ms = ((time.perf_counter() - t0) / 20) * 1000

    # 3. update_store_profile() latency
    t0 = time.perf_counter()
    service.update_store_profile(UpdateStoreProfileDTO(store_name="Perf Store Alpha"), actor=admin)
    t_update_profile_ms = (time.perf_counter() - t0) * 1000

    # 4. update_receipt_preferences() latency
    t0 = time.perf_counter()
    service.update_receipt_preferences(UpdateReceiptPreferencesDTO(receipt_header="Perf Header"), actor=admin)
    t_update_receipt_ms = (time.perf_counter() - t0) * 1000

    # 5. update_store_logo() latency (Pillow decode + normalize + disk write + DB commit + audit)
    sample_png = tmp_path / "perf_logo.png"
    PIL.Image.new("RGBA", (150, 75), color=(200, 50, 50, 255)).save(sample_png, format="PNG")
    t0 = time.perf_counter()
    service.update_store_logo(sample_png, actor=admin)
    t_update_logo_ms = (time.perf_counter() - t0) * 1000

    print(f"\n[SETTINGS BENCHMARKS] get_settings: {t_get_settings_avg_ms:.2f}ms | get_system_info: {t_get_info_avg_ms:.2f}ms | update_profile: {t_update_profile_ms:.2f}ms | update_receipt: {t_update_receipt_ms:.2f}ms | update_logo: {t_update_logo_ms:.2f}ms")

    assert t_get_settings_avg_ms < 50.0
    assert t_get_info_avg_ms < 50.0
    assert t_update_profile_ms < 100.0
    assert t_update_receipt_ms < 100.0
    assert t_update_logo_ms < 250.0
