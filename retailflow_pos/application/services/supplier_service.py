"""
RetailFlow POS - Supplier & Vendor Application Service
Coordinates supplier registration, code generation, payment term management, and audit logging.
"""

import logging
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from application.dto.supplier_dto import (
    CreateSupplierDTO,
    SupplierFilterDTO,
    SupplierMetricsDTO,
    SupplierResponseDTO,
    SupplierSearchResultDTO,
    UpdateSupplierDTO,
)
from domain.exceptions import ValidationError
from infrastructure.database.models.auth import User
from infrastructure.database.models.supplier import Supplier
from infrastructure.database.repositories.auth import AuditLogRepository

logger = logging.getLogger("retailflow.suppliers")


class SupplierService:
    """Application service for managing wholesale suppliers and vendors."""

    def __init__(self, session: Session):
        self._session = session
        self._audit_repo = AuditLogRepository(session)

    # ─── Query Operations ───

    def search(
        self,
        filters: SupplierFilterDTO,
        actor: Optional[User] = None,
    ) -> SupplierSearchResultDTO:
        """Search suppliers matching criteria with pagination."""
        query = self._session.query(Supplier)

        if filters.keyword:
            kw = f"%{filters.keyword.strip()}%"
            query = query.filter(
                (Supplier.code.ilike(kw))
                | (Supplier.name.ilike(kw))
                | (Supplier.contact_person.ilike(kw))
                | (Supplier.phone.ilike(kw))
                | (Supplier.email.ilike(kw))
                | (Supplier.address.ilike(kw))
                | (Supplier.tax_id.ilike(kw))
            )

        if filters.payment_terms:
            query = query.filter(Supplier.payment_terms.ilike(filters.payment_terms))

        if filters.is_active is not None:
            query = query.filter(Supplier.is_active == filters.is_active)

        total = query.count()

        offset = (filters.page - 1) * filters.page_size
        suppliers = (
            query.order_by(Supplier.code.asc(), Supplier.id.asc())
            .offset(offset)
            .limit(filters.page_size)
            .all()
        )

        items = [self._to_dto(s) for s in suppliers]
        return SupplierSearchResultDTO(
            items=items,
            total=total,
            page=filters.page,
            page_size=filters.page_size,
        )

    def get_supplier(self, supplier_id: int, actor: Optional[User] = None) -> SupplierResponseDTO:
        """Fetch supplier by ID."""
        supplier = self._session.get(Supplier, supplier_id)
        if not supplier:
            raise ValidationError(f"Supplier with ID {supplier_id} not found.")
        return self._to_dto(supplier)

    def get_supplier_by_code(self, code: str, actor: Optional[User] = None) -> Optional[SupplierResponseDTO]:
        """Fetch supplier by unique code."""
        supplier = self._session.query(Supplier).filter(Supplier.code == code.strip().upper()).first()
        return self._to_dto(supplier) if supplier else None

    def get_metrics(self, actor: Optional[User] = None) -> SupplierMetricsDTO:
        """Compute aggregate supplier statistics."""
        total = self._session.query(Supplier).count()
        active_count = self._session.query(Supplier).filter(Supplier.is_active == True).count()
        credit_count = self._session.query(Supplier).filter(
            Supplier.payment_terms.in_(["NET_30", "NET_60"])
        ).count()
        cod_count = self._session.query(Supplier).filter(Supplier.payment_terms == "COD").count()

        return SupplierMetricsDTO(
            total_suppliers=total,
            active_suppliers=active_count,
            credit_terms_count=credit_count,
            cod_count=cod_count,
        )

    def generate_next_code(self) -> str:
        """Generate next sequential supplier code."""
        max_id = self._session.query(func.coalesce(func.max(Supplier.id), 0)).scalar()
        return f"SUP-{(max_id + 1):03d}"

    # ─── Mutation Operations ───

    def create_supplier(self, dto: CreateSupplierDTO, actor: Optional[User] = None) -> SupplierResponseDTO:
        """Register a new wholesale supplier."""
        code = dto.code.strip().upper()
        name = dto.name.strip()
        phone = dto.phone.strip()

        if not code:
            code = self.generate_next_code()
        if not name:
            raise ValidationError("Supplier name cannot be empty.")
        if not phone:
            raise ValidationError("Phone number cannot be empty.")

        existing_code = self._session.query(Supplier).filter(Supplier.code == code).first()
        if existing_code:
            raise ValidationError(f"Supplier code '{code}' already exists.")

        supplier = Supplier(
            code=code,
            name=name,
            contact_person=dto.contact_person.strip() if dto.contact_person else None,
            phone=phone,
            email=dto.email.strip() if dto.email else None,
            address=dto.address.strip() if dto.address else None,
            payment_terms=dto.payment_terms.strip().upper(),
            tax_id=dto.tax_id.strip() if dto.tax_id else None,
            notes=dto.notes.strip() if dto.notes else None,
            is_active=dto.is_active,
        )

        self._session.add(supplier)
        self._session.commit()
        self._session.refresh(supplier)

        self._audit_repo.log_action(
            user_id=actor.id if actor else None,
            username=actor.username if actor else "system",
            action="CREATE_SUPPLIER",
            module="suppliers",
            record_type="supplier",
            record_id=supplier.id,
            new_value=f"Registered supplier {supplier.name} ({supplier.code})",
        )
        self._session.commit()

        logger.info(f"Created wholesale supplier: {supplier.name} (Code: {supplier.code})")
        return self._to_dto(supplier)

    def update_supplier(self, supplier_id: int, dto: UpdateSupplierDTO, actor: Optional[User] = None) -> SupplierResponseDTO:
        """Update supplier profile details."""
        supplier = self._session.get(Supplier, supplier_id)
        if not supplier:
            raise ValidationError(f"Supplier with ID {supplier_id} not found.")

        code = dto.code.strip().upper()
        name = dto.name.strip()
        phone = dto.phone.strip()

        if not code:
            raise ValidationError("Supplier code cannot be empty.")
        if not name:
            raise ValidationError("Supplier name cannot be empty.")
        if not phone:
            raise ValidationError("Phone number cannot be empty.")

        existing = self._session.query(Supplier).filter(Supplier.code == code, Supplier.id != supplier_id).first()
        if existing:
            raise ValidationError(f"Supplier code '{code}' is already assigned to another vendor.")

        supplier.code = code
        supplier.name = name
        supplier.contact_person = dto.contact_person.strip() if dto.contact_person else None
        supplier.phone = phone
        supplier.email = dto.email.strip() if dto.email else None
        supplier.address = dto.address.strip() if dto.address else None
        supplier.payment_terms = dto.payment_terms.strip().upper()
        supplier.tax_id = dto.tax_id.strip() if dto.tax_id else None
        supplier.notes = dto.notes.strip() if dto.notes else None
        supplier.is_active = dto.is_active

        self._session.commit()
        self._session.refresh(supplier)

        self._audit_repo.log_action(
            user_id=actor.id if actor else None,
            username=actor.username if actor else "system",
            action="UPDATE_SUPPLIER",
            module="suppliers",
            record_type="supplier",
            record_id=supplier.id,
            new_value=f"Updated profile for {supplier.name}",
        )
        self._session.commit()

        logger.info(f"Updated supplier: {supplier.name} (Code: {supplier.code})")
        return self._to_dto(supplier)

    def _to_dto(self, supplier: Supplier) -> SupplierResponseDTO:
        created = supplier.created_at.strftime("%b %d, %Y") if supplier.created_at else "N/A"
        return SupplierResponseDTO(
            id=supplier.id,
            code=supplier.code,
            name=supplier.name,
            contact_person=supplier.contact_person,
            phone=supplier.phone,
            email=supplier.email,
            address=supplier.address,
            payment_terms=supplier.payment_terms,
            tax_id=supplier.tax_id,
            notes=supplier.notes,
            is_active=supplier.is_active,
            created_at=created,
        )
