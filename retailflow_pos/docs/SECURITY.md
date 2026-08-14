# SECURITY.md — RetailFlow POS

## Overview

Security is built into the auth system via Argon2 password hashing, role-based access control (RBAC), account lockout, password policies, session management, and immutable audit logging.

## Authentication

### Password hashing
- **Algorithm**: Argon2id via `argon2-cffi`
- **Configuration** (in `.env`): `ARGON2_MEMORY_COST=65536`, `ARGON2_TIME_COST=3`, `ARGON2_PARALLELISM=4`
- **Module**: `infrastructure/security/hashing.py`
  - `hash_password(plain) → str` — hash a password
  - `verify_password(plain, hashed) → bool` — verify against stored hash
  - `validate_password_strength(password) → (bool, str)` — enforce complexity rules

### Password policy
| Rule | Config key | Default |
|---|---|---|
| Minimum length | `PASSWORD_MIN_LENGTH` | 8 |
| Require uppercase | hardcoded | yes |
| Require lowercase | hardcoded | yes |
| Require digit | hardcoded | yes |
| Expiry (days) | `PASSWORD_EXPIRY_DAYS` | 90 |
| History (prevent reuse) | `PASSWORD_HISTORY_COUNT` | 5 |
| Force change on first login | seeder | admin only |

### Login flow
1. `UserRepository.get_by_username()` — find user
2. Check `is_active` — raise `AccountInactiveError` if deactivated
3. Check `is_locked_out()` — raise `AccountLockedError` if locked; auto-unlock if timer expired
4. `verify_password()` — raise `AuthenticationError` on mismatch
5. Check `password_expires_at` — raise `PasswordExpiredError` if expired
6. On success: reset `failed_login_count`, record `last_login_at`, create session token (`secrets.token_urlsafe(48)`)
7. Audit log: `LOGIN_SUCCESS` or `LOGIN_FAILURE` + reason

### Account lockout
| Rule | Config key | Default |
|---|---|---|
| Max failed attempts | `MAX_LOGIN_ATTEMPTS` | 5 |
| Lockout duration (minutes) | `LOCKOUT_MINUTES` | 15 |

- Lockout triggers when `failed_login_count >= max_login_attempts`
- `User.is_locked = True`, `User.locked_until` set
- Auto-unlock when `locked_until` is in the past (checked on next login attempt)
- Audit logged: `ACCOUNT_LOCKED`, `ACCOUNT_UNLOCKED`

### Session management
- Token: `secrets.token_urlsafe(48)` — 384 bits of randomness
- Stored in `user_sessions` table with expiry (`SESSION_TIMEOUT_MINUTES`, default 30)
- Sessions invalidated on logout via `invalidate_session(token)`
- Expired sessions cleaned up via `cleanup_expired()`

## Authorization (RBAC)

### Roles (5 system roles)
| Role | Scope |
|---|---|
| Administrator | All 36 permissions |
| Manager | Products, inventory, purchasing, sales, reports, users, settings, audit |
| Cashier | POS, shifts, basic sales/returns, view products/inventory |
| Inventory Staff | Stock receiving, adjustments, transfers, view products/suppliers |
| Auditor | Read-only: reports, audit logs, sales, inventory |

### Permissions (36 granular, 12 modules)
Modules: `auth`, `dashboard`, `products`, `inventory`, `suppliers`, `purchasing`, `pos`, `sales`, `reports`, `settings`, `audit`, `shifts`

Each permission is a `module:action` code (e.g., `pos_void`, `auth:manage_roles`).

### Enforcement
- Every protected operation must call `AuthenticationService.check_permission(user, code)` or `user.has_permission(code)`
- **Default-deny**: no permission → `AuthorizationError` raised
- Permissions are granted only via role assignment (no per-user permission overrides)
- **Products module**: `view_products` gates all catalog reads (`search`, `get_product`, `get_metrics`, `get_form_options`); `create_products` / `edit_products` / `delete_products` gate writes. Product deletion is archive-based (`status='archived'`), not a physical delete, and is recorded as `PRODUCT_ARCHIVED` in the audit log.

## Audit logging

All sensitive actions are recorded in the `audit_logs` table via `AuditLogRepository.log_action()`.

**Must-log events**: create, update, delete (any module), login, logout, password change, password reset, permission changes, role assignment, financial transactions (sales, payments, refunds), inventory adjustments, settings changes, account lock/unlock.

Recorded fields: `user_id`, `username`, `action`, `module`, `record_type`, `record_id`, `previous_value`, `new_value`, `ip_address`, `reason`, `status`.

## Secrets and configuration

- **Never hardcode secrets** in source code
- `app/config.py` reads from `.env` via Pydantic `BaseSettings`
- Environment variable → `.env` file → defaults
- In production: set `SECRET_KEY` via OS environment variable, not `.env`

## Logging security

- **Never log passwords, tokens, or full session data**
- Security events use `retailflow.security` logger (separate rotating file)
- Log categories: `error`, `security`, `database`, `application`, `backup`, `printing`

## Security boundaries

- `infrastructure/security/hashing.py` is the **only** module that touches raw passwords — all other code uses it
- `domain/` has zero knowledge of hashing implementation
- Authentication orchestration lives in `application/services/auth_service.py`
- UI code (`presentation/`) never handles passwords — credentials are passed to the service immediately
