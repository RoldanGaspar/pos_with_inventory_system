"""
RetailFlow POS - DateTime Utilities
Common date/time helpers for the application.
"""
from datetime import datetime, date, timedelta
from typing import Optional


def now() -> datetime:
    """Get current UTC datetime."""
    return datetime.utcnow()


def today() -> date:
    """Get today's date."""
    return date.today()


def days_ago(days: int) -> datetime:
    """Get datetime for N days ago."""
    return datetime.utcnow() - timedelta(days=days)


def start_of_day(dt: Optional[datetime] = None) -> datetime:
    """Get the start of a given day (midnight)."""
    d = dt or datetime.utcnow()
    return datetime(d.year, d.month, d.day)


def end_of_day(dt: Optional[datetime] = None) -> datetime:
    """Get the end of a given day (23:59:59.999999)."""
    d = dt or datetime.utcnow()
    return datetime(d.year, d.month, d.day, 23, 59, 59, 999999)


def format_currency(amount: float, currency_symbol: str = "$") -> str:
    """Format a float amount as currency string."""
    return f"{currency_symbol}{amount:,.2f}"


def format_date(d: date, fmt: str = "%Y-%m-%d") -> str:
    """Format a date object."""
    return d.strftime(fmt)


def format_datetime(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format a datetime object."""
    return dt.strftime(fmt)
