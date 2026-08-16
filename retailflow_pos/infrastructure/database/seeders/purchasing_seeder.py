"""
RetailFlow POS - Purchase Orders Seeder
Seeds demo purchase orders linked to wholesale suppliers and catalog products.
Idempotent: skips if purchase orders already exist.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session

from infrastructure.database.models.product import Product
from infrastructure.database.models.purchasing import PurchaseOrder, PurchaseOrderItem
from infrastructure.database.models.supplier import Supplier

logger = logging.getLogger("retailflow.database")


def seed_purchase_orders(session: Session) -> None:
    """Seed demo purchase orders if none exist."""
    existing_count = session.query(PurchaseOrder).count()
    if existing_count > 0:
        logger.info(f"Purchase orders table already contains {existing_count} records. Skipping seeder.")
        return

    suppliers = session.query(Supplier).all()
    products = session.query(Product).all()

    if not suppliers or not products:
        logger.warning("Cannot seed purchase orders: suppliers or products are missing.")
        return

    logger.info("Seeding demo purchase orders...")

    sup_map = {s.code: s for s in suppliers}
    prod_map = {p.sku: p for p in products}

    now = datetime.utcnow()

    demo_pos = [
        {
            "po_number": f"PO-{now.strftime('%Y%m%d')}-0001",
            "supplier_code": "SUP-001",  # Coca-Cola
            "order_date": now - timedelta(days=2),
            "expected_delivery": now + timedelta(days=2),
            "status": "ORDERED",
            "payment_terms": "NET_30",
            "notes": "Weekly beverage restocking delivery via Bay 1.",
            "items": [
                {"sku": "BEV-001", "qty": 48, "cost": Decimal("25.00")},
                {"sku": "BEV-002", "qty": 36, "cost": Decimal("26.00")},
                {"sku": "BEV-003", "qty": 24, "cost": Decimal("25.00")},
            ],
        },
        {
            "po_number": f"PO-{now.strftime('%Y%m%d')}-0002",
            "supplier_code": "SUP-002",  # URC
            "order_date": now - timedelta(days=5),
            "expected_delivery": now - timedelta(days=1),
            "status": "RECEIVED",
            "payment_terms": "NET_30",
            "notes": "Snacks and chips assortment order.",
            "received_at": now - timedelta(days=1),
            "items": [
                {"sku": "SNK-001", "qty": 60, "cost": Decimal("28.00")},
                {"sku": "SNK-002", "qty": 40, "cost": Decimal("30.00")},
            ],
        },
        {
            "po_number": f"PO-{now.strftime('%Y%m%d')}-0003",
            "supplier_code": "SUP-003",  # Nestle
            "order_date": now - timedelta(days=1),
            "expected_delivery": now + timedelta(days=4),
            "status": "ORDERED",
            "payment_terms": "NET_60",
            "notes": "Coffee and dairy replenishment.",
            "items": [
                {"sku": "DAI-001", "qty": 30, "cost": Decimal("42.00")},
                {"sku": "DAI-002", "qty": 50, "cost": Decimal("12.00")},
            ],
        },
    ]

    for pdata in demo_pos:
        sup = sup_map.get(pdata["supplier_code"]) or suppliers[0]
        subtotal = Decimal("0.00")
        items_objs = []

        for it in pdata["items"]:
            prod = prod_map.get(it["sku"])
            if not prod and products:
                prod = products[0]

            if prod:
                line_sub = it["cost"] * Decimal(it["qty"])
                subtotal += line_sub
                items_objs.append(
                    PurchaseOrderItem(
                        product_id=prod.id,
                        product_name=prod.name,
                        quantity_ordered=it["qty"],
                        quantity_received=it["qty"] if pdata["status"] == "RECEIVED" else 0,
                        unit_cost=it["cost"],
                        subtotal=line_sub,
                    )
                )

        if not items_objs and products:
            prod = products[0]
            line_sub = Decimal("25.00") * 20
            subtotal += line_sub
            items_objs.append(
                PurchaseOrderItem(
                    product_id=prod.id,
                    product_name=prod.name,
                    quantity_ordered=20,
                    quantity_received=20 if pdata["status"] == "RECEIVED" else 0,
                    unit_cost=Decimal("25.00"),
                    subtotal=line_sub,
                )
            )

        po = PurchaseOrder(
            po_number=pdata["po_number"],
            supplier_id=sup.id,
            order_date=pdata["order_date"],
            expected_delivery=pdata.get("expected_delivery"),
            status=pdata["status"],
            subtotal=subtotal,
            tax_amount=Decimal("0.00"),
            total_amount=subtotal,
            payment_terms=pdata["payment_terms"],
            notes=pdata["notes"],
            received_at=pdata.get("received_at"),
        )
        po.items = items_objs
        session.add(po)

    session.flush()
    logger.info(f"Successfully seeded {len(demo_pos)} demo purchase orders.")
