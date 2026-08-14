# TESTING.md — RetailFlow POS

## Test framework

pytest with plugins: pytest-cov (coverage), pytest-qt (PySide6 widget testing), factory-boy (fixtures), Faker (test data).

## Test structure

```
tests/
├── unit/           ← isolated service/repository/domain logic tests
├── integration/    ← tests with real SQLite database
├── ui/             ← PySide6 widget and dialog tests (pytest-qt)
└── fixtures/       ← shared factories, conftest.py helpers
```

Tests are discovered via `test_*.py` pattern, defined in `pyproject.toml`.

## Test markers

| Marker | Purpose |
|---|---|
| `@pytest.mark.unit` | Pure logic, no DB, no UI |
| `@pytest.mark.integration` | Requires database (SQLite in-memory or file) |
| `@pytest.mark.ui` | Requires PySide6 QApplication (pytest-qt) |
| `@pytest.mark.slow` | Long-running; excluded from quick runs |

## Unit test strategy

- Target: domain logic, value objects, application services with mocked repositories
- Each service method: 1 happy-path test + at least 1 error-path test
- Repositories mocked via `unittest.mock` (no real DB)
- Use `Result[T, E]` pattern for return types; assert on `.is_success`, `.is_failure`, `.value`, `.error`

Example pattern:
```python
@pytest.mark.unit
def test_login_success(mock_user_repo, mock_session_repo):
    service = AuthenticationService(mock_session)
    user, token = service.login("admin", "admin123")
    assert user.username == "admin"
    assert len(token) > 0

@pytest.mark.unit
def test_login_invalid_password(mock_user_repo):
    service = AuthenticationService(mock_session)
    with pytest.raises(AuthenticationError, match="Invalid"):
        service.login("admin", "wrong")
```

## Integration test strategy

- Use SQLite `:memory:` database (no `data/retailflow.db` file)
- `tests/fixtures/conftest.py` provides `db_session` fixture:
  - Creates all tables via `Base.metadata.create_all()`
  - Runs seeder
  - Yields session, then rollback/cleanup
- Test repository methods against real queries
- Test full service→repository→DB flow

Example pattern:
```python
@pytest.mark.integration
def test_user_repository_get_by_username(db_session):
    repo = UserRepository(db_session)
    user = repo.get_by_username("admin")
    assert user is not None
    assert user.full_name == "System Administrator"
```

## UI test strategy

- Uses pytest-qt (`qtbot` fixture)
- Each dialog gets its own test class/file
- Test widget interactions: button clicks, field input, signals/slots
- Use `qtbot.mouseClick()`, `qtbot.keyClicks()` to simulate user input
- Avoid testing visual layout; test behavior and state transitions

Example pattern:
```python
@pytest.mark.ui
class TestLoginDialog:
    def test_empty_fields_shows_error(self, qtbot, db_session):
        dialog = LoginDialog(db_session)
        qtbot.addWidget(dialog)
        qtbot.mouseClick(dialog.btn_login, Qt.MouseButton.LeftButton)
        assert dialog.error_label.text() != ""
```

## Test isolation rules

1. Every test creates its own session; no shared state between tests
2. Use `db_session.rollback()` in teardown (or `yield` pattern)
3. Never depend on test execution order
4. Never depend on pre-existing data in `data/retailflow.db`
5. UI tests must clean up widgets/dialogs after each test

## Required checks before marking a task complete

Run these in order. All must pass with zero errors:

```powershell
# 1. Lint + auto-fix
ruff check . --fix

# 2. Format check (must produce no changes)
black . --check

# 3. Type check
mypy .

# 4. Run tests
pytest
```

If any step fails, the task is not complete.

## Coverage target

- Not enforced yet (56 tests exist; no coverage gate configured).
- Phase 2 target: ≥80% line coverage on `application/` and `domain/` layers.
- Run: `pytest --cov=app --cov=application --cov=domain --cov=infrastructure --cov=shared` (note: `pyproject.toml` coverage source needs fixing — see AGENTS.md)

## Test data (factories)

Use `factory-boy` for generating test instances. Define factories in `tests/fixtures/`. Example:

```python
# tests/fixtures/user_factories.py
import factory
from infrastructure.database.models.auth import User

class UserFactory(factory.Factory):
    class Meta:
        model = User
    username = factory.Sequence(lambda n: f"user{n}")
    full_name = factory.Faker("name")
    password_hash = "hashed_value"
    is_active = True
```

## Implemented

- [x] `tests/conftest.py` — shared fixtures (`db_session` in-memory SQLite, `user_with_permissions` factory)
- [x] Factory classes for Category, Brand, Unit, Product, ProductBarcode (`tests/fixtures/product_factories.py`)
- [x] Test suites: `unit/` (stock rules, validators), `integration/` (product + inventory repositories, product service), `ui/` (products page, product form dialog)

## Not yet implemented

- [ ] CI pipeline to run checks automatically
- [ ] Coverage enforcement
