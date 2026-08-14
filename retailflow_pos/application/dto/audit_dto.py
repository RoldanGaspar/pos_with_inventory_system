"""
RetailFlow POS - Audit Log Data Transfer Objects
Data structures for system activity tracking, filter parameters, and audit summaries.
"""

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass(frozen=True)
class AuditLogResponseDTO:
    """Represents a single immutable audit log record."""
    id: int
    user_id: Optional[int]
    username: str
    action: str
    module: str
    record_type: Optional[str]
    record_id: Optional[int]
    previous_value: Optional[str]
    new_value: Optional[str]
    ip_address: Optional[str]
    reason: Optional[str]
    status: str
    created_at: str
    formatted_time: str


@dataclass(frozen=True)
class AuditFilterDTO:
    """Filter criteria for searching audit trail."""
    keyword: Optional[str] = None
    module: Optional[str] = None
    action: Optional[str] = None
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class AuditSearchResultDTO:
    """Paginated result of audit logs."""
    items: List[AuditLogResponseDTO]
    total: int
    page: int
    page_size: int

    @property
    def has_next(self) -> bool:
        return self.page * self.page_size < self.total

    @property
    def has_previous(self) -> bool:
        return self.page > 1


@dataclass(frozen=True)
class AuditMetricsDTO:
    """Aggregate statistics for audit activity."""
    total_logs: int
    auth_logs: int
    inventory_logs: int
    user_logs: int
