"""
RetailFlow POS - Product & Catalog Seeder
Creates demo categories, brands, units, products, barcodes, and inventory on first run.
Idempotent: skips if products already exist.
"""

import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from app.constants import Status, TaxType
from infrastructure.database.models.inventory import Inventory
from infrastructure.database.models.product import Brand, Category, Product, ProductBarcode, Unit

logger = logging.getLogger("retailflow.database")


def _seed_categories(session: Session) -> dict:
    data = {
        "Beverages": None,
        "Snacks": None,
        "Dairy": None,
        "Personal Care": None,
        "Household": None,
    }
    result = {}
    for name in data:
        cat = session.query(Category).filter(Category.name == name).first()
        if cat is None:
            cat = Category(name=name, status=Status.ACTIVE)
            session.add(cat)
            session.flush()
        result[name] = cat
    return result


def _seed_brands(session: Session) -> dict:
    names = ["Coca-Cola", "Nestle", "Unilever", "Procter & Gamble", "Generic"]
    result = {}
    for name in names:
        brand = session.query(Brand).filter(Brand.name == name).first()
        if brand is None:
            brand = Brand(name=name, status=Status.ACTIVE)
            session.add(brand)
            session.flush()
        result[name] = brand
    return result


def _seed_units(session: Session) -> dict:
    data = [
        ("Piece", "pc"),
        ("Box", "box"),
        ("Pack", "pk"),
        ("Bottle", "btl"),
        ("Kilogram", "kg"),
    ]
    result = {}
    for name, abbr in data:
        unit = session.query(Unit).filter(Unit.name == name).first()
        if unit is None:
            unit = Unit(name=name, abbreviation=abbr)
            session.add(unit)
            session.flush()
        result[name] = unit
    return result


def _create_product(
    session: Session,
    sku: str,
    name: str,
    category: Category,
    brand: Brand,
    unit: Unit,
    cost: str,
    price: str,
    barcode: str,
    quantity_on_hand: int,
    reorder_level: int,
) -> None:
    product = Product(
        sku=sku,
        name=name,
        category_id=category.id,
        brand_id=brand.id,
        base_unit_id=unit.id,
        cost_price=Decimal(cost),
        selling_price=Decimal(price),
        tax_type=TaxType.VAT,
        status=Status.ACTIVE,
        reorder_level=reorder_level,
    )
    session.add(product)
    session.flush()
    session.add(ProductBarcode(product_id=product.id, barcode=barcode, is_primary=True))
    session.add(
        Inventory(
            product_id=product.id,
            quantity_on_hand=quantity_on_hand,
            quantity_allocated=0,
        )
    )


def seed_products(session: Session) -> None:
    """Seed demo catalog data if products do not already exist."""
    existing = session.query(Product).first()
    if existing:
        logger.info("Product catalog already seeded, skipping.")
        return

    logger.info("Seeding product catalog...")

    categories = _seed_categories(session)
    brands = _seed_brands(session)
    units = _seed_units(session)

    demo_products = [
        # sku, name, category, brand, unit, cost, price, barcode, qty, reorder
        (
            "BEV-001",
            "Coca-Cola 1.5L",
            categories["Beverages"],
            brands["Coca-Cola"],
            units["Bottle"],
            "35.00",
            "55.00",
            "4800010000017",
            150,
            24,
        ),
        (
            "BEV-002",
            "Nescafe 3-in-1 (10s)",
            categories["Beverages"],
            brands["Nestle"],
            units["Pack"],
            "48.00",
            "68.00",
            "4800010000024",
            80,
            20,
        ),
        (
            "SNK-001",
            "Piattos Cheese 40g",
            categories["Snacks"],
            brands["Generic"],
            units["Piece"],
            "12.00",
            "18.00",
            "4800010000031",
            12,
            20,
        ),
        (
            "SNK-002",
            "Nova Multigrain 78g",
            categories["Snacks"],
            brands["Generic"],
            units["Piece"],
            "28.00",
            "35.00",
            "4800010000048",
            0,
            15,
        ),
        (
            "DRY-001",
            "Bear Brand Powdered Milk 33g",
            categories["Dairy"],
            brands["Nestle"],
            units["Piece"],
            "9.00",
            "13.00",
            "4800010000055",
            300,
            50,
        ),
        (
            "PCR-001",
            "Safeguard Soap 60g",
            categories["Personal Care"],
            brands["Procter & Gamble"],
            units["Piece"],
            "28.00",
            "36.00",
            "4800010000062",
            5,
            10,
        ),
    ]

    for args in demo_products:
        _create_product(session, *args)

    session.flush()
    logger.info(f"Seeded {len(demo_products)} products.")


if __name__ == "__main__":
    from app.bootstrap import bootstrap, shutdown
    from infrastructure.database.session import create_session

    bootstrap()
    session = create_session()
    try:
        seed_products(session)
        session.commit()
        print("Product seeding complete!")
    except Exception as e:
        session.rollback()
        print(f"Seeding failed: {e}")
        raise
    finally:
        session.close()
        shutdown()
