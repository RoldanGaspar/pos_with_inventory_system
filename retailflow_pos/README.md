# RetailFlow POS

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
.venv\Scripts\activate  # Windows

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

See [ROADMAP.md](docs/ROADMAP.md) for the full feature roadmap.
