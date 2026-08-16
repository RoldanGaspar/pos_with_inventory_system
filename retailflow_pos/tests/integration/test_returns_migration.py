"""
RetailFlow POS - Returns Schema Migration & Database Bootstrap Tests (Phase 2B)
Verifies fresh database table creation and idempotent schema migration for existing databases.
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect

from infrastructure.database.models.base import Base
from infrastructure.database.session import _import_models, _migrate_schema, init_database


def test_fresh_database_bootstrap_creates_returns_tables():
    """A fresh database initialization creates sales_returns and sales_return_items tables."""
    test_engine = create_engine("sqlite:///:memory:")
    _import_models()
    Base.metadata.create_all(bind=test_engine)

    inspector = inspect(test_engine)
    tables = inspector.get_table_names()

    assert "sales_returns" in tables
    assert "sales_return_items" in tables

    # Verify column presence
    ret_cols = [c["name"] for c in inspector.get_columns("sales_returns")]
    assert "return_number" in ret_cols
    assert "sale_id" in ret_cols
    assert "cashier_id" in ret_cols
    assert "approved_by_id" in ret_cols
    assert "return_date" in ret_cols
    assert "subtotal_returned" in ret_cols
    assert "discount_reversal" in ret_cols
    assert "taxable_reversal" in ret_cols
    assert "tax_reversal" in ret_cols
    assert "total_refund_amount" in ret_cols
    assert "cogs_reversal_total" in ret_cols
    assert "writeoff_cost_total" in ret_cols
    assert "original_payment_method_snapshot" in ret_cols

    item_cols = [c["name"] for c in inspector.get_columns("sales_return_items")]
    assert "sales_return_id" in item_cols
    assert "sale_line_item_id" in item_cols
    assert "product_id" in item_cols
    assert "quantity" in item_cols
    assert "unit_price_snapshot" in item_cols
    assert "unit_cost_snapshot" in item_cols
    assert "cogs_reversal" in item_cols
    assert "writeoff_cost" in item_cols
    assert "disposition" in item_cols


def test_idempotent_schema_migration_on_existing_database():
    """Running _migrate_schema multiple times is safe and causes no duplicate errors."""
    test_engine = create_engine("sqlite:///:memory:")
    _import_models()
    Base.metadata.create_all(bind=test_engine)

    # First migration run
    _migrate_schema(test_engine)

    # Second migration run (idempotent)
    _migrate_schema(test_engine)

    inspector = inspect(test_engine)
    tables = inspector.get_table_names()
    assert "sales_returns" in tables
    assert "sales_return_items" in tables
