# CONTEXT.md — RetailFlow POS

## Purpose

Desktop **Point of Sale and Inventory Management** application for small-to-medium businesses (grocery stores, retail shops, pharmacies, cafés). Single-computer or multi-terminal operation with role-based access control.

## Target users

- **Cashiers** — fast POS entry, barcode scanning, cash handling, shift open/close
- **Managers** — product and inventory management, purchasing, reporting, user management
- **Administrators** — system configuration, user/role/permission administration, backup/restore
- **Inventory staff** — stock receiving, adjustments, transfers, stock counts
- **Auditors** — read-only access to transactions, reports, and audit logs

## Core features (v1.0 MVP scope)

| Module | Features |
|---|---|
| Authentication | Login/logout, account lockout, password expiry, password history, session management |
| RBAC | 5 roles, 36 granular permissions across 12 modules |
| Products | CRUD, categories, brands, units, barcodes, SKU, pricing, tax types |
| Inventory | Stock in/out, adjustments, transfers, stock counts, low-stock alerts |
| POS | Barcode scanning, product lookup, discounts (%, fixed, senior, PWD), cash/card/e-wallet payment |
| Sales | Transaction history, search, void |
| Sales returns | Return validation, stock restoration, refund |
| Purchasing | Purchase orders (draft→approved→received→closed), goods receiving |
| Suppliers | Supplier profiles, purchase history |
| Cashier shifts | Open/close, cash tracking, variance reporting |
| Reports | Sales reports, inventory reports, PDF/Excel export |
| Users | CRUD, role assignment |
| Audit logs | Immutable activity trail across all modules |
| Settings | Tax config, receipt config, security settings |
| Backup & restore | Manual and scheduled database backups |

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Desktop UI | PySide6 (Qt) |
| ORM | SQLAlchemy 2.0 |
| Dev database | SQLite |
| Production database | PostgreSQL |
| Migrations | Alembic (not yet configured) |
| Config | Pydantic v2 + pydantic-settings + python-dotenv |
| Auth | Argon2-cffi, `secrets.token_urlsafe` |
| Reports | ReportLab, WeasyPrint, Jinja2, pandas, openpyxl |
| Barcodes | Pillow, python-barcode, qrcode |
| Logging | structlog + rotating file handlers |
| Packaging | PyInstaller |
| Testing | pytest, pytest-cov, pytest-qt, factory-boy, Faker |
| Lint/format | ruff, black (line-length=100) |
| Type check | mypy |

## Project structure

```
retailflow_pos/          ← all commands run from here
├── app/                 ← entrypoint, bootstrap, config, constants
├── presentation/        ← PySide6 windows, dialogs, widgets, QSS styles
├── application/         ← services, use cases, DTOs, validators, commands, queries
├── domain/              ← repository interfaces, exceptions, enums, entities, value objects
├── infrastructure/      ← database (models, repos, seeders, migrations), security, logging, printing, backups
├── shared/              ← Result pattern, date_time utilities, pagination
├── tests/               ← unit/, integration/, ui/, fixtures/
├── scripts/             ← scaffolding/maintenance scripts
├── data/                ← SQLite database file
├── logs/                ← rotating log files
├── backups/             ← database backups
└── exports/             ← generated reports
```

## Current implementation status

**Working**: Authentication system (models, service, repositories, seeder), login dialog, main window shell (sidebar + QStackedWidget), QSS stylesheet, logging, configuration, Result pattern, all enums and exception classes. **Products module**: catalog models (Product, Category, Brand, Unit, ProductBarcode), Inventory snapshot, repositories, seeder, ProductService, Products page (metrics, search/filter, table, pagination), ProductFormDialog, archive-based deletion, RBAC read/write gating.

**Stubs only**: Inventory (stock movements), POS, sales, purchasing, suppliers, customers, expenses, reports, cashier shifts, backup/restore, printing, exports.

**Not started**: Alembic migrations, CI/CD. (Tests: 56 passing across unit/integration/UI.)

See [ROADMAP.md](ROADMAP.md) for planned phases.

## Known constraints

- **Windows-only**: tested and packaged for Windows (PyInstaller). Cross-platform not verified.
- **SQLite single-user**: development uses SQLite with `check_same_thread=False`. Multi-terminal requires PostgreSQL.
- **No web interface**: desktop-only. No API layer.
- **Philippine market**: currency defaults to PHP (₱), GCash/Maya payment methods, senior citizen/PWD discounts.
- **No multi-language**: English only. No i18n infrastructure.
- **No offline sync**: multi-terminal setup requires shared PostgreSQL; no offline-then-sync.
