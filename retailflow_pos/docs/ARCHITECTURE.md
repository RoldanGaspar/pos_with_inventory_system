# ARCHITECTURE.md — RetailFlow POS

## Pattern: Clean Architecture (layered)

Dependency direction is strictly inward. Outer layers depend on inner layers. Inner layers have zero knowledge of outer layers.

```
presentation/   ─── PySide6 UI
    │  depends on
    ▼
application/   ─── use cases, services, DTOs
    │  depends on
    ▼
domain/        ─── entities, value objects, repository interfaces, business rules
    ▲  implements
    │
infrastructure/ ─── SQLAlchemy, hashing, logging, printing
    ▲  depends on (for interfaces)
    │
domain/
```

`shared/` is cross-cutting — all layers may depend on it (Result, date utils, pagination).

## Layer responsibilities

### `app/` — Entrypoint and configuration
- `main.py` — creates QApplication, orchestrates login → MainWindow flow → event loop
- `bootstrap.py` — subsystem initialization in order: logging → directories → DB → seed
- `config.py` — Pydantic `Settings` singleton; all config from `.env` exposed as typed properties
- `constants.py` — all system enums (UserRole, Status, PaymentMethod, MovementType, etc.)

### `presentation/` — UI layer
- **Dependencies**: PySide6, `application/` services, `infrastructure/` models (for type hints)
- Windows: `MainWindow` (sidebar + QStackedWidget navigation)
- Dialogs: `LoginDialog` (modal, async login via QTimer)
- Widgets: reusable PySide6 custom widgets per module
- Styles: `app.qss` global stylesheet loaded at startup
- **Rule**: never import `domain/` interfaces; call application services instead

### `application/` — Use cases and orchestration
- Services: `AuthenticationService` (and future ProductService, InventoryService, etc.)
- Use cases: individual operations (e.g., CreateProduct, AdjustStock)
- DTOs: data transfer objects between layers
- Commands: write-side request objects (CQRS pattern — TBD)
- Queries: read-side query objects (CQRS pattern — TBD)
- Validators: input validation rules
- **Rule**: orchestrate domain entities and repositories; no UI or ORM imports

### `domain/` — Business rules (zero framework imports)
- Entities: not yet introduced as separate dataclasses. The current precedent (Auth, Products) is to use the SQLAlchemy ORM model directly as the entity, so `domain/entities/` and `domain/value_objects/` remain empty. Revisit only if a genuine need arises.
- Repository interfaces: `Repository[T, ID]` ABC (CRUD contract)
- Exceptions: 30+ domain exceptions (AuthenticationError, InsufficientStockError, etc.)
- Enums: re-exports from `app/constants.py`
- Business rules: pure, framework-free functions live in `domain/rules/` (e.g., `stock_rules.stock_status`)
- **Rule**: no SQLAlchemy, no PySide6, no infrastructure imports whatsoever

### `infrastructure/` — External adapters
- Database: models (SQLAlchemy ORM), repositories (concrete SqlAlchemyRepository), seeders
- Security: Argon2 password hashing and strength validation
- Logging: structlog + rotating file handlers (6 log categories)
- Printing, reports, exports, imports, backups: external I/O adapters (TBD)

### `shared/` — Cross-cutting utilities
- `result.py` — monadic `Result[T, E]` for consistent error handling
- `date_time.py` — date formatting, currency formatting (PHP)
- `pagination.py` — `PaginatedResult` and `paginate()` helper

## Dependency injection

No DI container. Dependencies are passed explicitly:
- Services receive `Session` and repositories in constructor
- Repositories receive `Session` in constructor
- Windows/dialogs receive services in constructor (or create them from a session)

Example (current pattern):
```python
session = create_session()
auth_service = AuthenticationService(session)
login_dialog = LoginDialog(session)
```

## Data flow

### Login flow
```
LoginDialog._attempt_login()
  → QTimer.singleShot(100, _do_login)   [non-blocking]
    → AuthenticationService.login(username, password)
      → UserRepository.get_by_username()
      → verify_password()
      → UserSessionRepository.create_session()
      → returns (User, token)
  → LoginDialog.accept()
→ main() reads user/token, creates MainWindow
```

### Planned POS flow (TBD)
```
POS screen (scanner/keyword input)
  → ProductRepository.search(query)       [debounced]
  → Add to cart (in-memory Cart object)
  → Checkout button
    → PaymentService.process(cart, payment_method, amount_tendered)
      → validate stock levels
      → create Sale + SaleLineItems
      → create StockMovements (sale out)
      → create Payment record
      → generate receipt
    → return SaleResult
```

### Planned inventory adjustment (TBD)
```
InventoryAdjustDialog → submit
  → InventoryService.adjust(product_id, quantity, reason)
    → validate adjustment (no negative stock without override)
    → create StockMovement
    → update product stock_on_hand
    → audit log
```

## Design decisions

| Decision | Rationale |
|---|---|
| Repository pattern | Swap SQLite/PostgreSQL without touching domain/application layers |
| Monadic Result | Consistent error handling without exception overhead for expected failures |
| No DI container | Simple explicit wiring; codebase is small enough. Revisit if complexity grows. |
| `Base.metadata.create_all()` for now | Fast dev iteration. Alembic migrations before Phase 3. |
| Session-per-login (current) | Simple. Will need session-per-request or scoped sessions for multi-tab concurrency. |
| QTimer.singleShot for login | Prevents UI freeze during synchronous DB call in the event loop |
| QSS stylesheet over Qt Designer | Designer `.ui` files not used; all widgets built in code + QSS styling |
| Enums in `app/constants.py`, re-exported in `domain/enums/` | Single source of truth avoids circular imports between domain and infrastructure |

## Boundaries that must not be violated

1. **`domain/` must not import from any other layer** — no SQLAlchemy, no PySide6, no `app/config.py`
2. **`presentation/` must not import from `domain/`** — call application services, which return DTOs or entities
3. **`shared/` must not import from any layer** — it's utility-only
4. **Only `infrastructure/database/repositories/` should import `Session` directly** — services use repositories, not raw sessions
5. **No business logic in UI code** — presentation handles display and events only; all decisions in application/domain
