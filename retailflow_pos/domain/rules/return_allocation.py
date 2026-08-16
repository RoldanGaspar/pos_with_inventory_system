"""
RetailFlow POS - Return Allocation Rules & Centavo Apportionment
Pure, deterministic financial allocation algorithms using integer centavos and largest-remainder (Hamilton) method.
Guarantees exact reconciliation without rounding drift, negative residuals, or float precision issues.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Sequence, Tuple

from app.constants import ReturnDisposition


@dataclass(frozen=True)
class LineFinancialBreakdown:
    """Exact calculated financial breakdown for a returned line item slice."""

    gross_amount_reversal: Decimal
    discount_reversal: Decimal
    taxable_reversal: Decimal
    tax_reversal: Decimal
    total_refund_amount: Decimal
    cogs_reversal: Decimal
    writeoff_cost: Decimal


def to_cents(amount: Decimal) -> int:
    """Convert Decimal currency to integer centavos safely."""
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))


def to_decimal(cents: int) -> Decimal:
    """Convert integer centavos to Decimal(2 places)."""
    return (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"))


def apportion_cents_largest_remainder(
    total_cents: int,
    weights: Sequence[Tuple[int, int]],
) -> Dict[int, int]:
    """
    Apportion an integer amount of centavos across items proportionally to their integer weights
    using the largest remainder (Hamilton) method with deterministic tie-breaking (item_id ASC).

    Args:
        total_cents: Total integer centavos to distribute (must be >= 0).
        weights: Sequence of (item_id, weight_cents) tuples (each weight_cents >= 0).

    Returns:
        Dict[item_id, allocated_cents] where sum(allocated_cents.values()) == total_cents.
    """
    if total_cents < 0:
        raise ValueError(f"total_cents must be >= 0, got {total_cents}")
    if total_cents == 0 or not weights:
        return {item_id: 0 for item_id, _ in weights}

    total_weight = sum(w for _, w in weights)
    if total_weight <= 0:
        # If all weights are 0 but total_cents > 0, distribute remainder evenly starting with lowest item_id
        allocations = {item_id: 0 for item_id, _ in weights}
        sorted_ids = sorted(item_id for item_id, _ in weights)
        for i in range(min(total_cents, len(sorted_ids))):
            allocations[sorted_ids[i]] += 1
        return allocations

    # Step 1: Compute floor share and exact remainder
    floor_shares: Dict[int, int] = {}
    remainders: List[Tuple[int, int]] = []  # (rem_numerator, item_id)

    total_floor = 0
    for item_id, weight in weights:
        num = total_cents * weight
        floor_val = num // total_weight
        rem_num = num % total_weight
        floor_shares[item_id] = floor_val
        total_floor += floor_val
        remainders.append((rem_num, item_id))

    remaining_cents = total_cents - total_floor

    # Step 2: Sort by remainder descending, tie-break by item_id ascending
    remainders.sort(key=lambda x: (x[0], -x[1]), reverse=True)

    # Step 3: Distribute 1 cent to the top remaining_cents items
    allocations = dict(floor_shares)
    for i in range(remaining_cents):
        item_id = remainders[i][1]
        allocations[item_id] += 1

    return allocations


def allocate_sale_discounts(
    sale_discount: Decimal,
    lines_subtotals: Sequence[Tuple[int, Decimal]],
) -> Dict[int, Decimal]:
    """
    Deterministically apportion order-level Sale.discount_amount across line items
    based on line item subtotal contribution.

    Guarantees:
        - sum(allocations.values()) == sale_discount exactly.
        - 0 <= line_allocation <= line_subtotal.
    """
    total_cents = to_cents(sale_discount)
    weights = [(item_id, to_cents(subtotal)) for item_id, subtotal in lines_subtotals]
    cent_allocations = apportion_cents_largest_remainder(total_cents, weights)
    return {item_id: to_decimal(cents) for item_id, cents in cent_allocations.items()}


def allocate_sale_vat(
    sale_tax: Decimal,
    lines_taxable: Sequence[Tuple[int, Decimal]],
) -> Dict[int, Decimal]:
    """
    Deterministically apportion Sale.tax_amount across line items
    based on each line's allocated taxable base.

    Guarantees:
        - sum(allocations.values()) == sale_tax exactly.
        - 0 <= line_tax_allocation.
    """
    total_tax_cents = to_cents(sale_tax)
    weights = [(item_id, to_cents(taxable)) for item_id, taxable in lines_taxable]
    cent_allocations = apportion_cents_largest_remainder(total_tax_cents, weights)
    return {item_id: to_decimal(cents) for item_id, cents in cent_allocations.items()}


def allocate_unit_slots_cents(
    total_cents: int,
    total_quantity: int,
    previously_returned_qty: int,
    requested_qty: int,
) -> int:
    """
    Calculate exact integer centavos for a partial return slice using deterministic unit slot indexing.

    Slots 0 .. rem-1 receive base + 1 centavos.
    Slots rem .. Q-1 receive base centavos.
    The current return takes slots [previously_returned_qty .. previously_returned_qty + requested_qty - 1].
    """
    if total_quantity <= 0:
        raise ValueError(f"total_quantity must be > 0, got {total_quantity}")
    if requested_qty <= 0:
        raise ValueError(f"requested_qty must be > 0, got {requested_qty}")
    if previously_returned_qty + requested_qty > total_quantity:
        raise ValueError(
            f"Exceeded returnable quantity: {previously_returned_qty} + {requested_qty} > {total_quantity}"
        )

    base = total_cents // total_quantity
    rem = total_cents % total_quantity

    start_idx = previously_returned_qty
    end_idx = previously_returned_qty + requested_qty

    allocated_cents = 0
    for idx in range(start_idx, end_idx):
        slot_val = base + 1 if idx < rem else base
        allocated_cents += slot_val

    return allocated_cents


def calculate_line_return_financials(
    unit_price: Decimal,
    unit_cost: Decimal,
    total_line_qty: int,
    line_discount_ceiling: Decimal,
    line_tax_ceiling: Decimal,
    previously_returned_qty: int,
    requested_qty: int,
    disposition: str = ReturnDisposition.RESTOCK.value,
) -> LineFinancialBreakdown:
    """
    Calculate the exact financial reversal snapshots for a single line item return slice.
    """
    gross_amount = (unit_price * requested_qty).quantize(Decimal("0.01"))

    # Discount allocated to this slice
    discount_cents = allocate_unit_slots_cents(
        total_cents=to_cents(line_discount_ceiling),
        total_quantity=total_line_qty,
        previously_returned_qty=previously_returned_qty,
        requested_qty=requested_qty,
    )
    discount_rev = to_decimal(discount_cents)

    # Taxable reversal
    taxable_rev = gross_amount - discount_rev

    # Tax allocated to this slice
    tax_cents = allocate_unit_slots_cents(
        total_cents=to_cents(line_tax_ceiling),
        total_quantity=total_line_qty,
        previously_returned_qty=previously_returned_qty,
        requested_qty=requested_qty,
    )
    tax_rev = to_decimal(tax_cents)

    total_refund = taxable_rev + tax_rev

    # COGS vs Write-off cost
    cost_base = (unit_cost * requested_qty).quantize(Decimal("0.01"))
    if disposition == ReturnDisposition.RESTOCK.value:
        cogs_rev = cost_base
        writeoff = Decimal("0.00")
    else:
        cogs_rev = Decimal("0.00")
        writeoff = cost_base

    return LineFinancialBreakdown(
        gross_amount_reversal=gross_amount,
        discount_reversal=discount_rev,
        taxable_reversal=taxable_rev,
        tax_reversal=tax_rev,
        total_refund_amount=total_refund,
        cogs_reversal=cogs_rev,
        writeoff_cost=writeoff,
    )
