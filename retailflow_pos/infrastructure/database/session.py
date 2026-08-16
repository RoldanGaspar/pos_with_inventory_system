"""
RetailFlow POS - Database Session Management
SQLAlchemy engine and session factory supporting SQLite and PostgreSQL.
"""

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from app.config import settings
from infrastructure.logging.setup import get_logger

logger = get_logger("database")

# SQLAlchemy declarative base for all ORM models
Base = declarative_base()

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    """Get or create the SQLAlchemy engine. Thread-safe singleton."""
    global _engine
    if _engine is None:
        db_url = settings.database_url
        logger.info(f"Creating database engine: type={settings.database_type}")

        if settings.database_type == "sqlite":
            _engine = create_engine(
                db_url,
                echo=False,
                connect_args={"check_same_thread": False},
            )
        else:
            _engine = create_engine(
                db_url,
                echo=False,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
            )

        logger.info("Database engine created successfully")
    return _engine


def get_session_factory() -> sessionmaker:
    """Get or create the session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _SessionLocal


def create_session() -> Session:
    """Create a new SQLAlchemy session."""
    return get_session_factory()()


def init_database() -> None:
    """Initialize the database: create engine and all tables."""
    logger.info("Initializing database...")

    # Ensure data directory exists
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    # Import all models so they register with Base.metadata
    _import_models()

    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    # Run safe schema migrations for existing databases
    _migrate_schema(engine)

    logger.info("Database initialized: all tables created and migrations verified")


def _import_models() -> None:
    """Import all model modules so they are registered on Base.metadata."""
    # Authentication models
    from infrastructure.database.models.auth import (
        User,
        Role,
        Permission,
        UserSession,
        LoginAttempt,
        PasswordHistory,
        AuditLog,
    )  # noqa: F401

    # Product & catalog models
    from infrastructure.database.models.product import (
        Product,
        Category,
        Brand,
        Unit,
        ProductBarcode,
    )  # noqa: F401
    from infrastructure.database.models.customer import Customer  # noqa: F401
    from infrastructure.database.models.expense import Expense  # noqa: F401
    from infrastructure.database.models.inventory import Inventory  # noqa: F401
    from infrastructure.database.models.purchasing import PurchaseOrder, PurchaseOrderItem  # noqa: F401
    from infrastructure.database.models.returns import SalesReturn, SalesReturnItem  # noqa: F401
    from infrastructure.database.models.sales import Sale, SaleLineItem, Payment  # noqa: F401
    from infrastructure.database.models.settings import StoreSettings  # noqa: F401
    from infrastructure.database.models.supplier import Supplier  # noqa: F401


def _migrate_schema(engine: Engine) -> None:
    """Apply safe schema migrations/upgrades for existing databases."""
    from sqlalchemy import inspect, text
    from infrastructure.database.models.returns import SalesReturn, SalesReturnItem
    from infrastructure.database.models.settings import StoreSettings

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    # 1. Backfill 'unit_cost' on sale_line_items if missing
    if "sale_line_items" in existing_tables:
        columns = [col["name"] for col in inspector.get_columns("sale_line_items")]
        if "unit_cost" not in columns:
            logger.info("Migrating schema: adding 'unit_cost' column to 'sale_line_items' table...")
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE sale_line_items ADD COLUMN unit_cost NUMERIC(12, 2) DEFAULT 0.00 NOT NULL")
                )
                conn.execute(
                    text(
                        """
                        UPDATE sale_line_items
                        SET unit_cost = (
                            SELECT COALESCE(products.cost_price, 0.00)
                            FROM products
                            WHERE products.id = sale_line_items.product_id
                        )
                        WHERE unit_cost = 0.00 OR unit_cost IS NULL
                        """
                    )
                )
            logger.info("Schema migration complete: 'unit_cost' column added and backfilled from product catalog.")

    # 2. Ensure sales_returns and sales_return_items tables exist on pre-existing databases
    if "sales_returns" not in existing_tables:
        logger.info("Migrating schema: creating 'sales_returns' table...")
        SalesReturn.__table__.create(bind=engine, checkfirst=True)
    else:
        columns = [col["name"] for col in inspector.get_columns("sales_returns")]
        if "reason_code" not in columns:
            logger.info("Migrating schema: adding 'reason_code' and 'reason_notes' columns to 'sales_returns'...")
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE sales_returns ADD COLUMN reason_code VARCHAR(50) DEFAULT 'other' NOT NULL")
                )
                conn.execute(
                    text("ALTER TABLE sales_returns ADD COLUMN reason_notes VARCHAR(255)")
                )
        if "idempotency_key" not in columns:
            logger.info("Migrating schema: adding 'idempotency_key' column to 'sales_returns'...")
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE sales_returns ADD COLUMN idempotency_key VARCHAR(64)")
                )

    if "sales_return_items" not in existing_tables:
        logger.info("Migrating schema: creating 'sales_return_items' table...")
        SalesReturnItem.__table__.create(bind=engine, checkfirst=True)

    # 3. Ensure store_settings table exists on pre-existing databases
    if "store_settings" not in existing_tables:
        logger.info("Migrating schema: creating 'store_settings' table...")
        StoreSettings.__table__.create(bind=engine, checkfirst=True)


def dispose_engine() -> None:
    """Dispose of the SQLAlchemy engine connection pool."""
    global _engine, _SessionLocal
    if _engine is not None:
        logger.info("Disposing database engine")
        _engine.dispose()
        _engine = None
        _SessionLocal = None
