"""
RetailFlow POS - Customer & Loyalty Seeder
Populates realistic Philippine customer profiles, loyalty tiers, and purchase history.
Idempotent: skips if customers already exist.
"""

import logging
from decimal import Decimal
from sqlalchemy.orm import Session

from infrastructure.database.models.customer import Customer

logger = logging.getLogger("retailflow.database")

DEMO_CUSTOMERS = [
    {
        "name": "Maria Santos",
        "phone": "+63 917 123 4567",
        "email": "maria.santos@gmail.com",
        "address": "Quezon City, Metro Manila",
        "loyalty_points": 1450,
        "tier": "platinum",
        "total_spent": Decimal("48520.00"),
        "total_visits": 32,
        "notes": "VIP Gold member, prefers Coca-Cola Zero and premium snacks.",
        "is_active": True,
    },
    {
        "name": "Juan Dela Cruz",
        "phone": "+63 918 555 7890",
        "email": "juan.delacruz@yahoo.com",
        "address": "Makati City, Metro Manila",
        "loyalty_points": 720,
        "tier": "gold",
        "total_spent": Decimal("18650.00"),
        "total_visits": 14,
        "notes": "Regular weekend grocery shopper.",
        "is_active": True,
    },
    {
        "name": "Ana Patricia Reyes",
        "phone": "+63 920 888 1122",
        "email": "ana.reyes@corp.ph",
        "address": "Pasig City, Metro Manila",
        "loyalty_points": 340,
        "tier": "silver",
        "total_spent": Decimal("7890.00"),
        "total_visits": 6,
        "notes": "Prefers Maya digital payments.",
        "is_active": True,
    },
    {
        "name": "Rodrigo Duterte Tan",
        "phone": "+63 922 345 6789",
        "email": "rodrigo.tan@outlook.com",
        "address": "Davao City, Davao del Sur",
        "loyalty_points": 1120,
        "tier": "platinum",
        "total_spent": Decimal("39400.00"),
        "total_visits": 28,
        "notes": "Wholesale beverage buyer.",
        "is_active": True,
    },
    {
        "name": "Liza Soberano Garcia",
        "phone": "+63 917 999 4321",
        "email": "liza.garcia@gmail.com",
        "address": "BGC, Taguig City",
        "loyalty_points": 880,
        "tier": "gold",
        "total_spent": Decimal("24150.00"),
        "total_visits": 18,
        "notes": "Personal care and household essentials regular.",
        "is_active": True,
    },
    {
        "name": "Gabriel Mercado",
        "phone": "+63 908 123 9876",
        "email": "gabriel.mercado@gmail.com",
        "address": "Cebu City, Cebu",
        "loyalty_points": 210,
        "tier": "silver",
        "total_spent": Decimal("4620.00"),
        "total_visits": 5,
        "notes": "Cash on pickup shopper.",
        "is_active": True,
    },
    {
        "name": "Kathryn Bernardo Lim",
        "phone": "+63 915 777 8899",
        "email": "kathryn.lim@gmail.com",
        "address": "Mandaluyong City",
        "loyalty_points": 650,
        "tier": "gold",
        "total_spent": Decimal("15300.00"),
        "total_visits": 11,
        "notes": "Loyalty points collector.",
        "is_active": True,
    },
    {
        "name": "Antonio Luna Diaz",
        "phone": "+63 919 444 3322",
        "email": "antonio.luna@gmail.com",
        "address": "San Fernando, Pampanga",
        "loyalty_points": 60,
        "tier": "bronze",
        "total_spent": Decimal("1850.00"),
        "total_visits": 2,
        "notes": "Walk-in new customer.",
        "is_active": True,
    },
    {
        "name": "Bea Alonzo Ramos",
        "phone": "+63 927 666 5544",
        "email": "bea.ramos@corp.ph",
        "address": "Alabang, Muntinlupa City",
        "loyalty_points": 1600,
        "tier": "platinum",
        "total_spent": Decimal("56200.00"),
        "total_visits": 42,
        "notes": "Corporate pantry account organizer.",
        "is_active": True,
    },
    {
        "name": "Carlo Aquino Fernandez",
        "phone": "+63 916 222 1133",
        "email": "carlo.aquino@yahoo.com",
        "address": "Marikina City",
        "loyalty_points": 45,
        "tier": "bronze",
        "total_spent": Decimal("950.00"),
        "total_visits": 1,
        "notes": "Snacks and beverages customer.",
        "is_active": True,
    },
    {
        "name": "Jasmine Curtis Smith",
        "phone": "+63 933 888 4455",
        "email": "jasmine.smith@gmail.com",
        "address": "Paranaque City",
        "loyalty_points": 420,
        "tier": "silver",
        "total_spent": Decimal("9450.00"),
        "total_visits": 8,
        "notes": "Frequently orders dairy and cold drinks.",
        "is_active": True,
    },
    {
        "name": "Danilo Cruz Morales",
        "phone": "+63 928 999 1234",
        "email": "danilo.morales@gmail.com",
        "address": "Caloocan City",
        "loyalty_points": 0,
        "tier": "bronze",
        "total_spent": Decimal("0.00"),
        "total_visits": 0,
        "notes": "Newly registered account.",
        "is_active": True,
    },
]


def seed_customers(session: Session) -> None:
    """Seed demo customers into the database if empty."""
    existing_count = session.query(Customer).count()
    if existing_count > 0:
        logger.info(f"Customers table already contains {existing_count} records. Skipping seeder.")
        return

    logger.info("Seeding demo customer profiles & loyalty rewards...")
    for data in DEMO_CUSTOMERS:
        customer = Customer(
            name=data["name"],
            phone=data["phone"],
            email=data["email"],
            address=data["address"],
            loyalty_points=data["loyalty_points"],
            tier=data["tier"],
            total_spent=data["total_spent"],
            total_visits=data["total_visits"],
            notes=data["notes"],
            is_active=data["is_active"],
        )
        session.add(customer)

    session.flush()
    logger.info(f"Successfully seeded {len(DEMO_CUSTOMERS)} demo customer profiles.")
