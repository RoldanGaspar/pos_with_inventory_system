"""
RetailFlow POS - Historical COGS & Sale Cost Snapshot Tests
Verifies that SaleLineItem snapshots the authoritative product cost basis at checkout
and that historical COGS remains strictly immutable even if product costs change later.
"""

from decimal import Decimal
import pytest
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.dto.sales_dto import CartItemDTO, CheckoutRequestDTO
from application.services.sales_service import SalesService
from infrastructure.database.models.auth import Permission, Role, User
from infrastructure.database.models.inventory import Inventory
from infrastructure.database.models.product import Product
from infrastructure.database.models.sales import Sale, SaleLineItem
from infrastructure.database.session import Base, _migrate_schema


@pytest.fixture
def cogs_test_env(db_session):
    """Set up test user, products, and inventory for sales checkout."""
    # 1. User with permissions
    perm = db_session.query(Permission).filter(Permission.code == "process_sale").first()
    if not perm:
        perm = Permission(code="process_sale", name="Process Sale", module="sales")
        db_session.add(perm)
        db_session.flush()

    role = Role(name="Cashier Role", code="cashier_role", permissions=[perm])
    db_session.add(role)
    db_session.flush()

    user = User(username="cogs_cashier", password_hash="hash", full_name="COGS Cashier", roles=[role])
    db_session.add(user)
    db_session.flush()

    # 2. Product A (Cost: ₱50.00, Sell: ₱100.00, Stock: 20)
    prod_a = Product(
        sku="COGS-PROD-A",
        name="COGS Test Item Alpha",
        cost_price=Decimal("50.00"),
        selling_price=Decimal("100.00"),
        status="active",
    )
    db_session.add(prod_a)
    db_session.flush()

    inv_a = Inventory(product_id=prod_a.id, quantity_on_hand=20)
    db_session.add(inv_a)

    # 3. Product B (Cost: ₱20.00, Sell: ₱45.00, Stock: 50)
    prod_b = Product(
        sku="COGS-PROD-B",
        name="COGS Test Item Beta",
        cost_price=Decimal("20.00"),
        selling_price=Decimal("45.00"),
        status="active",
    )
    db_session.add(prod_b)
    db_session.flush()

    inv_b = Inventory(product_id=prod_b.id, quantity_on_hand=50)
    db_session.add(inv_b)

    db_session.commit()
    return user, prod_a, prod_b


def test_sales_checkout_snapshots_unit_cost(db_session, cogs_test_env):
    """Verify that completing a sale captures Product.cost_price into SaleLineItem.unit_cost."""
    user, prod_a, _ = cogs_test_env
    sales_service = SalesService(db_session)

    request = CheckoutRequestDTO(
        items=[
            CartItemDTO(
                product_id=prod_a.id,
                sku=prod_a.sku,
                name=prod_a.name,
                unit_price=prod_a.selling_price,
                quantity=2,
            )
        ],
        payment_method="CASH",
        amount_tendered=Decimal("250.00"),
    )

    response = sales_service.process_checkout(request, user)
    assert response is not None
    assert len(response.items) == 1
    assert response.items[0].unit_cost == Decimal("50.00")
    assert response.items[0].unit_price == Decimal("100.00")
    assert response.items[0].quantity == 2

    # Verify directly from DB
    sale_db = db_session.query(Sale).filter(Sale.transaction_number == response.transaction_number).first()
    assert sale_db is not None
    assert len(sale_db.items) == 1
    assert sale_db.items[0].unit_cost == Decimal("50.00")


def test_historical_cost_immutability_when_product_cost_changes(db_session, cogs_test_env):
    """
    CRITICAL TEST:
    1. Sell 2 units at cost ₱50.00 (COGS = ₱100.00).
    2. Later, supplier price increases Product.cost_price to ₱80.00.
    3. Historical SaleLineItem.unit_cost must strictly remain ₱50.00 (COGS = ₱100.00, NOT ₱160.00).
    """
    user, prod_a, _ = cogs_test_env
    sales_service = SalesService(db_session)

    # Initial checkout
    request = CheckoutRequestDTO(
        items=[
            CartItemDTO(
                product_id=prod_a.id,
                sku=prod_a.sku,
                name=prod_a.name,
                unit_price=prod_a.selling_price,
                quantity=2,
            )
        ],
        payment_method="CASH",
        amount_tendered=Decimal("250.00"),
    )
    response = sales_service.process_checkout(request, user)
    txn_number = response.transaction_number

    # Verify initial snapshot
    sale_db = db_session.query(Sale).filter(Sale.transaction_number == txn_number).first()
    assert sale_db.items[0].unit_cost == Decimal("50.00")
    initial_cogs = sum(item.quantity * item.unit_cost for item in sale_db.items)
    assert initial_cogs == Decimal("100.00")

    # Now simulate product cost price inflation in the catalog
    prod_a.cost_price = Decimal("80.00")
    prod_a.selling_price = Decimal("150.00")
    db_session.commit()
    db_session.expire_all()

    # Re-query the historical sale
    historical_sale = db_session.query(Sale).filter(Sale.transaction_number == txn_number).first()
    assert historical_sale.items[0].unit_cost == Decimal("50.00"), "Historical unit_cost MUST remain ₱50.00!"
    
    historical_cogs = sum(item.quantity * item.unit_cost for item in historical_sale.items)
    assert historical_cogs == Decimal("100.00"), "Historical COGS MUST remain ₱100.00 even after product cost inflation!"


def test_discounts_do_not_alter_cogs(db_session, cogs_test_env):
    """
    Verify that granting an order discount reduces Net Sales but does not alter COGS.
    Retail = ₱100, Discount = ₱20, Cost = ₱50 -> Net Sales = ₱80, COGS = ₱50, Gross Profit = ₱30.
    """
    user, prod_a, _ = cogs_test_env
    sales_service = SalesService(db_session)

    request = CheckoutRequestDTO(
        items=[
            CartItemDTO(
                product_id=prod_a.id,
                sku=prod_a.sku,
                name=prod_a.name,
                unit_price=Decimal("100.00"),
                quantity=1,
            )
        ],
        payment_method="CASH",
        amount_tendered=Decimal("100.00"),
        discount_amount=Decimal("20.00"),
    )
    response = sales_service.process_checkout(request, user)

    sale_db = db_session.query(Sale).filter(Sale.transaction_number == response.transaction_number).first()
    net_sales = sale_db.subtotal - sale_db.discount_amount
    cogs = sale_db.items[0].quantity * sale_db.items[0].unit_cost
    gross_profit = net_sales - cogs

    assert net_sales == Decimal("80.00")
    assert cogs == Decimal("50.00")
    assert gross_profit == Decimal("30.00")


def test_cogs_query_contract_multiple_items_and_sales(db_session, cogs_test_env):
    """
    Verify COGS query across multiple sales:
    Sale A: 2x Prod A (qty 2 * ₱50 = ₱100)
    Sale B: 3x Prod B (qty 3 * ₱20 = ₱60)
    Total COGS = ₱160.00
    """
    user, prod_a, prod_b = cogs_test_env
    sales_service = SalesService(db_session)

    # Sale A
    sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[CartItemDTO(product_id=prod_a.id, sku=prod_a.sku, name=prod_a.name, unit_price=Decimal("100.00"), quantity=2)],
            payment_method="CASH",
            amount_tendered=Decimal("250.00"),
        ),
        user,
    )

    # Sale B
    sales_service.process_checkout(
        CheckoutRequestDTO(
            items=[CartItemDTO(product_id=prod_b.id, sku=prod_b.sku, name=prod_b.name, unit_price=Decimal("45.00"), quantity=3)],
            payment_method="CASH",
            amount_tendered=Decimal("200.00"),
        ),
        user,
    )

    # Calculate COGS across all COMPLETED sales
    total_cogs = (
        db_session.query(SaleLineItem.quantity, SaleLineItem.unit_cost)
        .join(Sale, Sale.id == SaleLineItem.sale_id)
        .filter(Sale.status == "COMPLETED")
        .all()
    )

    cogs_sum = sum((qty * cost for qty, cost in total_cogs), Decimal("0.00"))
    assert cogs_sum == Decimal("160.00")


def test_schema_migration_and_backfill_on_legacy_table():
    """
    Simulate an existing database without the 'unit_cost' column in 'sale_line_items'.
    Verify that _migrate_schema alters the table and backfills unit_cost from products.cost_price.
    """
    engine = create_engine("sqlite://", poolclass=StaticPool)
    
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku VARCHAR(50) NOT NULL,
                name VARCHAR(150) NOT NULL,
                cost_price NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
                selling_price NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
                tax_type VARCHAR(20) NOT NULL DEFAULT 'vat',
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                reorder_level INTEGER NOT NULL DEFAULT 0,
                has_batch_tracking BOOLEAN NOT NULL DEFAULT 0,
                has_expiry BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_number VARCHAR(50) NOT NULL UNIQUE,
                subtotal NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
                discount_amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
                tax_amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
                total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
                status VARCHAR(20) NOT NULL DEFAULT 'COMPLETED',
                payment_method VARCHAR(30) NOT NULL DEFAULT 'CASH',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # Legacy sale_line_items WITHOUT unit_cost
        conn.execute(text("""
            CREATE TABLE sale_line_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                product_name VARCHAR(150) NOT NULL,
                unit_price NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
                quantity INTEGER NOT NULL DEFAULT 1,
                subtotal NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Seed product & legacy sale
        conn.execute(text("INSERT INTO products (id, sku, name, cost_price, selling_price) VALUES (1, 'LEG-1', 'Legacy Product', 35.50, 70.00)"))
        conn.execute(text("INSERT INTO sales (id, transaction_number, subtotal, total_amount) VALUES (1, 'TXN-LEG-001', 140.00, 140.00)"))
        conn.execute(text("INSERT INTO sale_line_items (id, sale_id, product_id, product_name, unit_price, quantity, subtotal) VALUES (1, 1, 1, 'Legacy Product', 70.00, 2, 140.00)"))

    # Verify column does not exist initially
    inspector = inspect(engine)
    cols_before = [c["name"] for c in inspector.get_columns("sale_line_items")]
    assert "unit_cost" not in cols_before

    # Run migration
    _migrate_schema(engine)

    # Verify column was added
    inspector = inspect(engine)
    cols_after = [c["name"] for c in inspector.get_columns("sale_line_items")]
    assert "unit_cost" in cols_after

    # Verify data was backfilled from products.cost_price
    with engine.connect() as conn:
        row = conn.execute(text("SELECT unit_cost, quantity FROM sale_line_items WHERE id = 1")).first()
        assert row is not None
        assert Decimal(str(row[0])) == Decimal("35.50")
        assert row[1] == 2
