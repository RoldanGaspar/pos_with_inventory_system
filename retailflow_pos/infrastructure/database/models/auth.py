"""
RetailFlow POS - Authentication & User Models
SQLAlchemy ORM models for Users, Roles, Permissions, and security tracking.
"""
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Table, Enum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.models.base import Base, BaseEntity, TimestampMixin
from app.constants import Status, UserRole as UserRoleEnum


# ─── Association Tables ───

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)


# ─── Permission ───

class Permission(BaseEntity):
    """Fine-grained permission that can be assigned to roles."""

    __tablename__ = "permissions"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    roles: Mapped[List["Role"]] = relationship(
        "Role", secondary=role_permissions, back_populates="permissions"
    )

    def __repr__(self) -> str:
        return f"<Permission(code={self.code}, module={self.module})>"


# ─── Role ───

class Role(BaseEntity):
    """User role that aggregates permissions."""

    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    permissions: Mapped[List[Permission]] = relationship(
        "Permission", secondary=role_permissions, back_populates="roles"
    )
    users: Mapped[List["User"]] = relationship(
        "User", secondary=user_roles, back_populates="roles"
    )

    def has_permission(self, permission_code: str) -> bool:
        """Check if this role has a specific permission."""
        return any(p.code == permission_code for p in self.permissions)

    def __repr__(self) -> str:
        return f"<Role(code={self.code})>"


# ─── User ───

class User(BaseEntity):
    """Application user account."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    password_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    status: Mapped[str] = mapped_column(String(20), default=Status.ACTIVE, nullable=False)

    # Relationships
    roles: Mapped[List[Role]] = relationship(
        "Role", secondary=user_roles, back_populates="users"
    )
    sessions: Mapped[List["UserSession"]] = relationship("UserSession", back_populates="user")
    login_attempts: Mapped[List["LoginAttempt"]] = relationship("LoginAttempt", back_populates="user")

    def has_permission(self, permission_code: str) -> bool:
        """Check if this user has a specific permission via any of their roles."""
        for role in self.roles:
            if role.has_permission(permission_code):
                return True
        return False

    def is_admin(self) -> bool:
        return any(r.code == UserRoleEnum.ADMINISTRATOR for r in self.roles)

    def __repr__(self) -> str:
        return f"<User(username={self.username})>"


# ─── User Session ───

class UserSession(BaseEntity):
    """Active user session tracking."""

    __tablename__ = "user_sessions"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="sessions")

    def __repr__(self) -> str:
        return f"<UserSession(user_id={self.user_id})>"


# ─── Login Attempt ───

class LoginAttempt(BaseEntity):
    """Record of login attempts for auditing and lockout tracking."""

    __tablename__ = "login_attempts"

    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    user: Mapped[Optional[User]] = relationship("User", back_populates="login_attempts")

    def __repr__(self) -> str:
        return f"<LoginAttempt(username={self.username}, success={self.success})>"


# ─── Password History ───

class PasswordHistory(BaseEntity):
    """Stores previous password hashes to prevent reuse."""

    __tablename__ = "password_history"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    def __repr__(self) -> str:
        return f"<PasswordHistory(user_id={self.user_id})>"


# ─── Audit Log ───

class AuditLog(BaseEntity):
    """Immutable audit trail for all sensitive actions."""

    __tablename__ = "audit_logs"

    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    record_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    record_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    previous_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="success")

    def __repr__(self) -> str:
        return f"<AuditLog(action={self.action}, user={self.username})>"