"""
RetailFlow POS - Customer & Loyalty Data Transfer Objects
Data structures for customer CRM profiles, loyalty tier management, and metrics.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional


@dataclass(frozen=True)
class CustomerResponseDTO:
    """Full representation of a customer profile."""
    id: int
    name: str
    phone: str
    email: Optional[str]
    address: Optional[str]
    loyalty_points: int
    tier: str
    total_spent: Decimal
    total_visits: int
    notes: Optional[str]
    is_active: bool
    created_at: str


@dataclass(frozen=True)
class CreateCustomerDTO:
    """Payload for registering a new customer."""
    name: str
    phone: str
    email: Optional[str] = None
    address: Optional[str] = None
    initial_points: int = 0
    notes: Optional[str] = None
    is_active: bool = True


@dataclass(frozen=True)
class UpdateCustomerDTO:
    """Payload for updating an existing customer profile."""
    name: str
    phone: str
    email: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True


@dataclass(frozen=True)
class CustomerFilterDTO:
    """Query filters for searching customers."""
    keyword: Optional[str] = None
    tier: Optional[str] = None
    is_active: Optional[bool] = None
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class CustomerSearchResultDTO:
    """Paginated search results of customer profiles."""
    items: List[CustomerResponseDTO]
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
class CustomerMetricsDTO:
    """Aggregate statistics for customer base."""
    total_customers: int
    loyalty_members: int
    total_points: int
    avg_spend: Decimal
