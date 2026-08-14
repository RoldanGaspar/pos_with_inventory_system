"""
RetailFlow POS - Pagination
Pagination helper for large data tables.
"""
from dataclasses import dataclass
from typing import Generic, TypeVar, Sequence

T = TypeVar("T")


@dataclass
class PaginatedResult(Generic[T]):
    """Container for paginated query results."""

    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        if self.page_size == 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def previous_page(self) -> int:
        return max(1, self.page - 1)

    @property
    def next_page(self) -> int:
        return min(self.total_pages, self.page + 1)


def paginate(
    query,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedResult:
    """Apply pagination to a SQLAlchemy query.

    Args:
        query: SQLAlchemy query object.
        page: 1-based page number.
        page_size: Items per page.

    Returns:
        PaginatedResult with items, total count, and navigation helpers.
    """
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResult(items=items, total=total, page=page, page_size=page_size)
