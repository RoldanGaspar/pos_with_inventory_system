"""
Foundation setup script - creates all __init__.py files and remaining base modules.
Run from the retailflow_pos directory: python scripts/_setup_foundation.py
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# Ensure we're in the right place for imports
sys.path.insert(0, str(BASE))


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  Created: {path.relative_to(BASE)}")


def create_init_files():
    """Create __init__.py in every package directory."""
    packages = [
        "app",
        "presentation",
        "presentation/windows",
        "presentation/dialogs",
        "presentation/widgets",
        "presentation/presenters",
        "presentation/viewmodels",
        "presentation/resources",
        "presentation/styles",
        "application",
        "application/services",
        "application/use_cases",
        "application/commands",
        "application/queries",
        "application/dto",
        "application/validators",
        "domain",
        "domain/entities",
        "domain/value_objects",
        "domain/enums",
        "domain/interfaces",
        "domain/services",
        "domain/rules",
        "domain/exceptions",
        "infrastructure",
        "infrastructure/database",
        "infrastructure/database/models",
        "infrastructure/database/repositories",
        "infrastructure/database/migrations",
        "infrastructure/database/seeders",
        "infrastructure/printing",
        "infrastructure/reports",
        "infrastructure/backups",
        "infrastructure/exports",
        "infrastructure/imports",
        "infrastructure/security",
        "infrastructure/logging",
        "shared",
        "shared/utils",
        "shared/events",
        "tests",
        "tests/unit",
        "tests/integration",
        "tests/ui",
        "tests/fixtures",
    ]
    for pkg in packages:
        init = BASE / pkg / "__init__.py"
        if not init.exists():
            write(init, "")


def create_base_model():
    content = '''"""
RetailFlow POS - Base SQLAlchemy Model
Mixin with common fields: id, created_at, updated_at.
"""
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.session import Base


class TimestampMixin:
    """Mixin for created_at/updated_at timestamp columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class BaseEntity(Base, TimestampMixin):
    """Abstract base for all entities with an integer primary key."""

    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
'''
    write(BASE / "infrastructure" / "database" / "models" / "base.py", content)


def create_base_repository():
    content = '''"""
RetailFlow POS - Base SQLAlchemy Repository
Concrete implementation of the Repository interface using SQLAlchemy.
"""
from __future__ import annotations

from typing import TypeVar, Generic, Optional, Sequence, Any

from sqlalchemy.orm import Session

from domain.interfaces.repository import Repository
from infrastructure.database.session import Base

T = TypeVar("T", bound=Base)
ID = TypeVar("ID")


class SqlAlchemyRepository(Repository[T, ID]):
    """Generic SQLAlchemy-based repository."""

    def __init__(self, session: Session, model_class: type[T]):
        self._session = session
        self._model_class = model_class

    def get_by_id(self, entity_id: ID) -> Optional[T]:
        return self._session.get(self._model_class, entity_id)

    def get_all(self, skip: int = 0, limit: int = 100) -> list[T]:
        return (
            self._session.query(self._model_class)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def add(self, entity: T) -> T:
        self._session.add(entity)
        self._session.flush()
        return entity

    def update(self, entity: T) -> T:
        self._session.merge(entity)
        self._session.flush()
        return entity

    def delete(self, entity_id: ID) -> None:
        entity = self.get_by_id(entity_id)
        if entity:
            self._session.delete(entity)
            self._session.flush()

    def count(self) -> int:
        return self._session.query(self._model_class).count()
'''
    write(BASE / "infrastructure" / "database" / "repositories" / "base.py", content)


def create_domain_enums():
    content = '''"""
RetailFlow POS - Domain Enums
Re-exports constants for use in domain logic.
"""
from app.constants import (
    MovementType,
    PaymentMethod,
    PurchaseOrderStatus,
    DiscountType,
    TaxType,
    UserRole,
    ShiftStatus,
    Status,
    ReturnReason,
    CostingMethod,
    ReceiptWidth,
)
'''
    write(BASE / "domain" / "enums" / "__init__.py", content)


def create_shared_date_time():
    content = '''"""
RetailFlow POS - DateTime Utilities
Common date/time helpers for the application.
"""
from datetime import datetime, date, timedelta
from typing import Optional


def now() -> datetime:
    """Get current UTC datetime."""
    return datetime.utcnow()


def today() -> date:
    """Get today's date."""
    return date.today()


def days_ago(days: int) -> datetime:
    """Get datetime for N days ago."""
    return datetime.utcnow() - timedelta(days=days)


def start_of_day(dt: Optional[datetime] = None) -> datetime:
    """Get the start of a given day (midnight)."""
    d = dt or datetime.utcnow()
    return datetime(d.year, d.month, d.day)


def end_of_day(dt: Optional[datetime] = None) -> datetime:
    """Get the end of a given day (23:59:59.999999)."""
    d = dt or datetime.utcnow()
    return datetime(d.year, d.month, d.day, 23, 59, 59, 999999)


def format_currency(amount: float, currency_symbol: str = "\\u20b1") -> str:
    """Format a float amount as currency string."""
    return f"{currency_symbol}{amount:,.2f}"


def format_date(d: date, fmt: str = "%Y-%m-%d") -> str:
    """Format a date object."""
    return d.strftime(fmt)


def format_datetime(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format a datetime object."""
    return dt.strftime(fmt)
'''
    write(BASE / "shared" / "date_time.py", content)


def create_shared_pagination():
    content = '''"""
RetailFlow POS - Pagination
Pagination helper for large data tables.
"""
from dataclasses import dataclass
from typing import Generic, TypeVar, Sequence

T = TypeVar("T")


@dataclass
class PaginatedResult(Generic[T]):
    """Container for paginated query results."""

    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        if self.page_size == 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def previous_page(self) -> int:
        return max(1, self.page - 1)

    @property
    def next_page(self) -> int:
        return min(self.total_pages, self.page + 1)


def paginate(
    query,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedResult:
    """Apply pagination to a SQLAlchemy query.

    Args:
        query: SQLAlchemy query object.
        page: 1-based page number.
        page_size: Items per page.

    Returns:
        PaginatedResult with items, total count, and navigation helpers.
    """
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResult(items=items, total=total, page=page, page_size=page_size)
'''
    write(BASE / "shared" / "pagination.py", content)


def create_app_bootstrap():
    content = '''"""
RetailFlow POS - Application Bootstrap
Initializes all subsystems before the UI starts.
"""
import logging
import sys
from pathlib import Path

from app.config import settings
from infrastructure.logging.setup import setup_logging
from infrastructure.database.session import init_database, dispose_engine

logger = logging.getLogger("retailflow")


def bootstrap() -> None:
    """Initialize all application subsystems.

    Order matters:
    1. Logging (so everything else can be logged)
    2. Configuration validation
    3. Database (tables created if needed)
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

        # 3. Initialize database
        init_database()
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
'''
    write(BASE / "app" / "bootstrap.py", content)


def create_app_main():
    content = '''"""
RetailFlow POS - Application Entry Point
"""
import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

from app.bootstrap import bootstrap, shutdown
from presentation.windows.main_window import MainWindow


def main() -> int:
    """Application entry point."""
    # Bootstrap subsystems before creating QApplication
    bootstrap()

    app = QApplication(sys.argv)
    app.setApplicationName("RetailFlow POS")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("RetailFlow")

    # Global application stylesheet
    _load_stylesheet(app)

    try:
        window = MainWindow()
        window.show()
        exit_code = app.exec()
    except Exception as e:
        QMessageBox.critical(
            None,
            "Application Error",
            f"A critical error occurred:\\n\\n{str(e)}\\n\\n"
            "Please check the logs for details.",
        )
        traceback.print_exc()
        exit_code = 1
    finally:
        shutdown()

    return exit_code


def _load_stylesheet(app: QApplication) -> None:
    """Load the global QSS stylesheet."""
    from pathlib import Path
    style_path = Path(__file__).resolve().parent.parent / "presentation" / "styles" / "app.qss"
    if style_path.exists():
        with open(style_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())


if __name__ == "__main__":
    sys.exit(main())
'''
    write(BASE / "app" / "main.py", content)


def create_main_window():
    content = '''"""
RetailFlow POS - Main Application Window
Shell with collapsible sidebar navigation and content area.
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QLabel, QPushButton, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon


NAV_ITEMS = [
    ("Dashboard", "dashboard", "Dashboard"),
    ("Point of Sale", "pos", "POS"),
    ("Sales", "sales", "Sales"),
    ("Products", "products", "Products"),
    ("Inventory", "inventory", "Inventory"),
    ("Purchasing", "purchasing", "Purchasing"),
    ("Suppliers", "suppliers", "Suppliers"),
    ("Customers", "customers", "Customers"),
    ("Expenses", "expenses", "Expenses"),
    ("Reports", "reports", "Reports"),
    ("Users", "users", "Users"),
    ("Audit Logs", "audit", "Audit"),
    ("Settings", "settings", "Settings"),
]


class MainWindow(QMainWindow):
    """Main application window with sidebar navigation and stacked content."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("RetailFlow POS")
        self.setMinimumSize(1280, 768)

        self._current_page = ""
        self._init_ui()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ─── Sidebar ───
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(220)
        self.sidebar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # App logo / title
        title_lbl = QLabel("RetailFlow POS")
        title_lbl.setObjectName("sidebarTitle")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setFixedHeight(56)
        sidebar_layout.addWidget(title_lbl)

        # Navigation buttons
        self.nav_buttons = {}
        for label, key, icon_name in NAV_ITEMS:
            btn = QPushButton(f"  {label}")
            btn.setObjectName("navButton")
            btn.setFixedHeight(44)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self.navigate_to(k))
            sidebar_layout.addWidget(btn)
            self.nav_buttons[key] = btn

        sidebar_layout.addStretch()

        # Version label at bottom
        version_lbl = QLabel("v1.0.0")
        version_lbl.setObjectName("sidebarVersion")
        version_lbl.setAlignment(Qt.AlignCenter)
        version_lbl.setFixedHeight(32)
        sidebar_layout.addWidget(version_lbl)

        main_layout.addWidget(self.sidebar)

        # ─── Content Area ───
        content_frame = QFrame()
        content_frame.setObjectName("contentArea")
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Top bar
        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(48)
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(16, 0, 16, 0)

        self.page_title = QLabel("Dashboard")
        self.page_title.setObjectName("pageTitle")
        topbar_layout.addWidget(self.page_title)

        topbar_layout.addStretch()

        user_btn = QPushButton("User")
        user_btn.setObjectName("topbarUserButton")
        topbar_layout.addWidget(user_btn)

        content_layout.addWidget(topbar)

        # Stacked pages
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)

        main_layout.addWidget(content_frame)

        # Create placeholder pages
        for label, key, _ in NAV_ITEMS:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setAlignment(Qt.AlignCenter)
            placeholder = QLabel(f"{label} Module")
            placeholder.setObjectName("placeholderLabel")
            placeholder.setAlignment(Qt.AlignCenter)
            page_layout.addWidget(placeholder)
            self.stack.addWidget(page)

        self.navigate_to("dashboard")

    def navigate_to(self, page_key: str):
        """Navigate to a page by its key."""
        if page_key == self._current_page:
            return

        self._current_page = page_key

        # Update button states
        for key, btn in self.nav_buttons.items():
            btn.setProperty("active", key == page_key)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        # Find and show the matching page
        for i, (_, key, _) in enumerate(NAV_ITEMS):
            if key == page_key:
                self.stack.setCurrentIndex(i)
                self.page_title.setText(NAV_ITEMS[i][0])
                break

    def get_current_user_display(self) -> str:
        """Returns the current user display name (placeholder)."""
        return "Administrator"
'''
    write(BASE / "presentation" / "windows" / "main_window.py", content)


def create_qss_stylesheet():
    content = '''/* ================================================================
   RetailFlow POS - Application Stylesheet (QSS)
   Clean, modern professional design with light theme.
   ================================================================ */

/* ─── Global ─── */
QMainWindow {
    background-color: #f5f6fa;
}

/* ─── Sidebar ─── */
#sidebar {
    background-color: #1e293b;
    border-right: 1px solid #334155;
}

#sidebarTitle {
    color: #f8fafc;
    font-size: 16px;
    font-weight: 700;
    padding: 12px;
    background-color: #0f172a;
}

#sidebarVersion {
    color: #64748b;
    font-size: 11px;
    padding: 4px;
    background-color: #0f172a;
}

#navButton {
    background-color: transparent;
    color: #94a3b8;
    border: none;
    border-radius: 0;
    text-align: left;
    padding: 0 20px;
    font-size: 13px;
}

#navButton:hover {
    background-color: #334155;
    color: #f8fafc;
}

#navButton[active="true"] {
    background-color: #3b82f6;
    color: #ffffff;
    font-weight: 600;
}

/* ─── Top Bar ─── */
#topbar {
    background-color: #ffffff;
    border-bottom: 1px solid #e2e8f0;
}

#pageTitle {
    color: #1e293b;
    font-size: 18px;
    font-weight: 700;
}

#topbarUserButton {
    background-color: #f1f5f9;
    color: #1e293b;
    border: 1px solid #e2e8f0;
    border-radius: 4px;
    padding: 4px 16px;
    font-size: 12px;
}

#topbarUserButton:hover {
    background-color: #e2e8f0;
}

/* ─── Content Area ─── */
#contentArea {
    background-color: #f5f6fa;
}

#placeholderLabel {
    color: #94a3b8;
    font-size: 24px;
}

/* ─── Standard Buttons ─── */
QPushButton {
    font-family: "Segoe UI", "Arial", sans-serif;
}

QPushButton#primaryButton {
    background-color: #3b82f6;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: 600;
}

QPushButton#primaryButton:hover {
    background-color: #2563eb;
}

QPushButton#dangerButton {
    background-color: #ef4444;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: 600;
}

QPushButton#dangerButton:hover {
    background-color: #dc2626;
}

QPushButton#secondaryButton {
    background-color: #e2e8f0;
    color: #1e293b;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    padding: 8px 20px;
    font-size: 13px;
}

QPushButton#secondaryButton:hover {
    background-color: #cbd5e1;
}

/* ─── Input Fields ─── */
QLineEdit {
    padding: 6px 10px;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    background: #ffffff;
    font-size: 13px;
    color: #1e293b;
}

QLineEdit:focus {
    border-color: #3b82f6;
}

/* ─── Tables ─── */
QTableWidget {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    gridline-color: #f1f5f9;
    font-size: 13px;
    selection-background-color: #dbeafe;
    selection-color: #1e293b;
}

QHeaderView::section {
    background-color: #f8fafc;
    color: #475569;
    padding: 8px;
    border: none;
    border-bottom: 2px solid #e2e8f0;
    font-weight: 700;
    font-size: 12px;
    text-transform: uppercase;
}

/* ─── Group Box / Cards ─── */
QGroupBox {
    font-size: 14px;
    font-weight: 700;
    color: #1e293b;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    margin-top: 12px;
    padding: 16px;
    background-color: #ffffff;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #1e293b;
}

/* ─── Scroll Bars ─── */
QScrollBar:vertical {
    background: #f1f5f9;
    width: 8px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #94a3b8;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: #64748b;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}

/* ─── Status Bar ─── */
QStatusBar {
    background-color: #f8fafc;
    color: #475569;
    border-top: 1px solid #e2e8f0;
    font-size: 12px;
}
'''
    write(BASE / "presentation" / "styles" / "app.qss", content)


def create_readme():
    content = """# RetailFlow POS

**Desktop Point of Sale and Inventory Management System**

RetailFlow POS is a production-grade desktop application for small and medium-sized businesses (grocery stores, retail shops, pharmacies, cafes, etc.). Built with Python and PySide6 using Clean Architecture principles.

## Features (MVP v1.0)

- **Authentication & RBAC** - Secure login with Argon2 hashing, role-based access control
- **Dashboard** - Sales summary, low-stock alerts, recent transactions
- **Product Management** - Products, categories, brands, units, barcodes, pricing
- **Inventory Management** - Stock in/out, adjustments, stock counts, low-stock alerts
- **Supplier Management** - Supplier profiles, purchase history
- **Purchasing** - Purchase orders, goods receiving, purchase returns
- **Point of Sale** - Fast barcode scanning, cash payment, receipt printing
- **Sales History** - View and search past transactions
- **Cashier Shifts** - Open/close shifts, cash tracking, variance reporting
- **Basic Returns** - Sales returns with validation and stock restoration
- **Reports** - Sales reports, inventory reports, PDF/Excel export
- **User Management** - Create/edit users, assign roles and permissions
- **Settings** - System configuration, tax, receipt, security settings
- **Audit Trails** - Immutable activity logging
- **Backup & Restore** - Manual and scheduled database backups

## Tech Stack

| Layer | Technology |
|-------|-----------|
| UI Framework | PySide6 (Qt for Python) |
| ORM | SQLAlchemy 2.0 |
| Database (dev) | SQLite |
| Database (prod) | PostgreSQL |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| Security | Argon2, cryptography |
| Reports | ReportLab, pandas, openpyxl |
| Testing | pytest, pytest-qt |
| Packaging | PyInstaller |

## Architecture

Follows **Clean Architecture** with layered separation:

```
presentation/   → PySide6 windows, widgets, dialogs
application/    → Use cases, services, DTOs, validators
domain/         → Entities, value objects, interfaces, business rules
infrastructure/ → SQLAlchemy models, repositories, printing, backups
shared/         → Result pattern, date utilities, pagination
```

## Quick Start

### Prerequisites

- Python 3.12+
- pip

### Setup

```bash
# Clone the repository
git clone <repo-url>
cd retailflow_pos

# Create virtual environment
python -m venv .venv
.venv\\Scripts\\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Copy environment config
copy .env.example .env

# Run the application
python app/main.py
```

### First Login

Default admin account:
- **Username:** admin
- **Password:** admin123

*Change the password immediately after first login.*

## Development

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=retailflow_pos tests/

# Lint
ruff check .

# Format
black .

# Type check
mypy .
```

## Project Structure

```
retailflow_pos/
├── app/                 # Entry points, config, constants
├── presentation/        # PySide6 UI layer
├── application/         # Business use cases & services
├── domain/              # Core business entities & rules
├── infrastructure/      # Database, security, printing, etc.
├── shared/              # Cross-cutting utilities
├── tests/               # Test suite
├── scripts/             # Utility scripts
├── docs/                # Documentation
├── data/                # SQLite database
├── logs/                # Application logs
├── backups/             # Database backups
└── exports/             # Generated reports
```

## License

Proprietary software. All rights reserved.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full feature roadmap.
"""
    write(BASE / "README.md", content)


def create_requirements_txt():
    """Copy requirements from project root if it already exists."""
    src = BASE.parent / "requirements.txt"
    if src.exists():
        return
    # requirements.txt created earlier in root, skip


print("Creating __init__.py files...")
create_init_files()

print("\\nCreating base SQLAlchemy model...")
create_base_model()

print("\\nCreating base repository...")
create_base_repository()

print("\\nCreating domain enums...")
create_domain_enums()

print("\\nCreating shared utilities...")
create_shared_date_time()
create_shared_pagination()

print("\\nCreating application bootstrap...")
create_app_bootstrap()

print("\\nCreating main entry point...")
create_app_main()

print("\\nCreating main window...")
create_main_window()

print("\\nCreating QSS stylesheet...")
create_qss_stylesheet()

print("\\nCreating README...")
create_readme()

print("\\nFoundation files created successfully!")