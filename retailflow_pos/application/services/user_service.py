"""
RetailFlow POS - User & Staff Management Service
Coordinates user registration, profile updates, password resets, account locking,
and role assignments with audit trail logging.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from application.dto.user_dto import (
    CreateUserDTO,
    RoleDTO,
    UpdateUserDTO,
    UserMetricsDTO,
    UserResponseDTO,
)
from app.config import settings
from domain.exceptions import (
    AuthorizationError,
    DomainError,
    RetailFlowError,
    ValidationError,
)
from infrastructure.database.models.auth import Role, User
from infrastructure.database.repositories.auth import (
    AuditLogRepository,
    RoleRepository,
    UserRepository,
)
from infrastructure.security.hashing import (
    hash_password,
    validate_password_strength,
)

logger = logging.getLogger("retailflow.users")


class UserService:
    """Application service for managing staff users, roles, and account security."""

    def __init__(self, session: Session):
        self._session = session
        self._user_repo = UserRepository(session)
        self._role_repo = RoleRepository(session)
        self._audit_repo = AuditLogRepository(session)

    # ─── Query Operations ───

    def get_users(
        self,
        keyword: Optional[str] = None,
        role_code: Optional[str] = None,
        status: Optional[str] = None,
        actor: Optional[User] = None,
    ) -> List[UserResponseDTO]:
        """Fetch users matching optional filters."""
        query = self._session.query(User)

        if keyword:
            kw = f"%{keyword.strip()}%"
            query = query.filter(
                (User.username.ilike(kw))
                | (User.full_name.ilike(kw))
                | (User.email.ilike(kw))
            )

        if role_code:
            query = query.filter(User.roles.any(Role.code == role_code))

        if status:
            if status == "locked":
                query = query.filter(User.is_locked == True)
            elif status == "active":
                query = query.filter(User.is_active == True, User.is_locked == False)
            elif status == "inactive":
                query = query.filter(User.is_active == False)

        users = query.order_by(User.id.asc()).all()
        return [self._to_dto(u) for u in users]

    def get_user(self, user_id: int, actor: Optional[User] = None) -> UserResponseDTO:
        """Fetch a specific user by ID."""
        user = self._session.get(User, user_id)
        if not user:
            raise ValidationError(f"User with ID {user_id} not found.")
        return self._to_dto(user)

    def get_roles(self, actor: Optional[User] = None) -> List[RoleDTO]:
        """Fetch all available roles in the system."""
        roles = self._session.query(Role).order_by(Role.id.asc()).all()
        return [
            RoleDTO(
                id=r.id,
                name=r.name,
                code=r.code,
                description=r.description,
            )
            for r in roles
        ]

    def get_metrics(self, actor: Optional[User] = None) -> UserMetricsDTO:
        """Fetch aggregate staff metrics."""
        total_users = self._session.query(User).count()
        active_users = self._session.query(User).filter(User.is_active == True, User.is_locked == False).count()
        locked_users = self._session.query(User).filter(User.is_locked == True).count()
        roles_count = self._session.query(Role).count()

        return UserMetricsDTO(
            total_users=total_users,
            active_users=active_users,
            locked_users=locked_users,
            roles_count=roles_count,
        )

    # ─── Mutation Operations ───

    def create_user(self, dto: CreateUserDTO, actor: Optional[User] = None) -> UserResponseDTO:
        """Register a new staff user."""
        username = dto.username.strip()
        if not username:
            raise ValidationError("Username cannot be empty.")

        existing = self._user_repo.get_by_username(username)
        if existing:
            raise ValidationError(f"Username '{username}' already exists.")

        # Password validation
        is_valid, msg = validate_password_strength(dto.password)
        if not is_valid:
            raise ValidationError(msg)

        pw_hash = hash_password(dto.password)

        user = User(
            username=username,
            full_name=dto.full_name.strip(),
            password_hash=pw_hash,
            email=dto.email.strip() if dto.email else None,
            phone=dto.phone.strip() if dto.phone else None,
            is_active=(dto.status != "inactive"),
            is_locked=False,
            must_change_password=dto.must_change_password,
            status=dto.status,
        )

        # Attach role
        if dto.role_code:
            role = self._role_repo.get_by_code(dto.role_code)
            if role:
                user.roles.append(role)

        self._session.add(user)
        self._session.commit()
        self._session.refresh(user)

        self._audit_repo.log_action(
            user_id=actor.id if actor else None,
            username=actor.username if actor else "system",
            action="CREATE_USER",
            module="users",
            record_type="user",
            record_id=user.id,
            new_value=f"Created user {user.username} with role {dto.role_code}",
        )
        self._session.commit()

        logger.info(f"Created staff user: {user.username} (ID: {user.id})")
        return self._to_dto(user)

    def update_user(self, user_id: int, dto: UpdateUserDTO, actor: Optional[User] = None) -> UserResponseDTO:
        """Update staff profile details and role."""
        user = self._session.get(User, user_id)
        if not user:
            raise ValidationError(f"User with ID {user_id} not found.")

        user.full_name = dto.full_name.strip()
        user.email = dto.email.strip() if dto.email else None
        user.phone = dto.phone.strip() if dto.phone else None
        user.status = dto.status
        user.is_active = (dto.status != "inactive")

        if dto.role_code:
            role = self._role_repo.get_by_code(dto.role_code)
            if role:
                user.roles = [role]

        self._session.commit()
        self._session.refresh(user)

        self._audit_repo.log_action(
            user_id=actor.id if actor else None,
            username=actor.username if actor else "system",
            action="UPDATE_USER",
            module="users",
            record_type="user",
            record_id=user.id,
            new_value=f"Updated profile for {user.username}",
        )
        self._session.commit()

        logger.info(f"Updated staff user: {user.username} (ID: {user.id})")
        return self._to_dto(user)

    def reset_password(self, user_id: int, new_password: str, actor: Optional[User] = None) -> None:
        """Reset staff password."""
        user = self._session.get(User, user_id)
        if not user:
            raise ValidationError(f"User with ID {user_id} not found.")

        is_valid, msg = validate_password_strength(new_password)
        if not is_valid:
            raise ValidationError(msg)

        new_hash = hash_password(new_password)
        self._user_repo.change_password(user, new_hash)
        user.is_locked = False
        user.failed_login_count = 0
        user.must_change_password = True
        self._session.commit()

        self._audit_repo.log_action(
            user_id=actor.id if actor else None,
            username=actor.username if actor else "system",
            action="RESET_PASSWORD",
            module="users",
            record_type="user",
            record_id=user.id,
            new_value=f"Reset password for {user.username}",
        )
        self._session.commit()
        logger.info(f"Reset password for user: {user.username}")

    def toggle_lock(self, user_id: int, lock: bool, actor: Optional[User] = None) -> bool:
        """Lock or unlock a staff account."""
        user = self._session.get(User, user_id)
        if not user:
            raise ValidationError(f"User with ID {user_id} not found.")

        user.is_locked = lock
        if not lock:
            user.failed_login_count = 0
            user.locked_until = None

        self._session.commit()

        self._audit_repo.log_action(
            user_id=actor.id if actor else None,
            username=actor.username if actor else "system",
            action="LOCK_USER" if lock else "UNLOCK_USER",
            module="users",
            record_type="user",
            record_id=user.id,
            new_value=f"{'Locked' if lock else 'Unlocked'} account {user.username}",
        )
        self._session.commit()
        logger.info(f"{'Locked' if lock else 'Unlocked'} user: {user.username}")
        return user.is_locked

    # ─── Internal Helpers ───

    def _to_dto(self, user: User) -> UserResponseDTO:
        role_names = [r.name for r in user.roles]
        role_codes = [r.code for r in user.roles]
        primary_role = role_names[0] if role_names else "Staff"

        last_login = None
        if user.last_login_at:
            last_login = user.last_login_at.strftime("%b %d, %Y · %I:%M %p")

        created = user.created_at.strftime("%b %d, %Y") if user.created_at else "N/A"

        return UserResponseDTO(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            email=user.email,
            phone=user.phone,
            roles=role_names,
            role_codes=role_codes,
            primary_role=primary_role,
            is_active=user.is_active,
            is_locked=user.is_locked,
            must_change_password=user.must_change_password,
            last_login_at=last_login,
            status="locked" if user.is_locked else ("active" if user.is_active else "inactive"),
            created_at=created,
        )
