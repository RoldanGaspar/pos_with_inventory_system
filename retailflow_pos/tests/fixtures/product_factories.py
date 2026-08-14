"""
RetailFlow POS - Product Test Factories
factory-boy factories for catalog test data.
"""

from decimal import Decimal

import factory

from infrastructure.database.models.product import (
    Brand,
    Category,
    Product,
    ProductBarcode,
    Unit,
)


class CategoryFactory(factory.Factory):
    class Meta:
        model = Category

    name = factory.Sequence(lambda n: f"Category {n}")
    status = "active"


class BrandFactory(factory.Factory):
    class Meta:
        model = Brand

    name = factory.Sequence(lambda n: f"Brand {n}")
    status = "active"


class UnitFactory(factory.Factory):
    class Meta:
        model = Unit

    name = factory.Sequence(lambda n: f"Unit {n}")
    abbreviation = factory.Sequence(lambda n: f"u{n}")


class ProductFactory(factory.Factory):
    class Meta:
        model = Product

    sku = factory.Sequence(lambda n: f"SKU-{n:04d}")
    name = factory.Sequence(lambda n: f"Product {n}")
    cost_price = Decimal("10.00")
    selling_price = Decimal("20.00")
    status = "active"
    reorder_level = 0


class ProductBarcodeFactory(factory.Factory):
    class Meta:
        model = ProductBarcode

    barcode = factory.Sequence(lambda n: f"480000000000{n:04d}")
    is_primary = True
