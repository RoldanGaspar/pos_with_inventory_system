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

    logger.info("Database initialized: all tables created")


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
    from infrastructure.database.models.inventory import Inventory  # noqa: F401
    from infrastructure.database.models.sales import Sale, SaleLineItem, Payment  # noqa: F401


def dispose_engine() -> None:
    """Dispose of the SQLAlchemy engine connection pool."""
    global _engine, _SessionLocal
    if _engine is not None:
        logger.info("Disposing database engine")
        _engine.dispose()
        _engine = None
        _SessionLocal = None
