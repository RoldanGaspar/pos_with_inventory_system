# ROADMAP.md — RetailFlow POS

## Completion criteria per phase

A phase is complete when:
1. All modules in the phase have domain entities, SQLAlchemy models, repositories, application services, and presentation widgets
2. Ruff, black, and mypy pass with zero errors
3. Unit tests cover each service method (happy path + at least 1 error path)
4. Manual smoke test passes (launch app, navigate to each new page, perform core action)

## Phase 1 — Foundation (COMPLETE)

- [x] Project scaffold (directories, pyproject.toml, requirements.txt)
- [x] Configuration system (pydantic-settings, .env)
- [x] Database engine, session factory, base model
- [x] Auth models: User, Role, Permission, UserSession, LoginAttempt, PasswordHistory, AuditLog
- [x] Password hashing (Argon2), strength validation
- [x] Repository pattern (abstract + SQLAlchemy concrete)
- [x] Auth repositories (user, role, permission, audit, session)
- [x] Auth seeder (5 roles, 36 permissions, 3 default users)
- [x] Authentication service (login, logout, lockout, password change)
- [x] Domain exception hierarchy (30+ exceptions)
- [x] Login dialog (modal, async login, error display)
- [x] MainWindow shell (sidebar nav, QStackedWidget, 13 placeholder pages)
- [x] Global QSS stylesheet (light theme, dark sidebar)
- [x] Logging (6 rotating file handlers)
- [x] Result pattern (shared/result.py)
- [x] Pagination helper
- [x] Date/time and currency utilities

## Phase 2 — MVP Core (IN PROGRESS)

**Prerequisites**: Phase 1

### 2.1 Products Module
- [x] Entities: Product, Category, Brand, Unit, ProductBarcode (SQLAlchemy ORM models, consistent with Auth precedent)
- [x] Repository: ProductRepository with search by name/barcode/SKU
- [x] Application service: ProductService (CRUD + search + validation + archive)
- [x] UI: Product list table, add/edit dialog, search bar, metrics, filters, pagination
- [ ] Barcode generation (python-barcode integration)

### 2.2 Inventory Module
- [ ] Domain entities: StockMovement, StockCount
- [ ] Repository: InventoryRepository, StockMovementRepository
- [ ] Application service: InventoryService (receive, adjust, transfer, count)
- [ ] UI: Inventory list, movement history, stock adjustment dialog, low-stock alerts

### 2.3 Suppliers Module
- [ ] Domain entity: Supplier
- [ ] Repository: SupplierRepository
- [ ] Application service: SupplierService (CRUD)
- [ ] UI: Supplier list, add/edit dialog

### 2.4 Purchasing Module
- [ ] Domain entities: PurchaseOrder, PurchaseOrderLine
- [ ] State machine: DRAFT→SUBMITTED→APPROVED→PARTIALLY_RECEIVED→FULLY_RECEIVED→CLOSED
- [ ] Repository: PurchaseOrderRepository
- [ ] Application service: PurchaseService (create, approve, receive)
- [ ] UI: PO list, create/edit PO dialog, goods receiving dialog

### 2.5 POS Module
- [ ] UI: POS screen (product grid, cart panel, payment panel)
- [ ] Barcode/keyword search (debounced, real-time product lookup)
- [ ] Cart management (add, remove, quantity, discounts)
- [ ] Discount engine (%, fixed, senior citizen, PWD)
- [ ] Payment processing (cash, card, GCash, Maya)
- [ ] Receipt generation (58mm/80mm/A4)

### 2.6 Sales Module
- [ ] Domain entities: Sale, SaleLineItem, Payment
- [ ] Repository: SaleRepository
- [ ] Application service: SalesService (create sale from cart, void, refund)
- [ ] UI: Sales history table, sale detail view, void/return UI

### 2.7 Sales Returns Module
- [ ] Domain entity: Return
- [ ] Business rules: return window expiry, max return quantity ≤ sold quantity
- [ ] Application service: ReturnService (validate, process, restore stock)
- [ ] UI: Return dialog from sales history

### 2.8 Cashier Shifts Module
- [ ] Domain entities: Shift, ShiftCashDenomination
- [ ] Business rules: one open shift per cashier, mandatory close with cash count
- [ ] Application service: ShiftService (open, close, variance calc)
- [ ] UI: Shift open/close dialog, cash count entry

### 2.9 Reports Module
- [ ] Sales reports (daily, date range, by payment method, by product)
- [ ] Inventory reports (stock levels, movements, valuation)
- [ ] PDF export (ReportLab)
- [ ] Excel export (openpyxl)
- [ ] Dashboard widgets (summary cards, charts — TBD on charting library)

### 2.10 Users & Roles Module
- [ ] UI: User list table, add/edit user dialog, role assignment
- [ ] Application service: UserManagementService (CRUD, password reset)

### 2.11 Audit Logs Module
- [ ] UI: Filterable/sortable audit log table
- [ ] Export audit logs to CSV/PDF

### 2.12 Settings Module
- [ ] UI: Settings form (tax rate, receipt header/footer, security params)
- [ ] Persist settings to database (not just .env)

### 2.13 Dashboard
- [ ] Summary cards: today's sales, active users, low-stock count, active shift
- [ ] Recent transactions table

## Phase 3 — Post-MVP

**Prerequisites**: Phase 2

- [ ] Customer management (profiles, loyalty points — TBD)
- [ ] Expense tracking module
- [ ] Alembic migration setup and first migration
- [ ] PostgreSQL deployment guide and testing
- [ ] Backup/restore UI (currently config-only)
- [ ] Database backup scheduler
- [ ] Barcode scanner hardware integration
- [ ] Thermal receipt printer integration (ESC/POS)
- [ ] Cash drawer integration
- [ ] Advanced reports (profit/loss, tax summaries, purchasing analysis)
- [ ] Multi-terminal session management

## Phase 4 — Future (TBD)

- [ ] PyInstaller packaging script (single .exe)
- [ ] Auto-updater
- [ ] Multi-language support (i18n)
- [ ] API layer for external integrations
- [ ] E-commerce sync
- [ ] Supplier portal
