"""
RetailFlow POS - Security / Password Hashing
Uses Argon2 for secure password hashing.
"""
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from app.config import settings

_ph = PasswordHasher(
    time_cost=settings.argon2_time_cost,
    memory_cost=settings.argon2_memory_cost,
    parallelism=settings.argon2_parallelism,
)


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password using Argon2."""
    return _ph.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against an Argon2 hash."""
    try:
        return _ph.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError):
        return False


def validate_password_strength(password: str) -> tuple:
    """Validate password meets minimum security requirements.

    Returns (is_valid, error_message).
    """
    min_length = settings.password_min_length
    if len(password) < min_length:
        return False, f"Password must be at least {min_length} characters long."
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit."
    return True, ""
