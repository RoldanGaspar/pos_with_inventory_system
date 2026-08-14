"""
RetailFlow POS - Application Bootstrap
Initializes all subsystems before the UI starts.
"""

import logging
import sys

from app.config import settings
from infrastructure.database.session import dispose_engine, init_database
from infrastructure.logging.setup import setup_logging

logger = logging.getLogger("retailflow")


def bootstrap() -> None:
    """Initialize all application subsystems.

    Order matters:
    1. Logging (so everything else can be logged)
    2. Configuration validation
    3. Database (tables created if needed)
    4. Seed auth data if first run
    """
    try:
        # 1. Setup logging first
        setup_logging()
        logger.info("=" * 60)
        logger.info(f"{settings.app_name} v{settings.app_version} starting...")
        logger.info(f"Environment: {settings.app_env}")
        logger.info(f"Database type: {settings.database_type}")

        # 2. Ensure required directories exist
        _ensure_directories()

        # 3. Initialize database (creates tables)
        init_database()

        # 4. Auto-seed auth data if first run
        _seed_if_needed()

        logger.info("Application bootstrapped successfully.")

    except Exception as e:
        logger.critical(f"Bootstrap failed: {e}", exc_info=True)
        sys.exit(1)


def shutdown() -> None:
    """Cleanly shut down all subsystems."""
    logger.info(f"{settings.app_name} shutting down...")
    try:
        dispose_engine()
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    logger.info("Shutdown complete.")


def _ensure_directories() -> None:
    """Create all required directories."""
    dirs = [
        settings.data_dir,
        settings.log_dir,
        settings.backup_dir,
        settings.export_dir,
        settings.base_dir / "reports",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def _seed_if_needed() -> None:
    """Seed default roles, permissions, users, and catalog on first run."""
    from infrastructure.database.seeders.auth_seeder import seed_auth
    from infrastructure.database.seeders.customer_seeder import seed_customers
    from infrastructure.database.seeders.product_seeder import seed_products
    from infrastructure.database.seeders.supplier_seeder import seed_suppliers
    from infrastructure.database.session import create_session

    session = create_session()
    try:
        seed_auth(session)
        if settings.is_development:
            seed_products(session)
            seed_customers(session)
            seed_suppliers(session)
        else:
            logger.info("Skipping demo product catalog seeding (non-development environment).")
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Seeding failed: {e}")
    finally:
        session.close()
