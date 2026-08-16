"""
RetailFlow POS - Application Constants
Central location for all system-wide constants and enumerations.
"""
from enum import Enum, StrEnum, auto


# ─── Application ───

class AppEnvironment(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


# ─── Status ───

class Status(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    VOIDED = "voided"
    ARCHIVED = "archived"


# ─── Inventory Movement Types ───

class MovementType(StrEnum):
    OPENING_BALANCE = "opening_balance"
    PURCHASE_RECEIPT = "purchase_receipt"
    SALE = "sale"
    SALES_RETURN = "sales_return"
    PURCHASE_RETURN = "purchase_return"
    POSITIVE_ADJUSTMENT = "positive_adjustment"
    NEGATIVE_ADJUSTMENT = "negative_adjustment"
    DAMAGE = "damage"
    EXPIRATION = "expiration"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    STOCK_COUNT_CORRECTION = "stock_count_correction"


# ─── Purchase Order Status ───

class PurchaseOrderStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    PARTIALLY_RECEIVED = "partially_received"
    FULLY_RECEIVED = "fully_received"
    CANCELLED = "cancelled"
    CLOSED = "closed"


# ─── Payment Methods ───

class PaymentMethod(StrEnum):
    CASH = "cash"
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    GCASH = "gcash"
    MAYA = "maya"
    BANK_TRANSFER = "bank_transfer"
    CHECK = "check"
    STORE_CREDIT = "store_credit"
    GIFT_CARD = "gift_card"
    SPLIT = "split"


# ─── Discount Types ───

class DiscountType(StrEnum):
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"
    SENIOR_CITIZEN = "senior_citizen"
    PWD = "pwd"
    PROMOTIONAL = "promotional"


# ─── Tax Type ───

class TaxType(StrEnum):
    VAT = "vat"
    NON_VAT = "non_vat"
    ZERO_RATED = "zero_rated"
    EXEMPT = "exempt"


# ─── User Roles ───

class UserRole(StrEnum):
    ADMINISTRATOR = "administrator"
    MANAGER = "manager"
    CASHIER = "cashier"
    INVENTORY_STAFF = "inventory_staff"
    AUDITOR = "auditor"


# ─── Shift Status ───

class ShiftStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    PENDING_APPROVAL = "pending_approval"


# ─── Inventory Costing Method ───

class CostingMethod(StrEnum):
    WEIGHTED_AVERAGE = "weighted_average"
    FIFO = "fifo"
    SPECIFIC_IDENTIFICATION = "specific_identification"


# ─── Return Management ───

class ReturnStatus(StrEnum):
    COMPLETED = "completed"


class ReturnDisposition(StrEnum):
    RESTOCK = "restock"
    DAMAGED_WRITE_OFF = "damaged_write_off"


class RefundMethod(StrEnum):
    CASH = "cash"
    ORIGINAL_METHOD = "original_method"


class DerivedReturnState(StrEnum):
    NONE = "none"
    PARTIAL = "partial"
    FULL = "full"


class ReturnReason(StrEnum):
    DEFECTIVE = "defective"
    WRONG_ITEM = "wrong_item"
    CUSTOMER_CHANGE_MIND = "customer_change_mind"
    EXPIRED = "expired"
    OTHER = "other"


# ─── Receipt Width ───

class ReceiptWidth(StrEnum):
    MM_58 = "58mm"
    MM_80 = "80mm"
    A4 = "a4"


# ─── Expense Management ───

class ExpenseCategory(StrEnum):
    UTILITIES = "utilities"
    RENT = "rent"
    SALARIES = "salaries"
    SUPPLIES = "supplies"
    MAINTENANCE = "maintenance"
    TAXES_LICENSES = "taxes_licenses"
    MARKETING = "marketing"
    OTHER = "other"


class ExpenseStatus(StrEnum):
    PAID = "paid"
    VOID = "void"


class ExpenseSource(StrEnum):
    MANUAL = "manual"
    PAYROLL = "payroll"


EXPENSE_CATEGORY_LABELS = {
    ExpenseCategory.UTILITIES: "Utilities (Power, Water, Internet)",
    ExpenseCategory.RENT: "Store & Warehouse Rent",
    ExpenseCategory.SALARIES: "Staff Wages & Allowances",
    ExpenseCategory.SUPPLIES: "Store Supplies & Packaging",
    ExpenseCategory.MAINTENANCE: "Repairs & Maintenance",
    ExpenseCategory.TAXES_LICENSES: "Taxes, Permits & Licenses",
    ExpenseCategory.MARKETING: "Marketing & Advertising",
    ExpenseCategory.OTHER: "Other Miscellaneous",
}