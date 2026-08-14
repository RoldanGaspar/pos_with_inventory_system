"""
RetailFlow POS - Domain Exceptions
Custom exception hierarchy for the domain layer.
"""


class RetailFlowError(Exception):
    """Base exception for all RetailFlow errors."""


class DomainError(RetailFlowError):
    """Base exception for domain-level errors."""


# ─── Authentication ───

class AuthenticationError(DomainError):
    """Invalid credentials or authentication failure."""


class AccountLockedError(AuthenticationError):
    """Account temporarily locked due to too many failed attempts."""


class AccountInactiveError(AuthenticationError):
    """Account is deactivated."""


class PasswordExpiredError(AuthenticationError):
    """Password has expired and must be changed."""


class AuthorizationError(DomainError):
    """User does not have the required permission."""


# ─── Validation ───

class ValidationError(DomainError):
    """Input validation failed."""


class DuplicateBarcodeError(ValidationError):
    """Barcode already assigned to another product."""


class DuplicateSkuError(ValidationError):
    """SKU already assigned to another product."""


class DuplicateNameError(ValidationError):
    """Name already exists."""


class InvalidPriceError(ValidationError):
    """Product price is invalid (e.g., negative)."""


# ─── Products ───

class ProductNotFoundError(DomainError):
    """Product does not exist."""


# ─── Inventory ───

class InsufficientStockError(DomainError):
    """Not enough stock available for the requested operation."""


class StockMovementError(DomainError):
    """Error creating or validating stock movements."""


# ─── Sales ───

class SaleError(DomainError):
    """Error during sale processing."""


class SaleNotFoundError(SaleError):
    """Sale transaction does not exist."""


class PaymentError(DomainError):
    """Payment processing error."""


class RefundError(DomainError):
    """Refund validation or processing error."""


class ReturnPeriodExpiredError(RefundError):
    """Return period has expired for this transaction."""


class ReturnQuantityExceededError(RefundError):
    """Return quantity exceeds the original sold quantity."""


# ─── Cashier Shift ───

class ShiftError(DomainError):
    """Cashier shift operation error."""


class ShiftAlreadyOpenError(ShiftError):
    """A shift is already open for this cashier."""


class ShiftNotOpenError(ShiftError):
    """No open shift found for the current cashier."""


# ─── Purchasing ───

class PurchaseOrderError(DomainError):
    """Purchase order error."""


# ─── System ───

class DatabaseError(RetailFlowError):
    """Database operation failed."""


class BackupError(RetailFlowError):
    """Backup or restore operation failed."""


class PrintingError(RetailFlowError):
    """Printer operation failed."""


class ConfigurationError(RetailFlowError):
    """Invalid system configuration."""


class NotFoundError(DomainError):
    """Generic not-found error."""