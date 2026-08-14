# DATABASE.md — RetailFlow POS

## Engine

SQLAlchemy 2.0 ORM. Dev uses SQLite (`data/retailflow.db`). Production uses PostgreSQL.

Session settings (global):
- `autoflush=False` — manual flush control
- `expire_on_commit=False` — prevents detached instance errors in PySide6
- SQLite: `check_same_thread=False` (required for Qt thread model)

All models inherit from `BaseEntity`, which provides `id` (int PK, autoincrement), `created_at`, `updated_at`.

## Implemented entities (Auth)

### users
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK, autoincrement |
| username | VARCHAR(50) | UNIQUE, NOT NULL, INDEX |
| password_hash | VARCHAR(255) | NOT NULL |
| full_name | VARCHAR(100) | NOT NULL |
| email | VARCHAR(120) | NULLABLE |
| phone | VARCHAR(20) | NULLABLE |
| is_active | BOOLEAN | NOT NULL, DEFAULT TRUE |
| is_locked | BOOLEAN | NOT NULL, DEFAULT FALSE |
| must_change_password | BOOLEAN | NOT NULL, DEFAULT FALSE |
| failed_login_count | INTEGER | NOT NULL, DEFAULT 0 |
| locked_until | DATETIME | NULLABLE |
| last_login_at | DATETIME | NULLABLE |
| last_login_ip | VARCHAR(45) | NULLABLE |
| password_changed_at | DATETIME | NULLABLE |
| password_expires_at | DATETIME | NULLABLE |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'active' |
| created_at | DATETIME | NOT NULL |
| updated_at | DATETIME | NOT NULL |

### roles
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK, autoincrement |
| name | VARCHAR(100) | UNIQUE, NOT NULL |
| code | VARCHAR(50) | UNIQUE, NOT NULL, INDEX |
| description | VARCHAR(255) | NULLABLE |
| is_system | BOOLEAN | DEFAULT FALSE |
| created_at | DATETIME | NOT NULL |
| updated_at | DATETIME | NOT NULL |

### permissions
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK, autoincrement |
| name | VARCHAR(100) | UNIQUE, NOT NULL |
| code | VARCHAR(100) | UNIQUE, NOT NULL, INDEX |
| module | VARCHAR(50) | NOT NULL |
| description | VARCHAR(255) | NULLABLE |
| created_at | DATETIME | NOT NULL |
| updated_at | DATETIME | NOT NULL |

### user_roles (association)
| Column | Type | Constraints |
|---|---|---|
| user_id | INTEGER | PK, FK → users ON DELETE CASCADE |
| role_id | INTEGER | PK, FK → roles ON DELETE CASCADE |

### role_permissions (association)
| Column | Type | Constraints |
|---|---|---|
| role_id | INTEGER | PK, FK → roles ON DELETE CASCADE |
| permission_id | INTEGER | PK, FK → permissions ON DELETE CASCADE |

### user_sessions
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK, autoincrement |
| user_id | INTEGER | FK → users, NOT NULL |
| token | VARCHAR(255) | UNIQUE, NOT NULL |
| ip_address | VARCHAR(45) | NULLABLE |
| expires_at | DATETIME | NOT NULL |
| is_active | BOOLEAN | NOT NULL, DEFAULT TRUE |
| created_at | DATETIME | NOT NULL |
| updated_at | DATETIME | NOT NULL |

### login_attempts
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK, autoincrement |
| user_id | INTEGER | FK → users, NULLABLE |
| username | VARCHAR(50) | NOT NULL |
| ip_address | VARCHAR(45) | NULLABLE |
| success | BOOLEAN | NOT NULL, DEFAULT FALSE |
| failure_reason | VARCHAR(100) | NULLABLE |
| created_at | DATETIME | NOT NULL |
| updated_at | DATETIME | NOT NULL |

### password_history
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK, autoincrement |
| user_id | INTEGER | FK → users, NOT NULL, INDEX |
| password_hash | VARCHAR(255) | NOT NULL |
| created_at | DATETIME | NOT NULL |
| updated_at | DATETIME | NOT NULL |

### audit_logs
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK, autoincrement |
| user_id | INTEGER | FK → users, NULLABLE |
| username | VARCHAR(50) | NOT NULL |
| action | VARCHAR(100) | NOT NULL, INDEX |
| module | VARCHAR(50) | NOT NULL, INDEX |
| record_type | VARCHAR(50) | NULLABLE |
| record_id | INTEGER | NULLABLE |
| previous_value | TEXT | NULLABLE |
| new_value | TEXT | NULLABLE |
| ip_address | VARCHAR(45) | NULLABLE |
| reason | VARCHAR(255) | NULLABLE |
| status | VARCHAR(20) | DEFAULT 'success' |
| created_at | DATETIME | NOT NULL |
| updated_at | DATETIME | NOT NULL |

## Implemented entities (Products & catalog)

### categories
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK, autoincrement |
| name | VARCHAR(100) | UNIQUE, NOT NULL |
| parent_id | INTEGER | FK → categories, NULLABLE (self-reference) |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'active' |
| created_at / updated_at | DATETIME | NOT NULL |

### brands
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK, autoincrement |
| name | VARCHAR(100) | UNIQUE, NOT NULL |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'active' |
| created_at / updated_at | DATETIME | NOT NULL |

### units
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK, autoincrement |
| name | VARCHAR(100) | UNIQUE, NOT NULL |
| abbreviation | VARCHAR(20) | UNIQUE, NOT NULL |
| created_at / updated_at | DATETIME | NOT NULL |

### products
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK, autoincrement |
| sku | VARCHAR(50) | UNIQUE, NOT NULL, INDEX |
| name | VARCHAR(150) | NOT NULL, INDEX |
| description | TEXT | NULLABLE |
| category_id | INTEGER | FK → categories, NULLABLE |
| brand_id | INTEGER | FK → brands, NULLABLE |
| base_unit_id | INTEGER | FK → units, NULLABLE |
| cost_price | NUMERIC(12,2) | NOT NULL, DEFAULT 0 |
| selling_price | NUMERIC(12,2) | NOT NULL, DEFAULT 0 |
| tax_type | VARCHAR(20) | NOT NULL, DEFAULT 'vat' |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'active' (`active` / `inactive` / `archived`) |
| reorder_level | INTEGER | NOT NULL, DEFAULT 0 |
| has_batch_tracking | BOOLEAN | NOT NULL, DEFAULT false |
| has_expiry | BOOLEAN | NOT NULL, DEFAULT false |
| created_at / updated_at | DATETIME | NOT NULL |

### product_barcodes
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK, autoincrement |
| product_id | INTEGER | FK → products, NOT NULL, INDEX |
| barcode | VARCHAR(100) | UNIQUE, NOT NULL, INDEX |
| is_primary | BOOLEAN | NOT NULL, DEFAULT false |
| created_at / updated_at | DATETIME | NOT NULL |

### inventory (stock-on-hand snapshot)
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK, autoincrement |
| product_id | INTEGER | FK → products, UNIQUE, NOT NULL (one row per product) |
| quantity_on_hand | INTEGER | NOT NULL, DEFAULT 0 |
| quantity_allocated | INTEGER | NOT NULL, DEFAULT 0 |
| last_counted_at | DATETIME | NULLABLE |
| created_at / updated_at | DATETIME | NOT NULL |

## Planned entities (Phase 2 — TBD until implemented)

### stock_movements
```
id, product_id (FK), movement_type (enum: receive, sale, return, adjust, transfer, damage, etc.),
quantity (INTEGER, signed — negative for out), reference_type, reference_id, batch_number, expiry_date,
unit_cost, reason, created_by, created_at
```

### suppliers
```
id, code (UNIQUE), company_name, contact_person, email, phone, address, status, notes,
created_at, updated_at
```

### purchase_orders
```
id, po_number (UNIQUE), supplier_id (FK), status (draft→submitted→approved→received→closed),
order_date, expected_date, received_date, subtotal, tax_amount, total, notes,
created_by, approved_by, created_at, updated_at
```

### purchase_order_lines
```
id, po_id (FK), product_id (FK), quantity_ordered, quantity_received, unit_cost, total,
created_at, updated_at
```

### sales
```
id, invoice_number (UNIQUE), user_id (FK, cashier), customer_id (FK, NULLABLE),
shift_id (FK), subtotal, discount_total, tax_amount, grand_total, amount_tendered,
change, payment_method (enum), status, notes, created_at
```

### sale_line_items
```
id, sale_id (FK), product_id (FK), quantity, unit_price, discount_amount, line_total, created_at
```

### sale_payments
```
id, sale_id (FK), payment_method (enum), amount, reference_number (NULLABLE), created_at
```

### sales_returns
```
id, return_number (UNIQUE), sale_id (FK), reason (enum), subtotal, tax_amount, total_refund,
status, processed_by, created_at, updated_at
```

### return_line_items
```
id, return_id (FK), sale_line_item_id (FK), quantity_returned, unit_refund, line_refund, created_at
```

### shifts
```
id, user_id (FK), shift_number, opening_amount, closing_amount, expected_amount,
variance, status (open/closed/pending_approval), opened_at, closed_at, closed_by,
notes, created_at, updated_at
```

### shift_cash_denominations
```
id, shift_id (FK), denomination (1000, 500, 200, 100, 50, 20, coin), count, subtotal, created_at
```

### settings
```
id, key (UNIQUE INDEX), value, value_type, module, description, created_at, updated_at
```
Store system settings as key-value pairs (TBD: single-row config vs key-value table).

## Entity relationship diagram (planned)

```
users ──< user_roles >── roles ──< role_permissions >── permissions
users ──< user_sessions
users ──< login_attempts
users ──< password_history
users ──< audit_logs
users ──< shifts
users ──< sales

categories ──< products
brands ──< products
units ──< products
products ──< product_barcodes
products ──< inventory          (one-to-one)
products ──< stock_movements
products ──< sale_line_items
products ──< purchase_order_lines

suppliers ──< purchase_orders ──< purchase_order_lines

sales ──< sale_line_items
sales ──< sale_payments
sales ──< sales_returns ──< return_line_items

shifts ──< shift_cash_denominations
shifts ──< sales
```

## Indexes (beyond PKs and FKs)

| Table | Index | Reason |
|---|---|---|
| products.sku | UNIQUE | Product lookup by SKU |
| product_barcodes.barcode | UNIQUE | Barcode scan lookup |
| purchase_orders.po_number | UNIQUE | PO number lookup |
| sales.invoice_number | UNIQUE | Receipt lookup |
| sales.created_at | INDEX | Date-range queries for reports |
| stock_movements.product_id + created_at | COMPOSITE | Stock movement history by product |
| stock_movements.movement_type | INDEX | Filter by movement type |
| audit_logs.action + created_at | COMPOSITE | Audit trail queries |
| settings.key | UNIQUE | Settings lookup |

## Migration strategy

**Current**: `Base.metadata.create_all()` in `init_database()`. Tables are created on first run. Not suitable for production schema evolution.

**Planned (Phase 3)**: Alembic with `alembic.ini` at project root.
- `alembic revision --autogenerate -m "description"` for each schema change
- `alembic upgrade head` on app startup (or manual)
- Migrations stored in `infrastructure/database/migrations/versions/`
- Each migration must be testable: upgrade + downgrade round-trip

## Migration-era hardening (deferred)

The following database-level `CHECK` constraints should be introduced through Alembic migrations (not `create_all()`, which will not alter existing tables). They are currently enforced only at the application layer:

- `products.cost_price >= 0`, `products.selling_price >= 0`
- `products.reorder_level >= 0`
- `inventory.quantity_on_hand >= 0`, `inventory.quantity_allocated >= 0`
- `products.status IN ('active','inactive','archived')`, `products.tax_type IN ('vat','non_vat','zero_rated','exempt')`

## Development vs production

| Aspect | Development | Production |
|---|---|---|
| Database | SQLite (file-based) | PostgreSQL |
| Connection pool | N/A (single file) | pool_size=5, max_overflow=10, pool_pre_ping=True |
| Secret key | `change-this-...` in .env | Environment variable or secrets manager |
| Log level | DEBUG | INFO or WARNING |
| Auth seeder | Auto-runs on empty DB | Manual, or disabled; admin created via script |
| Backup | Manual config | Scheduled auto-backup |
