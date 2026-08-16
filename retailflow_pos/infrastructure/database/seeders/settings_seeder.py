"""
RetailFlow POS - Store Settings Seeder
Ensures canonical singleton configuration record (id = 1) exists on startup.
Idempotent: skips if row id=1 already exists without overwriting customized values.
"""

import logging
from sqlalchemy.orm import Session

from app.constants import ReceiptWidth
from infrastructure.database.models.settings import StoreSettings

logger = logging.getLogger("retailflow.database")


def seed_settings(session: Session) -> None:
    """Seed default store settings (id = 1) if not already present."""
    existing = session.query(StoreSettings).filter_by(id=1).first()
    if existing:
        logger.info("Store settings (id=1) already exist. Skipping seeder.")
        return

    logger.info("Seeding default store settings (id=1)...")
    default_settings = StoreSettings(
        id=1,
        store_name="RetailFlow Store",
        store_address=None,
        contact_number=None,
        email=None,
        tin=None,
        logo_path=None,
        receipt_header="Official Sales Invoice / Thermal Receipt",
        receipt_footer="Thank you for shopping with us!",
        paper_width=ReceiptWidth.MM_80.value,
        show_store_address=True,
        show_contact=True,
        show_tin=True,
        show_tax_details=True,
        updated_by_id=None,
    )
    session.add(default_settings)
    session.flush()
    logger.info("Default store settings seeded successfully.")
