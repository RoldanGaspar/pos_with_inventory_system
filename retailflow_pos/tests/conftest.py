"""
RetailFlow POS - Shared Test Fixtures
Provides an isolated in-memory SQLite session for each test.
"""

import itertools

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import infrastructure.database.models.auth  # noqa: F401
import infrastructure.database.models.inventory  # noqa: F401
import infrastructure.database.models.product  # noqa: F401
import infrastructure.database.models.sales  # noqa: F401
from infrastructure.database.models.auth import Permission, Role, User
from infrastructure.database.session import Base

_user_counter = itertools.count(1)


@pytest.fixture
def db_session():
    """An isolated in-memory SQLite session with all tables created."""
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def user_with_permissions(db_session):
    """Factory that creates a user granted the given permission codes."""

    def _make(*codes: str) -> User:
        n = next(_user_counter)
        permissions = []
        for code in codes:
            perm = db_session.query(Permission).filter(Permission.code == code).first()
            if perm is None:
                perm = Permission(code=code, name=code.replace("_", " ").title(), module="products")
                db_session.add(perm)
            permissions.append(perm)
        db_session.flush()

        role = Role(name=f"Test Role {n}", code=f"test_role_{n}")
        role.permissions = permissions
        db_session.add(role)
        db_session.flush()

        user = User(
            username=f"tester_{n}",
            password_hash="x",
            full_name="Test User",
            is_active=True,
        )
        user.roles.append(role)
        db_session.add(user)
        db_session.commit()
        return user

    return _make
