"""Fix script: create hashing.py and clean up corrupted files."""
import os, shutil, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SEC = BASE / "infrastructure" / "security"

# 1. Remove corrupted file and stale cache
corrupted = SEC / "h"
if corrupted.exists():
    corrupted.unlink()
    print(f"Deleted corrupted: {corrupted}")

cache = SEC / "__pycache__"
if cache.exists():
    shutil.rmtree(cache)
    print(f"Cleared cache: {cache}")

# 2. Fix __init__.py
init_file = SEC / "__init__.py"
init_file.write_text("", encoding="utf-8")
print(f"Fixed: {init_file}")

# 3. Write hashing.py
hashing_file = SEC / "hashing.py"
content = '''"""
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
'''
hashing_file.write_text(content, encoding="utf-8")
print(f"Created: {hashing_file} ({hashing_file.stat().st_size} bytes)")

# 4. Verify
print(f"\nFiles in {SEC}:")
for f in sorted(SEC.iterdir()):
    print(f"  {f.name} ({f.stat().st_size} bytes)")

# 5. Test import
sys.path.insert(0, str(BASE))
from infrastructure.security.hashing import hash_password, verify_password
h = hash_password("test123")
assert verify_password("test123", h), "Password verification failed!"
print("\nVerification successful! Hashing module works correctly.")