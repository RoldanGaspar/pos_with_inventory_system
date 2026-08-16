"""
RetailFlow POS - Return Allocation & Centavo Apportionment Unit Tests (Phase 2B.1)
Rigorously tests largest-remainder (Hamilton) centavo apportionment, partial-quantity slot allocation,
and exact financial reconciliation across Cases A, B, C, D, E.
"""

from decimal import Decimal

import pytest

from app.constants import ReturnDisposition
from domain.rules.return_allocation import (
    allocate_sale_discounts,
    allocate_sale_vat,
    allocate_unit_slots_cents,
    apportion_cents_largest_remainder,
    calculate_line_return_financials,
    to_cents,
    to_decimal,
)


# ── 1. Case A: ₱0.05 Discount / 10 Equal Lines ────────────────────────

def test_case_a_ten_equal_lines_five_cents_discount():
    """
    Case A: ₱0.05 discount across 10 equal lines (subtotal ₱100.00 each).
    Under old ROUND_HALF_UP, 10 lines of 0.005 could produce 0.01 * 9 = 0.09 and -0.04 residual.
    Under largest-remainder: exactly 5 lines get ₱0.01 and 5 lines get ₱0.00.
    Total == ₱0.05 exactly, no negative residuals.
    """
    sale_discount = Decimal("0.05")
    lines = [(i, Decimal("100.00")) for i in range(1, 11)]

    allocations = allocate_sale_discounts(sale_discount, lines)

    # Invariant 1: Sum equals exactly ₱0.05
    total_allocated = sum(allocations.values())
    assert total_allocated == Decimal("0.05")

    # Invariant 2: No negative allocations
    for item_id, amount in allocations.items():
        assert amount >= Decimal("0.00")
        assert amount <= Decimal("0.01")

    # Invariant 3: Deterministic tie-breaking gives ₱0.01 to lines 1..5 and ₱0.00 to lines 6..10
    for i in range(1, 6):
        assert allocations[i] == Decimal("0.01")
    for i in range(6, 11):
        assert allocations[i] == Decimal("0.00")


# ── 2. Case B: Ten Separate 1-Unit Partial Returns ────────────────────

def test_case_b_ten_separate_one_unit_returns():
    """
    Case B: Line discount ₱0.05, original quantity 10 units.
    Ten separate 1-unit partial returns performed sequentially.
    Total cumulative discount reversal must equal exactly ₱0.05.
    """
    total_discount_cents = 5  # ₱0.05
    total_qty = 10

    reversals = []
    for prev_returned in range(10):
        cents = allocate_unit_slots_cents(
            total_cents=total_discount_cents,
            total_quantity=total_qty,
            previously_returned_qty=prev_returned,
            requested_qty=1,
        )
        reversals.append(to_decimal(cents))

    # First 5 single-unit returns get ₱0.01 each
    assert reversals[:5] == [Decimal("0.01")] * 5
    # Next 5 single-unit returns get ₱0.00 each
    assert reversals[5:] == [Decimal("0.00")] * 5

    # Sum must equal exactly ₱0.05
    assert sum(reversals) == Decimal("0.05")


# ── 3. Case C: Multiple Unequal Lines with Repeating Fractions ─────────

def test_case_c_repeating_fractions_discount_apportionment():
    """
    Case C: 3 lines with subtotals ₱100.00, ₱200.00, ₱300.00 (Total ₱600.00).
    Order discount: ₱50.00.
    Exact shares:
      Line 1 (1/6): 5000 / 6 = 833.333... cents -> Floor 833, Remainder 2/6
      Line 2 (2/6): 10000 / 6 = 1666.666... cents -> Floor 1666, Remainder 4/6
      Line 3 (3/6): 15000 / 6 = 2500.000... cents -> Floor 2500, Remainder 0/6
    Total floor = 4999 cents. Remaining = 1 cent.
    Largest remainder is Line 2 (4/6), so Line 2 gets the extra cent:
      Line 1: 833 cents = ₱8.33
      Line 2: 1667 cents = ₱16.67
      Line 3: 2500 cents = ₱25.00
    Total = ₱50.00 exactly.
    """
    sale_discount = Decimal("50.00")
    lines = [
        (1, Decimal("100.00")),
        (2, Decimal("200.00")),
        (3, Decimal("300.00")),
    ]

    allocations = allocate_sale_discounts(sale_discount, lines)

    assert allocations[1] == Decimal("8.33")
    assert allocations[2] == Decimal("16.67")
    assert allocations[3] == Decimal("25.00")
    assert sum(allocations.values()) == Decimal("50.00")


# ── 4. Case D: VAT Total with Fractional Cent Line Weights ─────────────

def test_case_d_vat_fractional_cent_line_weights():
    """
    Case D: 3 lines with taxable bases ₱33.33, ₱33.33, ₱33.34 (Total ₱100.00).
    Total VAT: ₱12.00 (1200 cents).
    Exact shares:
      Line 1 (33.33%): 399.96 cents -> Floor 399, Rem 96
      Line 2 (33.33%): 399.96 cents -> Floor 399, Rem 96
      Line 3 (33.34%): 400.08 cents -> Floor 400, Rem 8
    Total floor = 1198. Remaining = 2 cents.
    Lines 1 and 2 have largest remainders (96), so each gets +1 cent:
      Line 1: 400 cents = ₱4.00
      Line 2: 400 cents = ₱4.00
      Line 3: 400 cents = ₱4.00
    Total VAT = ₱12.00 exactly.
    """
    sale_tax = Decimal("12.00")
    taxable_lines = [
        (1, Decimal("33.33")),
        (2, Decimal("33.33")),
        (3, Decimal("33.34")),
    ]

    vat_allocations = allocate_sale_vat(sale_tax, taxable_lines)

    assert vat_allocations[1] == Decimal("4.00")
    assert vat_allocations[2] == Decimal("4.00")
    assert vat_allocations[3] == Decimal("4.00")
    assert sum(vat_allocations.values()) == Decimal("12.00")


# ── 5. Case E: One-Shot Full Return vs. Multi-Stage Partial Returns ───

def test_case_e_oneshot_vs_multistage_exact_equality():
    """
    Case E: Compare full return of 5 units at once vs 3 partial returns (2 + 1 + 2 units).
    Line: 5 units @ ₱100.00 unit price, ₱40.00 unit cost.
    Allocated discount ceiling: ₱13.33.
    Allocated VAT ceiling: ₱58.40.
    Final cumulative Gross, Discount, Taxable, VAT, Refund, and COGS must be 100% IDENTICAL.
    """
    unit_price = Decimal("100.00")
    unit_cost = Decimal("40.00")
    total_qty = 5
    discount_ceiling = Decimal("13.33")
    tax_ceiling = Decimal("58.40")

    # One-shot full return of 5 units
    oneshot = calculate_line_return_financials(
        unit_price=unit_price,
        unit_cost=unit_cost,
        total_line_qty=total_qty,
        line_discount_ceiling=discount_ceiling,
        line_tax_ceiling=tax_ceiling,
        previously_returned_qty=0,
        requested_qty=5,
        disposition=ReturnDisposition.RESTOCK.value,
    )

    # Multi-stage returns: 2 units, then 1 unit, then 2 units
    stage1 = calculate_line_return_financials(
        unit_price=unit_price,
        unit_cost=unit_cost,
        total_line_qty=total_qty,
        line_discount_ceiling=discount_ceiling,
        line_tax_ceiling=tax_ceiling,
        previously_returned_qty=0,
        requested_qty=2,
        disposition=ReturnDisposition.RESTOCK.value,
    )

    stage2 = calculate_line_return_financials(
        unit_price=unit_price,
        unit_cost=unit_cost,
        total_line_qty=total_qty,
        line_discount_ceiling=discount_ceiling,
        line_tax_ceiling=tax_ceiling,
        previously_returned_qty=2,
        requested_qty=1,
        disposition=ReturnDisposition.RESTOCK.value,
    )

    stage3 = calculate_line_return_financials(
        unit_price=unit_price,
        unit_cost=unit_cost,
        total_line_qty=total_qty,
        line_discount_ceiling=discount_ceiling,
        line_tax_ceiling=tax_ceiling,
        previously_returned_qty=3,
        requested_qty=2,
        disposition=ReturnDisposition.RESTOCK.value,
    )

    # Cumulative sums
    cum_gross = stage1.gross_amount_reversal + stage2.gross_amount_reversal + stage3.gross_amount_reversal
    cum_discount = stage1.discount_reversal + stage2.discount_reversal + stage3.discount_reversal
    cum_taxable = stage1.taxable_reversal + stage2.taxable_reversal + stage3.taxable_reversal
    cum_tax = stage1.tax_reversal + stage2.tax_reversal + stage3.tax_reversal
    cum_refund = stage1.total_refund_amount + stage2.total_refund_amount + stage3.total_refund_amount
    cum_cogs = stage1.cogs_reversal + stage2.cogs_reversal + stage3.cogs_reversal

    # Exact equality with one-shot full return
    assert cum_gross == oneshot.gross_amount_reversal == Decimal("500.00")
    assert cum_discount == oneshot.discount_reversal == Decimal("13.33")
    assert cum_taxable == oneshot.taxable_reversal == Decimal("486.67")
    assert cum_tax == oneshot.tax_reversal == Decimal("58.40")
    assert cum_refund == oneshot.total_refund_amount == Decimal("545.07")
    assert cum_cogs == oneshot.cogs_reversal == Decimal("200.00")


# ── 6. Boundary Conditions & Damaged Disposition ─────────────────────

def test_zero_discount_and_zero_tax():
    """Zero discount and zero tax allocations yield zero reversal without error."""
    lines = [(1, Decimal("50.00")), (2, Decimal("50.00"))]
    disc_alloc = allocate_sale_discounts(Decimal("0.00"), lines)
    assert disc_alloc[1] == Decimal("0.00")
    assert disc_alloc[2] == Decimal("0.00")

    tax_alloc = allocate_sale_vat(Decimal("0.00"), lines)
    assert tax_alloc[1] == Decimal("0.00")
    assert tax_alloc[2] == Decimal("0.00")


def test_damaged_disposition_does_not_reverse_cogs():
    """Damaged return records writeoff_cost and ₱0.00 COGS reversal."""
    financials = calculate_line_return_financials(
        unit_price=Decimal("100.00"),
        unit_cost=Decimal("45.00"),
        total_line_qty=2,
        line_discount_ceiling=Decimal("0.00"),
        line_tax_ceiling=Decimal("0.00"),
        previously_returned_qty=0,
        requested_qty=2,
        disposition=ReturnDisposition.DAMAGED_WRITE_OFF.value,
    )
    assert financials.cogs_reversal == Decimal("0.00")
    assert financials.writeoff_cost == Decimal("90.00")
    assert financials.total_refund_amount == Decimal("200.00")
