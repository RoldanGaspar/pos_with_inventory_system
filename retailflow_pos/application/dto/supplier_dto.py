"""
RetailFlow POS - Supplier & Vendor Data Transfer Objects
Data structures for wholesale supplier management, contact information, and payment terms.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class SupplierResponseDTO:
    """Full representation of a wholesale supplier."""
    id: int
    code: str
    name: str
    contact_person: Optional[str]
    phone: str
    email: Optional[str]
    address: Optional[str]
    payment_terms: str
    tax_id: Optional[str]
    notes: Optional[str]
    is_active: bool
    created_at: str


@dataclass(frozen=True)
class CreateSupplierDTO:
    """Payload for registering a new wholesale vendor."""
    code: str
    name: str
    phone: str
    contact_person: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    payment_terms: str = "NET_30"
    tax_id: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True


@dataclass(frozen=True)
class UpdateSupplierDTO:
    """Payload for updating an existing wholesale vendor."""
    code: str
    name: str
    phone: str
    contact_person: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    payment_terms: str = "NET_30"
    tax_id: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True


@dataclass(frozen=True)
class SupplierFilterDTO:
    """Query parameters for searching suppliers."""
    keyword: Optional[str] = None
    payment_terms: Optional[str] = None
    is_active: Optional[bool] = None
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class SupplierSearchResultDTO:
    """Paginated search results of suppliers."""
    items: List[SupplierResponseDTO]
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
class SupplierMetricsDTO:
    """Aggregate counts for suppliers."""
    total_suppliers: int
    active_suppliers: int
    credit_terms_count: int
    cod_count: int
