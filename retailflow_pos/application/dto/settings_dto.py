"""
RetailFlow POS - Store Settings Data Transfer Objects
Strongly-typed, immutable DTO schemas for store profile, receipt preferences,
and sanitized system information.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class StoreSettingsDTO:
    """Read-only application projection of persisted StoreSettings."""

    id: int
    store_name: str
    store_address: Optional[str]
    contact_number: Optional[str]
    email: Optional[str]
    tin: Optional[str]
    logo_path: Optional[str]
    receipt_header: Optional[str]
    receipt_footer: Optional[str]
    paper_width: str
    show_store_address: bool
    show_contact: bool
    show_tin: bool
    show_tax_details: bool
    updated_by_id: Optional[int]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class UpdateStoreProfileDTO:
    """
    Input payload for updating store profile information.
    Excludes logo_path which is managed through dedicated logo commands.
    """

    store_name: str
    store_address: Optional[str] = None
    contact_number: Optional[str] = None
    email: Optional[str] = None
    tin: Optional[str] = None


@dataclass(frozen=True)
class UpdateReceiptPreferencesDTO:
    """Input payload for updating receipt formatting and display preferences."""

    receipt_header: Optional[str] = None
    receipt_footer: Optional[str] = None
    paper_width: str = "80mm"
    show_store_address: bool = True
    show_contact: bool = True
    show_tin: bool = True
    show_tax_details: bool = True


@dataclass(frozen=True)
class SystemInfoDTO:
    """Sanitized, read-only diagnostic and runtime environment information."""

    app_name: str
    app_version: str
    app_env: str
    database_type: str
    database_location: str
    timezone: str
    currency: str
    python_version: str
    pyside_version: str
    os_platform: str
    data_dir: str
    log_dir: str
    backup_dir: str
    export_dir: str
