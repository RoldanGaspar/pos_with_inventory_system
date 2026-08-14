"""
RetailFlow POS - Audit Log Query Service
Application service for querying immutable system activity logs, filtering by module/action,
and computing audit metrics.
"""

import logging
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from application.dto.audit_dto import (
    AuditFilterDTO,
    AuditLogResponseDTO,
    AuditMetricsDTO,
    AuditSearchResultDTO,
)
from infrastructure.database.models.auth import AuditLog, User
from infrastructure.database.repositories.auth import AuditLogRepository

logger = logging.getLogger("retailflow.audit")


class AuditService:
    """Service for searching and inspecting immutable system audit logs."""

    def __init__(self, session: Session):
        self._session = session
        self._audit_repo = AuditLogRepository(session)

    def search(
        self,
        filters: AuditFilterDTO,
        actor: Optional[User] = None,
    ) -> AuditSearchResultDTO:
        """Search audit logs matching filter parameters with pagination."""
        query = self._session.query(AuditLog)

        if filters.keyword:
            kw = f"%{filters.keyword.strip()}%"
            query = query.filter(
                (AuditLog.username.ilike(kw))
                | (AuditLog.action.ilike(kw))
                | (AuditLog.module.ilike(kw))
                | (AuditLog.new_value.ilike(kw))
                | (AuditLog.reason.ilike(kw))
                | (AuditLog.ip_address.ilike(kw))
            )

        if filters.module:
            query = query.filter(AuditLog.module.ilike(filters.module))

        if filters.action:
            query = query.filter(AuditLog.action.ilike(filters.action))

        total = query.count()

        offset = (filters.page - 1) * filters.page_size
        logs = (
            query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset(offset)
            .limit(filters.page_size)
            .all()
        )

        items = [self._to_dto(log) for log in logs]
        return AuditSearchResultDTO(
            items=items,
            total=total,
            page=filters.page,
            page_size=filters.page_size,
        )

    def get_metrics(self, actor: Optional[User] = None) -> AuditMetricsDTO:
        """Fetch high-level aggregate audit metrics."""
        total = self._session.query(AuditLog).count()
        auth_count = self._session.query(AuditLog).filter(AuditLog.module == "auth").count()
        inv_count = self._session.query(AuditLog).filter(
            AuditLog.module.in_(["inventory", "products"])
        ).count()
        user_count = self._session.query(AuditLog).filter(AuditLog.module == "users").count()

        return AuditMetricsDTO(
            total_logs=total,
            auth_logs=auth_count,
            inventory_logs=inv_count,
            user_logs=user_count,
        )

    def get_modules(self, actor: Optional[User] = None) -> List[str]:
        """Fetch distinct modules that have generated audit logs."""
        rows = self._session.query(AuditLog.module).distinct().all()
        return sorted([r[0] for r in rows if r[0]])

    def get_actions(self, actor: Optional[User] = None) -> List[str]:
        """Fetch distinct action names recorded."""
        rows = self._session.query(AuditLog.action).distinct().all()
        return sorted([r[0] for r in rows if r[0]])

    def _to_dto(self, log: AuditLog) -> AuditLogResponseDTO:
        created_str = log.created_at.isoformat() if log.created_at else ""
        formatted = (
            log.created_at.strftime("%b %d, %Y · %I:%M:%S %p")
            if log.created_at
            else "N/A"
        )

        return AuditLogResponseDTO(
            id=log.id,
            user_id=log.user_id,
            username=log.username,
            action=log.action,
            module=log.module,
            record_type=log.record_type,
            record_id=log.record_id,
            previous_value=log.previous_value,
            new_value=log.new_value,
            ip_address=log.ip_address,
            reason=log.reason,
            status=log.status or "success",
            created_at=created_str,
            formatted_time=formatted,
        )
