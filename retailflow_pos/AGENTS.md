# AGENTS.md — RetailFlow POS

## Quick start

```powershell
# From retailflow_pos/:
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m app.main
```

Run with `python -m app.main` (NOT `python app/main.py`). Running the script directly puts `app/` on `sys.path[0]` instead of the project root, so `from app.config import settings` fails with `ModuleNotFoundError: No module named 'app'`.

Default admin: `admin` / `admin123` (change immediately after first login).

## Working directory

All commands run from `retailflow_pos/`. The parent directory (`pos_with_inventory_system/`) contains no project code.

## Project is NOT an installed package

Imports work because the working directory is `retailflow_pos/`. There is no `setup.py` install or `pip install -e .`. Do not add `retailflow_pos.` prefixes to imports — the flat layout (`app/`, `domain/`, etc.) is intentional. Because of this, always launch via `python -m app.main` (module mode adds the project root to `sys.path`), never `python app/main.py`.

## Before any task

Load these docs for full context (they are authoritative for their domains):
- `docs/CONTEXT.md` — project purpose, features, tech stack, current status
- `docs/ARCHITECTURE.md` — layer boundaries, dependency rules, design decisions
- `docs/DATABASE.md` — entity schemas (implemented + planned), indexes, migration strategy
- `docs/ROADMAP.md` — phases, completion criteria, feature scope
- `docs/SECURITY.md` — auth, RBAC, password policy, audit logging, secrets
- `docs/TESTING.md` — test patterns, required checks, isolation rules

**Source code is the source of truth.** If docs conflict with the actual code, code wins. Update the docs to match.

## Architecture rules (non-negotiable)

Layers form a strict dependency chain. **Never** invert these:

```
presentation/   → depends on → application/   → depends on → domain/
infrastructure/ → implements contracts in → domain/
shared/         → usable by all layers
```

**Hard boundaries:**
1. `domain/` must never import from any other layer (no SQLAlchemy, no PySide6, no `app/config.py`)
2. `presentation/` must never import from `domain/` directly — call `application/` services instead
3. `shared/` must never import from any layer — utility code only
4. Raw `Session` objects belong only in `infrastructure/database/repositories/` — services use repositories, not sessions
5. No business logic in UI code — presentation handles display and events; all decisions live in `application/` or `domain/`
6. No Qt widget code in `application/` or `domain/`

**Known exception:** `domain/enums/__init__.py` imports from `app/constants.py`. This is an intentional re-export pattern (see `docs/ARCHITECTURE.md` line 135). Do not "fix" it by moving enums — the single source of truth avoids circular imports.

## How to build a new module

Each feature module follows this exact stack (top to bottom):

1. **Domain layer** — entity/value objects in `domain/entities/`, business rules in `domain/rules/`, new exceptions in `domain/exceptions/__init__.py`
2. **Infrastructure layer** — SQLAlchemy model in `infrastructure/database/models/`, import it in `session.py`'s `_import_models()`, repository in `infrastructure/database/repositories/`, seeder if needed
3. **Application layer** — service in `application/services/`, DTOs in `application/dto/`, validators in `application/validators/`
4. **Presentation layer** — widget/list/dialog in `presentation/widgets/` or `presentation/dialogs/`, wire into `MainWindow` navigation

Follow existing patterns: `AuthenticationService` + `UserRepository` + `User` model is the reference implementation.

## Coding conventions

- **Line length**: 100 (black + ruff both configured)
- **Imports**: ruff's `I` rule sorts imports (stdlib → third-party → local). Group by layer.
- **Type hints**: use SQLAlchemy 2.0 `Mapped[]` / `mapped_column()` style (see `models/auth.py`). Domain entities prefer dataclasses.
- **Exceptions**: use the existing hierarchy in `domain/exceptions/`. Never use bare `Exception` or generic `ValueError` in services. Add new exceptions under the correct parent.
- **Result pattern**: `shared/result.py` provides `Result.ok(value)` / `Result.fail(error)`. Prefer this for service return types where failure is expected. Use exceptions only for truly exceptional cases.
- **Currency**: Philippine Peso (`₱`). Use `shared/date_time.py` formatting helpers.
- **QSS styling**: use object name selectors (`#navButton`, `#primaryButton`) with a style class in `app.qss`. Widgets are built in code, not Qt Designer `.ui` files.
- **Active nav buttons**: use `btn.setProperty("active", True)` + `style().unpolish(btn)` + `style().polish(btn)` — QSS `[active="true"]` selectors only re-evaluate after polish.
- **Non-blocking UI**: long operations use `QTimer.singleShot(100, lambda: ...)` to keep the event loop responsive (see `LoginDialog._attempt_login`).
- **Python 3.12+**: `datetime.utcnow()` is deprecated. Use `from datetime import UTC` then `datetime.now(UTC)` (or `datetime.now(timezone.utc)`). Note `datetime.UTC` only works when `datetime` is the module, not when imported as the class.
- **PyInstaller paths**: `Path(__file__).resolve()` resolves to the temp `_MEIPASS` directory in frozen bundles. Use `sys._MEIPASS` detection for bundled resources like `app.qss` — otherwise the stylesheet silently fails to load.

## Development workflow (required order)

Run these in sequence. All must pass with zero errors before a task is complete:

```powershell
ruff check . --fix    # 1. lint + auto-fix
black . --check       # 2. format check
mypy .                # 3. type check
pytest                # 4. run tests
```

To run with coverage (the `pyproject.toml` source path is wrong — use explicit `--cov` args):

```powershell
pytest --cov=app --cov=application --cov=domain --cov=infrastructure --cov=shared --cov=presentation
```

Run a single test file:

```powershell
pytest tests/unit/test_auth_service.py
```

Run only one test mark:

```powershell
pytest -m unit
```

## Testing requirements

- Zero test files exist yet. Every new service/module **must** include tests.
- **Unit tests** (`tests/unit/`): mock repositories, test service logic. 1 happy path + ≥1 error path per method.
- **Integration tests** (`tests/integration/`): SQLite `:memory:`, real DB calls. Test repository queries end-to-end.
- **UI tests** (`tests/ui/`): pytest-qt with `qtbot`. Test behavior and state transitions, not visual layout.
- Use `factory-boy` for test data (put factories in `tests/fixtures/`).
- Tests must not depend on `data/retailflow.db` or test execution order.
- Full details: see `docs/TESTING.md`.

## Security rules

Full details: `docs/SECURITY.md`. Key points:

- Never hardcode secrets or log passwords/tokens.
- Audit-log all sensitive actions via `AuditLogRepository.log_action()`.
- Passwords via `hash_password()` / `verify_password()` from `infrastructure/security/hashing.py`.
- RBAC: `check_permission()` or `user.has_permission()` — default-deny, grant via roles.
- **Error messages must not leak account existence.** If a user enters a valid username, the error message for a wrong password, locked account, inactive account, or expired password should all read `"Invalid username or password."` — not distinct messages per case.

## Destructive database operations

- **Never drop or delete `data/retailflow.db`** unless explicitly asked by the user.
- **Never run DROP TABLE, TRUNCATE, or DELETE without WHERE** unless explicitly asked.
- **Never modify the seeder** to remove existing data unless asked. Appending new seed data is safe.
- When adding a new model, register it in `infrastructure/database/session.py`'s `_import_models()`. Existing data survives `Base.metadata.create_all()` (it only creates missing tables).
- The seeder checks for existing `admin` user before inserting — it is idempotent. Follow this pattern for new seeders.
- There are no Alembic migrations yet. Schema changes require deleting the DB file and re-running the seeder — **confirm with the user before doing this.**

## No unnecessary refactoring

- Do not restructure working code unless the task demands it.
- Do not rename modules, reorganize directory structure, or change existing class interfaces without explicit instruction.
- Do not introduce new dependencies without checking `requirements.txt` first.
- Do not change configuration defaults in `.env.example` or `app/config.py`.
- Adding new code to stub directories is expected. Refactoring existing working code is not.

## Key file reference

| File | Role |
|---|---|
| `app/main.py` | Entrypoint — QApplication, login→MainWindow, event loop (run via `python -m app.main`) |
| `app/bootstrap.py` | Init order: logging → dirs → DB → seed |
| `app/config.py` | Settings singleton (`from app.config import settings`) |
| `app/constants.py` | All enums — single source of truth |
| `infrastructure/database/session.py` | Engine, session factory, `init_database()`, `_import_models()` |
| `infrastructure/database/models/base.py` | `BaseEntity` (id, created_at, updated_at) |
| `infrastructure/database/models/auth.py` | Reference model — follow this style for new models |
| `infrastructure/database/repositories/base.py` | `SqlAlchemyRepository` — generic CRUD |
| `infrastructure/database/repositories/auth.py` | Reference repository — follow this style |
| `infrastructure/database/seeders/auth_seeder.py` | Reference seeder — idempotent, checks before insert |
| `domain/interfaces/repository.py` | Abstract `Repository[T, ID]` ABC |
| `domain/exceptions/__init__.py` | Exception hierarchy — add new exceptions here |
| `application/services/auth_service.py` | Reference service — follow this constructor + method style |
| `presentation/windows/main_window.py` | MainWindow — sidebar nav, QStackedWidget |
| `presentation/dialogs/login_dialog.py` | Reference dialog — non-blocking login pattern |
| `presentation/styles/app.qss` | Global stylesheet |
| `shared/result.py` | `Result[T, E]` — use for service return types |
