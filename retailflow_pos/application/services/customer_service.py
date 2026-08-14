"""
RetailFlow POS - Customer & Loyalty CRM Service
Coordinates customer registration, profile updates, loyalty points adjustments,
tier derivation, and audit logging.
"""

import logging
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from application.dto.customer_dto import (
    CreateCustomerDTO,
    CustomerFilterDTO,
    CustomerMetricsDTO,
    CustomerResponseDTO,
    CustomerSearchResultDTO,
    UpdateCustomerDTO,
)
from domain.exceptions import ValidationError
from infrastructure.database.models.auth import User
from infrastructure.database.models.customer import Customer
from infrastructure.database.repositories.auth import AuditLogRepository

logger = logging.getLogger("retailflow.customers")


class CustomerService:
    """Application service for managing customer profiles and loyalty rewards."""

    def __init__(self, session: Session):
        self._session = session
        self._audit_repo = AuditLogRepository(session)

    # ─── Query Operations ───

    def search(
        self,
        filters: CustomerFilterDTO,
        actor: Optional[User] = None,
    ) -> CustomerSearchResultDTO:
        """Search customer profiles matching criteria with pagination."""
        query = self._session.query(Customer)

        if filters.keyword:
            kw = f"%{filters.keyword.strip()}%"
            query = query.filter(
                (Customer.name.ilike(kw))
                | (Customer.phone.ilike(kw))
                | (Customer.email.ilike(kw))
                | (Customer.address.ilike(kw))
            )

        if filters.tier:
            query = query.filter(Customer.tier.ilike(filters.tier))

        if filters.is_active is not None:
            query = query.filter(Customer.is_active == filters.is_active)

        total = query.count()

        offset = (filters.page - 1) * filters.page_size
        customers = (
            query.order_by(Customer.total_spent.desc(), Customer.id.desc())
            .offset(offset)
            .limit(filters.page_size)
            .all()
        )

        items = [self._to_dto(c) for c in customers]
        return CustomerSearchResultDTO(
            items=items,
            total=total,
            page=filters.page,
            page_size=filters.page_size,
        )

    def get_customer(self, customer_id: int, actor: Optional[User] = None) -> CustomerResponseDTO:
        """Fetch customer profile by ID."""
        customer = self._session.get(Customer, customer_id)
        if not customer:
            raise ValidationError(f"Customer with ID {customer_id} not found.")
        return self._to_dto(customer)

    def get_customer_by_phone(self, phone: str, actor: Optional[User] = None) -> Optional[CustomerResponseDTO]:
        """Lookup customer by phone number."""
        customer = self._session.query(Customer).filter(Customer.phone == phone.strip()).first()
        return self._to_dto(customer) if customer else None

    def get_metrics(self, actor: Optional[User] = None) -> CustomerMetricsDTO:
        """Compute aggregate customer statistics."""
        total = self._session.query(Customer).count()
        loyalty_members = self._session.query(Customer).filter(Customer.loyalty_points > 0).count()
        total_pts = self._session.query(func.coalesce(func.sum(Customer.loyalty_points), 0)).scalar()
        total_revenue = self._session.query(func.coalesce(func.sum(Customer.total_spent), 0)).scalar()

        avg_spend = (Decimal(total_revenue) / Decimal(total)) if total > 0 else Decimal("0.00")

        return CustomerMetricsDTO(
            total_customers=total,
            loyalty_members=loyalty_members,
            total_points=int(total_pts),
            avg_spend=avg_spend,
        )

    # ─── Mutation Operations ───

    def create_customer(self, dto: CreateCustomerDTO, actor: Optional[User] = None) -> CustomerResponseDTO:
        """Register a new customer profile."""
        name = dto.name.strip()
        phone = dto.phone.strip()

        if not name:
            raise ValidationError("Customer name cannot be empty.")
        if not phone:
            raise ValidationError("Phone number cannot be empty.")

        existing = self._session.query(Customer).filter(Customer.phone == phone).first()
        if existing:
            raise ValidationError(f"A customer with phone number '{phone}' already exists.")

        customer = Customer(
            name=name,
            phone=phone,
            email=dto.email.strip() if dto.email else None,
            address=dto.address.strip() if dto.address else None,
            loyalty_points=max(0, dto.initial_points),
            notes=dto.notes.strip() if dto.notes else None,
            is_active=dto.is_active,
        )
        customer.tier = customer.calculate_tier()

        self._session.add(customer)
        self._session.commit()
        self._session.refresh(customer)

        self._audit_repo.log_action(
            user_id=actor.id if actor else None,
            username=actor.username if actor else "system",
            action="CREATE_CUSTOMER",
            module="customers",
            record_type="customer",
            record_id=customer.id,
            new_value=f"Registered customer {customer.name} ({customer.phone})",
        )
        self._session.commit()

        logger.info(f"Created customer: {customer.name} (ID: {customer.id})")
        return self._to_dto(customer)

    def update_customer(self, customer_id: int, dto: UpdateCustomerDTO, actor: Optional[User] = None) -> CustomerResponseDTO:
        """Update customer details."""
        customer = self._session.get(Customer, customer_id)
        if not customer:
            raise ValidationError(f"Customer with ID {customer_id} not found.")

        name = dto.name.strip()
        phone = dto.phone.strip()

        if not name:
            raise ValidationError("Customer name cannot be empty.")
        if not phone:
            raise ValidationError("Phone number cannot be empty.")

        existing = self._session.query(Customer).filter(Customer.phone == phone, Customer.id != customer_id).first()
        if existing:
            raise ValidationError(f"Phone number '{phone}' is already in use by another customer.")

        customer.name = name
        customer.phone = phone
        customer.email = dto.email.strip() if dto.email else None
        customer.address = dto.address.strip() if dto.address else None
        customer.notes = dto.notes.strip() if dto.notes else None
        customer.is_active = dto.is_active

        self._session.commit()
        self._session.refresh(customer)

        self._audit_repo.log_action(
            user_id=actor.id if actor else None,
            username=actor.username if actor else "system",
            action="UPDATE_CUSTOMER",
            module="customers",
            record_type="customer",
            record_id=customer.id,
            new_value=f"Updated profile for {customer.name}",
        )
        self._session.commit()

        logger.info(f"Updated customer: {customer.name} (ID: {customer.id})")
        return self._to_dto(customer)

    def adjust_points(
        self,
        customer_id: int,
        points_delta: int,
        reason: Optional[str] = None,
        actor: Optional[User] = None,
    ) -> CustomerResponseDTO:
        """Add or deduct customer loyalty points and recalculate tier."""
        customer = self._session.get(Customer, customer_id)
        if not customer:
            raise ValidationError(f"Customer with ID {customer_id} not found.")

        prev_points = customer.loyalty_points
        new_points = max(0, prev_points + points_delta)
        customer.loyalty_points = new_points
        customer.tier = customer.calculate_tier()

        self._session.commit()
        self._session.refresh(customer)

        delta_str = f"+{points_delta}" if points_delta > 0 else str(points_delta)
        self._audit_repo.log_action(
            user_id=actor.id if actor else None,
            username=actor.username if actor else "system",
            action="ADJUST_LOYALTY_POINTS",
            module="customers",
            record_type="customer",
            record_id=customer.id,
            previous_value=f"Points: {prev_points}",
            new_value=f"Points: {new_points} ({delta_str})",
            reason=reason,
        )
        self._session.commit()

        logger.info(f"Adjusted points for customer {customer.name}: {prev_points} -> {new_points}")
        return self._to_dto(customer)

    def _to_dto(self, customer: Customer) -> CustomerResponseDTO:
        created = customer.created_at.strftime("%b %d, %Y") if customer.created_at else "N/A"
        return CustomerResponseDTO(
            id=customer.id,
            name=customer.name,
            phone=customer.phone,
            email=customer.email,
            address=customer.address,
            loyalty_points=customer.loyalty_points,
            tier=customer.tier,
            total_spent=customer.total_spent,
            total_visits=customer.total_visits,
            notes=customer.notes,
            is_active=customer.is_active,
            created_at=created,
        )
