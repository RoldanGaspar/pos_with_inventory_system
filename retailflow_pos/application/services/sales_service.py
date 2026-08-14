"""
RetailFlow POS - Sales Service
Coordinates sales checkout, stock deduction, payment processing, and transaction queries.
"""

import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from application.dto.sales_dto import (
    CheckoutRequestDTO,
    SaleLineItemDTO,
    SaleResponseDTO,
)
from domain.exceptions import (
    AuthorizationError,
    InsufficientStockError,
    PaymentError,
    ProductNotFoundError,
    ValidationError,
)
from infrastructure.database.models.auth import User
from infrastructure.database.models.sales import Payment, Sale, SaleLineItem
from infrastructure.database.repositories.auth import AuditLogRepository
from infrastructure.database.repositories.product import InventoryRepository, ProductRepository
from infrastructure.database.repositories.sale import SaleRepository
from shared.pagination import PaginatedResult

logger = logging.getLogger("retailflow.sales")

PERMISSION_PROCESS_SALE = "process_sale"
PERMISSION_VIEW_SALES = "view_sales"


class SalesService:
    """Handles checkout transactions and sales reporting."""

    def __init__(self, session: Session):
        self._session = session
        self.sale_repo = SaleRepository(session)
        self.product_repo = ProductRepository(session)
        self.inventory_repo = InventoryRepository(session)
        self.audit_repo = AuditLogRepository(session)

    def process_checkout(self, request: CheckoutRequestDTO, actor: User) -> SaleResponseDTO:
        """Validate cart, check stock, record sale, deduct inventory, and record payment."""
        if not request.items:
            raise ValidationError("Cannot checkout with an empty cart.")

        # Calculate totals
        subtotal = sum((item.subtotal for item in request.items), Decimal("0.00"))
        discount = request.discount_amount or Decimal("0.00")
        taxable = max(Decimal("0.00"), subtotal - discount)
        tax = (taxable * Decimal("0.12")).quantize(Decimal("0.01"))
        total_amount = max(Decimal("0.00"), subtotal - discount + tax)

        if request.amount_tendered < total_amount:
            raise PaymentError(
                f"Tendered amount ({request.amount_tendered:.2f}) is less than total due ({total_amount:.2f})."
            )

        change_given = request.amount_tendered - total_amount

        # Validate product stock and build line items
        line_items: list[SaleLineItem] = []
        for cart_item in request.items:
            product = self.product_repo.get_by_id(cart_item.product_id)
            if not product:
                raise ProductNotFoundError(f"Product id {cart_item.product_id} not found.")

            inv = self.inventory_repo.get_by_product_id(product.id)
            current_stock = inv.quantity_on_hand if inv else 0

            if current_stock < cart_item.quantity:
                raise InsufficientStockError(
                    f"Insufficient stock for '{product.name}'. Available: {current_stock}, Requested: {cart_item.quantity}."
                )

            # Deduct stock
            if inv:
                inv.quantity_on_hand -= cart_item.quantity

            line_items.append(
                SaleLineItem(
                    product_id=product.id,
                    product_name=product.name,
                    unit_price=cart_item.unit_price,
                    quantity=cart_item.quantity,
                    subtotal=cart_item.subtotal,
                )
            )

        # Create Sale header
        txn_number = self.sale_repo.generate_transaction_number()
        sale = Sale(
            transaction_number=txn_number,
            cashier_id=actor.id if actor else None,
            subtotal=subtotal,
            discount_amount=discount,
            tax_amount=tax,
            total_amount=total_amount,
            status="COMPLETED",
            payment_method=request.payment_method,
            items=line_items,
        )

        # Create Payment record
        payment = Payment(
            payment_method=request.payment_method,
            amount_paid=request.amount_tendered,
            change_given=change_given,
            reference_number=request.reference_number,
        )
        sale.payments.append(payment)

        self._session.add(sale)
        self._session.flush()

        if actor:
            self.audit_repo.log_action(
                user_id=actor.id,
                username=actor.username,
                action="SALE_COMPLETED",
                module="sales",
                record_type="sale",
                record_id=sale.id,
            )

        self._session.commit()
        logger.info(f"Sale completed successfully: {txn_number}, total={total_amount}")

        return self._to_response_dto(sale, payment)

    def search_sales(
        self,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResult[SaleResponseDTO]:
        result = self.sale_repo.search(keyword=keyword, status=status, page=page, page_size=page_size)
        items = [
            self._to_response_dto(s, s.payments[0] if s.payments else None) for s in result.items
        ]
        return PaginatedResult(items=items, total=result.total, page=page, page_size=result.page_size)

    def get_today_summary(self) -> tuple[Decimal, int]:
        return self.sale_repo.get_today_sales_summary()

    def get_top_selling_products(self, limit: int = 5) -> list[tuple[str, int, Decimal]]:
        return self.sale_repo.get_top_selling_products(limit=limit)

    def get_recent_sales(self, limit: int = 5) -> list[SaleResponseDTO]:
        sales = self.sale_repo.get_recent_sales(limit=limit)
        return [
            self._to_response_dto(s, s.payments[0] if s.payments else None) for s in sales
        ]

    def get_revenue_trend(self, days: int = 7) -> list[tuple[str, Decimal]]:
        return self.sale_repo.get_revenue_trend(days=days)

    def get_payment_method_breakdown(self) -> list[tuple[str, Decimal]]:
        return self.sale_repo.get_payment_method_breakdown()

    def _to_response_dto(self, sale: Sale, payment: Payment | None) -> SaleResponseDTO:
        item_dtos = [
            SaleLineItemDTO(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                unit_price=item.unit_price,
                quantity=item.quantity,
                subtotal=item.subtotal,
            )
            for item in sale.items
        ]

        return SaleResponseDTO(
            id=sale.id,
            transaction_number=sale.transaction_number,
            subtotal=sale.subtotal,
            discount_amount=sale.discount_amount,
            tax_amount=sale.tax_amount,
            total_amount=sale.total_amount,
            payment_method=sale.payment_method,
            amount_paid=payment.amount_paid if payment else sale.total_amount,
            change_given=payment.change_given if payment else Decimal("0.00"),
            status=sale.status,
            created_at=sale.created_at.strftime("%Y-%m-%d %H:%M:%S") if sale.created_at else "",
            items=item_dtos,
        )
