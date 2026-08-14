"""
RetailFlow POS - Wholesale Supplier Seeder
Populates realistic Philippine wholesale distributors, vendors, and payment terms.
Idempotent: skips if suppliers already exist.
"""

import logging
from sqlalchemy.orm import Session

from infrastructure.database.models.supplier import Supplier

logger = logging.getLogger("retailflow.database")

DEMO_SUPPLIERS = [
    {
        "code": "SUP-001",
        "name": "Coca-Cola Beverages Philippines, Inc.",
        "contact_person": "Eduardo Rodriguez",
        "phone": "+63 2 8888 1234",
        "email": "orders@coca-cola.com.ph",
        "address": "Taguig City, Metro Manila",
        "payment_terms": "NET_30",
        "tax_id": "000-123-456-000",
        "notes": "Primary distributor for carbonated soft drinks, juices, and bottled water.",
        "is_active": True,
    },
    {
        "code": "SUP-002",
        "name": "Universal Robina Corporation (URC)",
        "contact_person": "Carmela Mendoza",
        "phone": "+63 2 8633 7631",
        "email": "sales@urc.com.ph",
        "address": "Pasig City, Metro Manila",
        "payment_terms": "NET_30",
        "tax_id": "000-456-789-000",
        "notes": "Snacks (Piattos, Nova, Jack 'n Jill) and beverage supplier.",
        "is_active": True,
    },
    {
        "code": "SUP-003",
        "name": "Nestle Philippines, Inc.",
        "contact_person": "Ricardo Santos",
        "phone": "+63 2 8898 0001",
        "email": "ph.orders@nestle.com",
        "address": "Makati City, Metro Manila",
        "payment_terms": "NET_60",
        "tax_id": "000-987-654-000",
        "notes": "Coffee, milk, cereals, and dairy distribution network.",
        "is_active": True,
    },
    {
        "code": "SUP-004",
        "name": "Unilever Philippines",
        "contact_person": "Maria Cristina Gomez",
        "phone": "+63 2 8588 8800",
        "email": "distributor.ph@unilever.com",
        "address": "BGC, Taguig City",
        "payment_terms": "NET_30",
        "tax_id": "000-321-654-000",
        "notes": "Personal care, shampoo, soap, and home cleaning products.",
        "is_active": True,
    },
    {
        "code": "SUP-005",
        "name": "Procter & Gamble Philippines",
        "contact_person": "Arthur King Ramos",
        "phone": "+63 2 8894 7000",
        "email": "directsales.ph@pg.com",
        "address": "BGC, Taguig City",
        "payment_terms": "NET_30",
        "tax_id": "000-789-123-000",
        "notes": "Household and laundry detergent essentials (Ariel, Tide, Safeguard).",
        "is_active": True,
    },
    {
        "code": "SUP-006",
        "name": "San Miguel Food and Beverage, Inc.",
        "contact_person": "Felipe Villanueva",
        "phone": "+63 2 8632 2000",
        "email": "smfb.orders@sanmiguel.com.ph",
        "address": "Mandaluyong City, Metro Manila",
        "payment_terms": "NET_15",
        "tax_id": "000-654-987-000",
        "notes": "Dairy, butter, spreads (Magnolia, Purefoods), and beverages.",
        "is_active": True,
    },
    {
        "code": "SUP-007",
        "name": "Monde Nissin Corporation",
        "contact_person": "Rowena David",
        "phone": "+63 2 8737 1000",
        "email": "sales@mondenissin.com",
        "address": "Santa Rosa, Laguna",
        "payment_terms": "NET_30",
        "tax_id": "000-111-222-000",
        "notes": "Instant noodles (Lucky Me!) and bakery biscuits (SkyFlakes).",
        "is_active": True,
    },
    {
        "code": "SUP-008",
        "name": "Benguet Fresh Produce Cooperative",
        "contact_person": "Mang Jose Dela Cruz",
        "phone": "+63 917 555 4321",
        "email": "benguet.coop@gmail.com",
        "address": "La Trinidad, Benguet",
        "payment_terms": "COD",
        "tax_id": "123-888-999-000",
        "notes": "Direct farm supplier for fresh vegetables and highland fruits.",
        "is_active": True,
    },
    {
        "code": "SUP-009",
        "name": "NutriAsia, Inc.",
        "contact_person": "Danilo Fernandez",
        "phone": "+63 2 8667 1100",
        "email": "orders@nutriasia.com",
        "address": "Taguig City, Metro Manila",
        "payment_terms": "NET_30",
        "tax_id": "000-333-444-000",
        "notes": "Condiments and cooking sauces (Datu Puti, UFC, Silver Swan).",
        "is_active": True,
    },
    {
        "code": "SUP-010",
        "name": "Century Pacific Food, Inc.",
        "contact_person": "Leah Soriano",
        "phone": "+63 2 8633 8555",
        "email": "cannedgoods@centurypacific.com.ph",
        "address": "Ortigas Center, Pasig City",
        "payment_terms": "NET_30",
        "tax_id": "000-555-666-000",
        "notes": "Canned seafood, meat, and coconut products (Century Tuna, 555).",
        "is_active": True,
    },
]


def seed_suppliers(session: Session) -> None:
    """Seed demo wholesale distributors into database if empty."""
    existing_count = session.query(Supplier).count()
    if existing_count > 0:
        logger.info(f"Suppliers table already contains {existing_count} records. Skipping seeder.")
        return

    logger.info("Seeding demo wholesale suppliers & payment terms...")
    for data in DEMO_SUPPLIERS:
        supplier = Supplier(
            code=data["code"],
            name=data["name"],
            contact_person=data["contact_person"],
            phone=data["phone"],
            email=data["email"],
            address=data["address"],
            payment_terms=data["payment_terms"],
            tax_id=data["tax_id"],
            notes=data["notes"],
            is_active=data["is_active"],
        )
        session.add(supplier)

    session.flush()
    logger.info(f"Successfully seeded {len(DEMO_SUPPLIERS)} demo wholesale suppliers.")
