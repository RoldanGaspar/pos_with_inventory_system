"""
RetailFlow POS - Authentication Seeder
Creates default roles, permissions, and admin user on first run.
"""
import logging
from sqlalchemy.orm import Session

from infrastructure.database.models.auth import User, Role, Permission
from infrastructure.security.hashing import hash_password
from app.constants import UserRole as UserRoleEnum

logger = logging.getLogger("retailflow.database")

# Default permissions per module
DEFAULT_PERMISSIONS = {
    "auth": [
        ("view_users", "View Users"),
        ("create_users", "Create Users"),
        ("edit_users", "Edit Users"),
        ("delete_users", "Delete Users"),
        ("manage_roles", "Manage Roles & Permissions"),
    ],
    "dashboard": [
        ("view_dashboard", "View Dashboard"),
    ],
    "products": [
        ("view_products", "View Products"),
        ("create_products", "Create Products"),
        ("edit_products", "Edit Products"),
        ("delete_products", "Delete Products"),
    ],
    "inventory": [
        ("view_inventory", "View Inventory"),
        ("receive_stock", "Receive Stock"),
        ("adjust_stock", "Adjust Stock"),
        ("transfer_stock", "Transfer Stock"),
    ],
    "suppliers": [
        ("view_suppliers", "View Suppliers"),
        ("manage_suppliers", "Manage Suppliers"),
    ],
    "purchasing": [
        ("view_purchase_orders", "View Purchase Orders"),
        ("create_purchase_orders", "Create Purchase Orders"),
        ("approve_purchase_orders", "Approve Purchase Orders"),
    ],
    "pos": [
        ("pos_access", "Access POS"),
        ("pos_discount", "Apply Discounts"),
        ("pos_void", "Void Transactions"),
        ("pos_hold_resume", "Hold & Resume Transactions"),
    ],
    "sales": [
        ("view_sales", "View Sales"),
        ("return_sales", "Process Returns"),
        ("refund_approve", "Approve Refunds"),
    ],
    "reports": [
        ("view_reports", "View Reports"),
        ("export_reports", "Export Reports"),
    ],
    "settings": [
        ("view_settings", "View Settings"),
        ("edit_settings", "Edit Settings"),
        ("manage_backup", "Manage Backups & Restore"),
    ],
    "audit": [
        ("view_audit_logs", "View Audit Logs"),
    ],
    "shifts": [
        ("open_shift", "Open Cashier Shift"),
        ("close_shift", "Close Shift"),
        ("approve_shift_close", "Approve Shift Closure"),
    ],
}

# Role-to-permission mapping
ROLE_PERMISSIONS = {
    UserRoleEnum.ADMINISTRATOR: ["*"],  # Admin gets all permissions
    UserRoleEnum.MANAGER: [
        "view_dashboard", "view_products", "create_products", "edit_products",
        "delete_products", "view_inventory", "receive_stock", "adjust_stock",
        "transfer_stock", "view_suppliers", "manage_suppliers",
        "view_purchase_orders", "create_purchase_orders", "approve_purchase_orders",
        "view_sales", "return_sales", "refund_approve",
        "view_reports", "export_reports",
        "view_settings", "edit_settings", "manage_backup",
        "view_audit_logs", "view_users", "create_users", "edit_users",
        "approve_shift_close",
    ],
    UserRoleEnum.CASHIER: [
        "pos_access", "pos_discount", "pos_hold_resume",
        "open_shift", "close_shift", "view_sales", "return_sales",
        "view_dashboard", "view_products", "view_inventory",
    ],
    UserRoleEnum.INVENTORY_STAFF: [
        "view_dashboard", "view_products", "view_inventory",
        "receive_stock", "adjust_stock", "transfer_stock",
        "view_suppliers", "view_purchase_orders",
    ],
    UserRoleEnum.AUDITOR: [
        "view_dashboard", "view_products", "view_inventory",
        "view_sales", "view_reports", "export_reports",
        "view_audit_logs", "view_suppliers", "view_purchase_orders",
        "view_users",
    ],
}


def seed_auth(session: Session) -> None:
    """Seed roles, permissions, and admin user if they do not exist."""
    # Check if already seeded
    existing_admin = session.query(User).filter(User.username == "admin").first()
    if existing_admin:
        logger.info("Auth data already seeded, skipping.")
        return

    logger.info("Seeding authentication data...")

    # Create permissions
    perm_map = {}
    for module, perms in DEFAULT_PERMISSIONS.items():
        for code, name in perms:
            perm = Permission(
                code=code, name=name, module=module,
                description=f"Allows {name.lower()}"
            )
            session.add(perm)
            perm_map[code] = perm
    session.flush()

    all_permission_codes = list(perm_map.keys())

    # Create roles
    for role_code in UserRoleEnum:
        role_perms = ROLE_PERMISSIONS.get(role_code, [])
        if role_perms == ["*"]:
            role_perms = all_permission_codes

        role = Role(
            name=role_code.value.replace("_", " ").title(),
            code=role_code.value,
            description=f"{role_code.value.replace('_', ' ').title()} role",
            is_system=True,
        )
        # Assign permissions
        role.permissions = [perm_map[code] for code in role_perms if code in perm_map]
        session.add(role)
    session.flush()

    # Create admin user
    admin_role = session.query(Role).filter(Role.code == UserRoleEnum.ADMINISTRATOR).first()
    admin = User(
        username="admin",
        password_hash=hash_password("admin123"),
        full_name="System Administrator",
        email="admin@retailflow.local",
        is_active=True,
        must_change_password=True,
    )
    admin.roles.append(admin_role)
    session.add(admin)

    # Create demo cashier
    cashier_role = session.query(Role).filter(Role.code == UserRoleEnum.CASHIER).first()
    cashier = User(
        username="cashier",
        password_hash=hash_password("cashier123"),
        full_name="Demo Cashier",
        is_active=True,
    )
    cashier.roles.append(cashier_role)
    session.add(cashier)

    # Create demo manager
    manager_role = session.query(Role).filter(Role.code == UserRoleEnum.MANAGER).first()
    manager = User(
        username="manager",
        password_hash=hash_password("manager123"),
        full_name="Demo Manager",
        is_active=True,
    )
    manager.roles.append(manager_role)
    session.add(manager)

    session.flush()
    logger.info(f"Seeded {len(perm_map)} permissions, {len(UserRoleEnum)} roles, 3 users.")

if __name__ == "__main__":
    from app.bootstrap import bootstrap, shutdown
    from infrastructure.database.session import create_session
    bootstrap()
    session = create_session()
    try:
        seed_auth(session)
        session.commit()
        print("Seeding complete!")
    except Exception as e:
        session.rollback()
        print(f"Seeding failed: {e}")
        raise
    finally:
        session.close()
        shutdown()
