"""
RetailFlow POS - Result Pattern
A monadic Result type for consistent error handling across the application.
"""
from dataclasses import dataclass, field
from typing import Generic, TypeVar, Optional, Any

T = TypeVar("T")
E = TypeVar("E")


@dataclass(frozen=True)
class Result(Generic[T, E]):
    """Represents the outcome of an operation that may succeed or fail.

    Use Result.ok(value) for success and Result.fail(error) for failure.
    """

    _value: Optional[T] = field(default=None)
    _error: Optional[E] = field(default=None)
    _is_success: bool = field(default=True)

    @classmethod
    def ok(cls, value: T) -> "Result[T, Any]":
        """Create a successful result."""
        return cls(_value=value, _is_success=True)

    @classmethod
    def fail(cls, error: E) -> "Result[Any, E]":
        """Create a failed result."""
        return cls(_error=error, _is_success=False)

    @property
    def is_success(self) -> bool:
        return self._is_success

    @property
    def is_failure(self) -> bool:
        return not self._is_success

    @property
    def value(self) -> T:
        """Get the success value. Raises if this is a failure result."""
        if self.is_failure:
            raise ValueError(f"Cannot get value from a failed result: {self._error}")
        return self._value  # type: ignore

    @property
    def error(self) -> E:
        """Get the error value. Raises if this is a success result."""
        if self.is_success:
            raise ValueError("Cannot get error from a successful result")
        return self._error  # type: ignore

    def map(self, func) -> "Result[Any, E]":
        """Apply a function to the value if successful."""
        if self.is_success:
            return Result.ok(func(self._value))
        return self  # type: ignore

    def and_then(self, func) -> "Result[Any, E]":
        """Chain another Result-returning function."""
        if self.is_success:
            return func(self._value)
        return self  # type: ignore

    def get_or_default(self, default: T) -> T:
        """Return value on success, default on failure."""
        if self.is_success:
            return self._value  # type: ignore
        return default

    def __bool__(self) -> bool:
        return self.is_success