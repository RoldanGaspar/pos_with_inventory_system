"""
RetailFlow POS - Base SQLAlchemy Repository
Concrete implementation of the Repository interface using SQLAlchemy.
"""
from __future__ import annotations

from typing import TypeVar, Generic, Optional, Sequence, Any

from sqlalchemy.orm import Session

from domain.interfaces.repository import Repository
from infrastructure.database.session import Base

T = TypeVar("T", bound=Base)
ID = TypeVar("ID")


class SqlAlchemyRepository(Repository[T, ID]):
    """Generic SQLAlchemy-based repository."""

    def __init__(self, session: Session, model_class: type[T]):
        self._session = session
        self._model_class = model_class

    def get_by_id(self, entity_id: ID) -> Optional[T]:
        return self._session.get(self._model_class, entity_id)

    def get_all(self, skip: int = 0, limit: int = 100) -> list[T]:
        return (
            self._session.query(self._model_class)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def add(self, entity: T) -> T:
        self._session.add(entity)
        self._session.flush()
        return entity

    def update(self, entity: T) -> T:
        self._session.merge(entity)
        self._session.flush()
        return entity

    def delete(self, entity_id: ID) -> None:
        entity = self.get_by_id(entity_id)
        if entity:
            self._session.delete(entity)
            self._session.flush()

    def count(self) -> int:
        return self._session.query(self._model_class).count()
