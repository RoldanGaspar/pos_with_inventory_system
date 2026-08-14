"""
RetailFlow POS - Repository Interfaces
Abstract base classes defining repository contracts for Dependency Injection.
"""
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional

T = TypeVar("T")
ID = TypeVar("ID")


class Repository(ABC, Generic[T, ID]):
    """Generic repository interface for basic CRUD operations."""

    @abstractmethod
    def get_by_id(self, entity_id: ID) -> Optional[T]:
        ...

    @abstractmethod
    def get_all(self, skip: int = 0, limit: int = 100) -> list[T]:
        ...

    @abstractmethod
    def add(self, entity: T) -> T:
        ...

    @abstractmethod
    def update(self, entity: T) -> T:
        ...

    @abstractmethod
    def delete(self, entity_id: ID) -> None:
        ...

    @abstractmethod
    def count(self) -> int:
        ...