"""
RetailFlow POS - Authentication Repositories
Specialized repository queries for users, roles, permissions.
"""
from datetime import datetime, timedelta
from typing import Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import and_

from infrastructure.database.models.auth import (
    User, Role, Permission, UserSession, LoginAttempt, PasswordHistory, AuditLog
)
from infrastructure.database.repositories.base import SqlAlchemyRepository
from infrastructure.security.hashing import hash_password, verify_password
from app.config import settings
from app.constants import Status as StatusEnum


class UserRepository(SqlAlchemyRepository[User, int]):
    """Repository for User entities with auth-specific queries."""

    def __init__(self, session: Session):
        super().__init__(session, User)

    def get_by_username(self, username: str) -> Optional[User]:
        return self._session.query(User).filter(
            User.username == username
        ).first()

    def get_active_users(self, skip: int = 0, limit: int = 100) -> List[User]:
        return self._session.query(User).filter(
            User.is_active == True
        ).offset(skip).limit(limit).all()

    def record_login_attempt(
        self,
        username: str,
        success: bool,
        ip_address: Optional[str] = None,
        failure_reason: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> LoginAttempt:
        attempt = LoginAttempt(
            username=username,
            user_id=user_id,
            ip_address=ip_address,
            success=success,
            failure_reason=failure_reason,
        )
        self._session.add(attempt)
        self._session.flush()
        return attempt

    def is_locked_out(self, user: User) -> bool:
        """Check if user account is currently locked."""
        if not user.is_locked:
            return False
        if user.locked_until and datetime.utcnow() >= user.locked_until:
            # Lockout period expired
            self._unlock_user(user)
            return False
        return True

    def register_failed_attempt(self, user: User) -> None:
        """Increment failed attempts and lock account if threshold reached."""
        user.failed_login_count += 1
        if user.failed_login_count >= settings.max_login_attempts:
            user.is_locked = True
            user.locked_until = datetime.utcnow() + timedelta(minutes=settings.lockout_minutes)
        self._session.flush()

    def reset_failed_attempts(self, user: User) -> None:
        """Reset failed login counter after successful login."""
        user.failed_login_count = 0
        user.is_locked = False
        user.locked_until = None
        self._session.flush()

    def record_login(self, user: User, ip_address: Optional[str] = None) -> None:
        """Record successful login timestamp."""
        user.last_login_at = datetime.utcnow()
        user.last_login_ip = ip_address
        self._session.flush()

    def _unlock_user(self, user: User) -> None:
        """Unlock an account whose lockout timer has expired."""
        user.is_locked = False
        user.locked_until = None
        user.failed_login_count = 0
        self._session.flush()

    def change_password(self, user: User, new_password_hash: str) -> None:
        """Update password and track password change metadata."""
        # Save old hash to history
        history = PasswordHistory(
            user_id=user.id,
            password_hash=user.password_hash,
        )
        self._session.add(history)

        # Update password
        user.password_hash = new_password_hash
        user.password_changed_at = datetime.utcnow()
        user.password_expires_at = datetime.utcnow() + timedelta(days=settings.password_expiry_days)
        user.must_change_password = False
        self._session.flush()

    def check_password_history(self, user: User, new_password_plain: str) -> bool:
        """Check if the new password was used recently (prevent reuse)."""
        history_count = settings.password_history_count
        recent_hashes = (
            self._session.query(PasswordHistory.password_hash)
            .filter(PasswordHistory.user_id == user.id)
            .order_by(PasswordHistory.created_at.desc())
            .limit(history_count)
            .all()
        )
        # Also check the current hash
        all_hashes = [user.password_hash] + [h[0] for h in recent_hashes]
        return any(verify_password(new_password_plain, h) for h in all_hashes)


class RoleRepository(SqlAlchemyRepository[Role, int]):
    """Repository for Role entities."""

    def __init__(self, session: Session):
        super().__init__(session, Role)

    def get_by_code(self, code: str) -> Optional[Role]:
        return self._session.query(Role).filter(Role.code == code).first()

    def get_system_roles(self) -> List[Role]:
        return self._session.query(Role).filter(Role.is_system == True).all()


class PermissionRepository(SqlAlchemyRepository[Permission, int]):
    """Repository for Permission entities."""

    def __init__(self, session: Session):
        super().__init__(session, Permission)

    def get_by_code(self, code: str) -> Optional[Permission]:
        return self._session.query(Permission).filter(Permission.code == code).first()

    def get_module_permissions(self, module: str) -> List[Permission]:
        return self._session.query(Permission).filter(Permission.module == module).all()


class AuditLogRepository(SqlAlchemyRepository[AuditLog, int]):
    """Repository for audit log entries."""

    def __init__(self, session: Session):
        super().__init__(session, AuditLog)

    def log_action(
        self,
        user_id: Optional[int],
        username: str,
        action: str,
        module: str,
        record_type: Optional[str] = None,
        record_id: Optional[int] = None,
        previous_value: Optional[str] = None,
        new_value: Optional[str] = None,
        ip_address: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> AuditLog:
        entry = AuditLog(
            user_id=user_id,
            username=username,
            action=action,
            module=module,
            record_type=record_type,
            record_id=record_id,
            previous_value=previous_value,
            new_value=new_value,
            ip_address=ip_address,
            reason=reason,
        )
        self._session.add(entry)
        self._session.flush()
        return entry


class UserSessionRepository(SqlAlchemyRepository[UserSession, int]):
    """Repository for user session tracking."""

    def __init__(self, session: Session):
        super().__init__(session, UserSession)

    def create_session(self, user_id: int, token: str, ip_address: Optional[str] = None) -> UserSession:
        session = UserSession(
            user_id=user_id,
            token=token,
            ip_address=ip_address,
            expires_at=datetime.utcnow() + timedelta(minutes=settings.session_timeout_minutes),
        )
        self._session.add(session)
        self._session.flush()
        return session

    def invalidate_session(self, token: str) -> None:
        session = self._session.query(UserSession).filter(
            UserSession.token == token
        ).first()
        if session:
            session.is_active = False
            self._session.flush()

    def cleanup_expired(self) -> int:
        count = self._session.query(UserSession).filter(
            UserSession.expires_at < datetime.utcnow()
        ).delete()
        self._session.flush()
        return count