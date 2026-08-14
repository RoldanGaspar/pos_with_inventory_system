"""
RetailFlow POS - User Data Transfer Objects
Data structures for user management, role assignments, and staff metrics.
"""

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass(frozen=True)
class RoleDTO:
    """Represents a security role in the system."""
    id: int
    name: str
    code: str
    description: Optional[str] = None


@dataclass(frozen=True)
class UserResponseDTO:
    """Full representation of a staff user account."""
    id: int
    username: str
    full_name: str
    email: Optional[str]
    phone: Optional[str]
    roles: List[str]
    role_codes: List[str]
    primary_role: str
    is_active: bool
    is_locked: bool
    must_change_password: bool
    last_login_at: Optional[str]
    status: str
    created_at: str


@dataclass(frozen=True)
class CreateUserDTO:
    """Payload for registering a new staff user."""
    username: str
    full_name: str
    password: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role_code: str = "cashier"
    must_change_password: bool = False
    status: str = "active"


@dataclass(frozen=True)
class UpdateUserDTO:
    """Payload for editing an existing staff user."""
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role_code: Optional[str] = None
    status: str = "active"


@dataclass(frozen=True)
class UserMetricsDTO:
    """Aggregate statistics for staff accounts."""
    total_users: int
    active_users: int
    locked_users: int
    roles_count: int
