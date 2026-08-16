"""
RetailFlow POS - Purchasing & Purchase Order Application Service
Coordinates purchase order issuing, item management, automated stock receiving, and audit logging.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from application.dto.purchasing_dto import (
    CreatePurchaseOrderDTO,
    PurchaseOrderFilterDTO,
    PurchaseOrderItemDTO,
    PurchaseOrderResponseDTO,
    POSearchResultDTO,
    PurchasingMetricsDTO,
)
from domain.exceptions import ValidationError
from infrastructure.database.models.auth import User
from infrastructure.database.models.inventory import Inventory
from infrastructure.database.models.product import Product
from infrastructure.database.models.purchasing import PurchaseOrder, PurchaseOrderItem
from infrastructure.database.models.supplier import Supplier
from infrastructure.database.repositories.auth import AuditLogRepository

logger = logging.getLogger("retailflow.purchasing")


class PurchasingService:
    """Application service for managing purchase orders and receiving wholesale stock."""

    def __init__(self, session: Session):
        self._session = session
        self._audit_repo = AuditLogRepository(session)

    # ─── Query Operations ───

    def search(
        self,
        filters: PurchaseOrderFilterDTO,
        actor: Optional[User] = None,
    ) -> POSearchResultDTO:
        """Search purchase orders matching criteria with pagination."""
        query = self._session.query(PurchaseOrder).join(Supplier)

        if filters.keyword:
            kw = f"%{filters.keyword.strip()}%"
            query = query.filter(
                (PurchaseOrder.po_number.ilike(kw))
                | (Supplier.name.ilike(kw))
                | (Supplier.code.ilike(kw))
                | (PurchaseOrder.notes.ilike(kw))
                | (PurchaseOrder.items.any(PurchaseOrderItem.product_name.ilike(kw)))
            )

        if filters.status:
            query = query.filter(PurchaseOrder.status.ilike(filters.status))

        if filters.supplier_id:
            query = query.filter(PurchaseOrder.supplier_id == filters.supplier_id)

        total = query.count()

        offset = (filters.page - 1) * filters.page_size
        orders = (
            query.order_by(PurchaseOrder.order_date.desc(), PurchaseOrder.id.desc())
            .offset(offset)
            .limit(filters.page_size)
            .all()
        )

        items = [self._to_dto(po) for po in orders]
        return POSearchResultDTO(
            items=items,
            total=total,
            page=filters.page,
            page_size=filters.page_size,
        )

    def get_po(self, po_id: int, actor: Optional[User] = None) -> PurchaseOrderResponseDTO:
        """Fetch purchase order by ID."""
        po = self._session.get(PurchaseOrder, po_id)
        if not po:
            raise ValidationError(f"Purchase order with ID {po_id} not found.")
        return self._to_dto(po)

    def get_po_by_number(self, po_number: str, actor: Optional[User] = None) -> Optional[PurchaseOrderResponseDTO]:
        """Fetch purchase order by PO number."""
        po = self._session.query(PurchaseOrder).filter(PurchaseOrder.po_number == po_number.strip().upper()).first()
        return self._to_dto(po) if po else None

    def get_metrics(self, actor: Optional[User] = None) -> PurchasingMetricsDTO:
        """Compute aggregate purchasing metrics."""
        total_pos = self._session.query(PurchaseOrder).count()
        pending = self._session.query(PurchaseOrder).filter(
            PurchaseOrder.status.in_(["ORDERED", "DRAFT"])
        ).count()
        received = self._session.query(PurchaseOrder).filter(
            PurchaseOrder.status == "RECEIVED"
        ).count()
        total_spent = self._session.query(
            func.coalesce(func.sum(PurchaseOrder.total_amount), 0)
        ).filter(PurchaseOrder.status != "CANCELLED").scalar()

        return PurchasingMetricsDTO(
            total_pos=total_pos,
            pending_orders=pending,
            received_orders=received,
            total_purchases_spent=Decimal(total_spent),
        )

    def generate_next_po_number(self) -> str:
        """Generate formatted sequence PO number (e.g. PO-20260815-0001)."""
        today_str = datetime.utcnow().strftime("%Y%m%d")
        count_today = (
            self._session.query(PurchaseOrder)
            .filter(PurchaseOrder.po_number.like(f"PO-{today_str}-%"))
            .count()
        )
        return f"PO-{today_str}-{(count_today + 1):04d}"

    # ─── Mutation Operations ───

    def create_po(self, dto: CreatePurchaseOrderDTO, actor: Optional[User] = None) -> PurchaseOrderResponseDTO:
        """Issue or draft a new purchase order."""
        supplier = self._session.get(Supplier, dto.supplier_id)
        if not supplier:
            raise ValidationError(f"Supplier with ID {dto.supplier_id} not found.")

        if not dto.items:
            raise ValidationError("Purchase order must contain at least one product line item.")

        po_number = self.generate_next_po_number()

        # Compute line items & totals
        subtotal = Decimal("0.00")
        po_items = []

        for item_dto in dto.items:
            product = self._session.get(Product, item_dto.product_id)
            if not product:
                raise ValidationError(f"Product with ID {item_dto.product_id} not found.")

            if item_dto.quantity <= 0:
                raise ValidationError(f"Quantity for product '{product.name}' must be greater than 0.")

            unit_cost = Decimal(str(item_dto.unit_cost))
            line_subtotal = unit_cost * Decimal(item_dto.quantity)
            subtotal += line_subtotal

            po_item = PurchaseOrderItem(
                product_id=product.id,
                product_name=product.name,
                quantity_ordered=item_dto.quantity,
                quantity_received=0,
                unit_cost=unit_cost,
                subtotal=line_subtotal,
            )
            po_items.append(po_item)

        tax_amount = Decimal("0.00")
        total_amount = subtotal + tax_amount

        exp_delivery = None
        if dto.expected_delivery:
            try:
                exp_delivery = datetime.fromisoformat(dto.expected_delivery)
            except Exception:
                pass

        po = PurchaseOrder(
            po_number=po_number,
            supplier_id=supplier.id,
            order_date=datetime.utcnow(),
            expected_delivery=exp_delivery,
            status=dto.status.upper(),
            subtotal=subtotal,
            tax_amount=tax_amount,
            total_amount=total_amount,
            payment_terms=dto.payment_terms.upper(),
            notes=dto.notes.strip() if dto.notes else None,
            created_by_id=actor.id if actor else None,
        )
        po.items = po_items

        self._session.add(po)
        self._session.commit()
        self._session.refresh(po)

        self._audit_repo.log_action(
            user_id=actor.id if actor else None,
            username=actor.username if actor else "system",
            action="CREATE_PURCHASE_ORDER",
            module="purchasing",
            record_type="purchase_order",
            record_id=po.id,
            new_value=f"Created PO {po.po_number} for {supplier.name} (Total: ₱{total_amount:,.2f})",
        )
        self._session.commit()

        logger.info(f"Created purchase order: {po.po_number} (Total: ₱{total_amount})")
        return self._to_dto(po)

    def receive_stock(self, po_id: int, actor: Optional[User] = None) -> PurchaseOrderResponseDTO:
        """Receive all line items in a purchase order and increment inventory stock on hand."""
        po = self._session.get(PurchaseOrder, po_id)
        if not po:
            raise ValidationError(f"Purchase order with ID {po_id} not found.")

        if po.status == "RECEIVED":
            raise ValidationError(f"Purchase order {po.po_number} has already been received.")

        if po.status == "CANCELLED":
            raise ValidationError(f"Cannot receive stock for a cancelled purchase order.")

        # Update inventory for each line item
        received_items_summary = []
        for item in po.items:
            inventory = self._session.query(Inventory).filter(Inventory.product_id == item.product_id).first()
            if not inventory:
                inventory = Inventory(product_id=item.product_id, quantity_on_hand=0)
                self._session.add(inventory)
                self._session.flush()

            old_qty = inventory.quantity_on_hand
            inventory.quantity_on_hand += item.quantity_ordered
            item.quantity_received = item.quantity_ordered
            received_items_summary.append(f"{item.product_name}: {old_qty} -> {inventory.quantity_on_hand}")

        po.status = "RECEIVED"
        po.received_at = datetime.utcnow()
        po.received_by_id = actor.id if actor else None

        self._session.commit()
        self._session.refresh(po)

        self._audit_repo.log_action(
            user_id=actor.id if actor else None,
            username=actor.username if actor else "system",
            action="RECEIVE_PURCHASE_ORDER",
            module="purchasing",
            record_type="purchase_order",
            record_id=po.id,
            previous_value="Status: ORDERED",
            new_value=f"Received PO {po.po_number} - Stock updated: {', '.join(received_items_summary[:3])}",
        )
        self._session.commit()

        logger.info(f"Received purchase order: {po.po_number} and updated product stock")
        return self._to_dto(po)

    def cancel_po(self, po_id: int, reason: Optional[str] = None, actor: Optional[User] = None) -> PurchaseOrderResponseDTO:
        """Cancel an open purchase order."""
        po = self._session.get(PurchaseOrder, po_id)
        if not po:
            raise ValidationError(f"Purchase order with ID {po_id} not found.")

        if po.status == "RECEIVED":
            raise ValidationError("Cannot cancel a purchase order that has already been received.")

        po.status = "CANCELLED"
        self._session.commit()
        self._session.refresh(po)

        self._audit_repo.log_action(
            user_id=actor.id if actor else None,
            username=actor.username if actor else "system",
            action="CANCEL_PURCHASE_ORDER",
            module="purchasing",
            record_type="purchase_order",
            record_id=po.id,
            reason=reason,
            new_value=f"Cancelled PO {po.po_number}",
        )
        self._session.commit()

        logger.info(f"Cancelled purchase order: {po.po_number}")
        return self._to_dto(po)

    def _to_dto(self, po: PurchaseOrder) -> PurchaseOrderResponseDTO:
        order_date_str = po.order_date.strftime("%b %d, %Y") if po.order_date else "N/A"
        exp_date_str = po.expected_delivery.strftime("%b %d, %Y") if po.expected_delivery else None
        rec_date_str = po.received_at.strftime("%b %d, %Y · %I:%M %p") if po.received_at else None

        items_dto = [
            PurchaseOrderItemDTO(
                id=it.id,
                product_id=it.product_id,
                product_name=it.product_name,
                quantity_ordered=it.quantity_ordered,
                quantity_received=it.quantity_received,
                unit_cost=it.unit_cost,
                subtotal=it.subtotal,
            )
            for it in po.items
        ]

        total_units = sum(it.quantity_ordered for it in po.items)

        return PurchaseOrderResponseDTO(
            id=po.id,
            po_number=po.po_number,
            supplier_id=po.supplier_id,
            supplier_name=po.supplier.name if po.supplier else "Unknown Supplier",
            supplier_code=po.supplier.code if po.supplier else "N/A",
            status=po.status,
            order_date=order_date_str,
            expected_delivery=exp_date_str,
            received_at=rec_date_str,
            subtotal=po.subtotal,
            tax_amount=po.tax_amount,
            total_amount=po.total_amount,
            payment_terms=po.payment_terms,
            notes=po.notes,
            items_count=len(po.items),
            total_units=total_units,
            items=items_dto,
        )
