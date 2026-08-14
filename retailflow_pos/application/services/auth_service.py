"""
RetailFlow POS - Authentication Service
Coordinates login, logout, lockout, and permission checking.
"""
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from infrastructure.database.repositories.auth import (
    UserRepository, AuditLogRepository, UserSessionRepository
)
from infrastructure.database.models.auth import User
from infrastructure.security.hashing import verify_password, hash_password, validate_password_strength
from app.config import settings
from domain.exceptions import (
    AuthenticationError, AccountLockedError, AccountInactiveError,
    PasswordExpiredError, AuthorizationError, ValidationError
)

logger = logging.getLogger("retailflow.security")


class AuthenticationService:
    """Handles all authentication and authorization operations."""

    def __init__(self, session: Session):
        self._session = session
        self.user_repo = UserRepository(session)
        self.audit_repo = AuditLogRepository(session)
        self.session_repo = UserSessionRepository(session)

    def login(
        self, username: str, password: str, ip_address: Optional[str] = None
    ) -> Tuple[User, str]:
        user = self.user_repo.get_by_username(username)
        if user is None:
            self.user_repo.record_login_attempt(
                username=username, success=False, ip_address=ip_address,
                failure_reason="User not found")
            raise AuthenticationError("Invalid username or password.")

        if not user.is_active:
            raise AccountInactiveError("This account has been deactivated.")

        if self.user_repo.is_locked_out(user):
            self.user_repo.record_login_attempt(
                username=username, success=False, ip_address=ip_address,
                failure_reason="Account locked", user_id=user.id)
            raise AccountLockedError(
                f"Account is temporarily locked. Try again in {settings.lockout_minutes} minutes.")

        if not verify_password(password, user.password_hash):
            self.user_repo.register_failed_attempt(user)
            self.user_repo.record_login_attempt(
                username=username, success=False, ip_address=ip_address,
                failure_reason="Incorrect password", user_id=user.id)
            logger.warning(f"Failed login for user: {username}")
            raise AuthenticationError("Invalid username or password.")

        if user.password_expires_at and user.password_expires_at < datetime.utcnow():
            raise PasswordExpiredError(
                "Your password has expired. Please change it before logging in.")

        self.user_repo.reset_failed_attempts(user)
        self.user_repo.record_login(user, ip_address)
        self.user_repo.record_login_attempt(
            username=username, success=True, ip_address=ip_address, user_id=user.id)

        token = secrets.token_urlsafe(48)
        self.session_repo.create_session(user.id, token, ip_address)
        logger.info(f"User logged in: {username}")
        return user, token

    def logout(self, token: str) -> None:
        self.session_repo.invalidate_session(token)
        logger.info("User logged out")

    def check_permission(self, user: User, permission_code: str) -> None:
        if not user.has_permission(permission_code):
            raise AuthorizationError(
                f"You do not have permission: {permission_code}")

    def change_password(self, user: User, current_password: str, new_password: str) -> None:
        if not verify_password(current_password, user.password_hash):
            raise AuthenticationError("Current password is incorrect.")
        is_valid, error_msg = validate_password_strength(new_password)
        if not is_valid:
            raise ValidationError(error_msg)
        if self.user_repo.check_password_history(user, new_password):
            raise ValidationError("You cannot reuse a previously used password.")
        new_hash = hash_password(new_password)
        self.user_repo.change_password(user, new_hash)
        self.audit_repo.log_action(
            user_id=user.id, username=user.username,
            action="PASSWORD_CHANGED", module="auth")
        logger.info(f"Password changed for: {user.username}")

    def reset_password(self, user: User, new_password: str) -> None:
        is_valid, error_msg = validate_password_strength(new_password)
        if not is_valid:
            raise ValidationError(error_msg)
        new_hash = hash_password(new_password)
        user.must_change_password = True
        self.user_repo.change_password(user, new_hash)
        self.audit_repo.log_action(
            user_id=user.id, username=user.username,
            action="PASSWORD_RESET", module="auth")
        logger.info(f"Password reset for: {user.username}")

    def lock_user(self, user: User) -> None:
        user.is_locked = True
        user.locked_until = datetime.utcnow() + timedelta(minutes=settings.lockout_minutes)
        self._session.flush()
        self.audit_repo.log_action(
            user_id=user.id, username=user.username,
            action="ACCOUNT_LOCKED", module="auth")

    def unlock_user(self, user: User) -> None:
        self.user_repo.reset_failed_attempts(user)
        self.audit_repo.log_action(
            user_id=user.id, username=user.username,
            action="ACCOUNT_UNLOCKED", module="auth")
