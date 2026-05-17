"""
Multiplication rendering.

Multiplication is structurally different from addition/subtraction:

- For a 1-digit multiplier (e.g. `35 × 7`) the layout is the same as
  addition: thin carry row, two operand rows, a horizontal rule, and a
  bordered answer-box row.
- For a multi-digit multiplier (e.g. `616 × 435`) we replace the answer
  with N partial-product rows (one per digit of the multiplier) plus a
  final-answer row. All partial rows share the same per-problem width
  (the widest partial), so the staircase is regular — only the *shift*
  changes between rows. Inactive cells in a partial row get a light
  dashed border so the student sees a complete grid.

The module also picks its own layout (cells, font, cards-per-row)
without coordinating with addition or division: multi-digit problems
get bigger cells (11mm @ 22pt) and 2 cards per row for breathing room.
"""

from __future__ import annotations

from html import escape

from .generator import Problem, max_partial_width
from .render_common import (
    COLUMN_GAP_MM,
    PAGE_CONTENT_W,
    digit_cells,
    empty_cells,
    fit_cells,
    font_for,
)


def section_digit_cols(problems: list[Problem]) -> int:
    """How many digit columns are needed across all multiplication problems."""
    n = 1
    for p in problems:
        n = max(n, len(str(p.operand1)), len(str(p.operand2)), len(str(p.answer)))
        if len(str(p.operand2)) >= 2:
            # uniform-width partial staircase: leftmost partial sits at shift
            # (op2_digits - 1) and is `max_partial_width(p)` wide.
            n = max(n, max_partial_width(p) + len(str(p.operand2)) - 1)
    return n


def compute_layout(problems: list[Problem]) -> dict:
    """Pick cell size, cards-per-row, fonts, and a card-height estimate."""
    digit_cols = section_digit_cols(problems)
    cells_per_card = digit_cols + 1                    # +1 for the operator column
    has_multi = any(len(str(p.operand2)) >= 2 for p in problems)
    max_cell = 11 if has_multi else 9

    # multi-digit problems use 2 cards per row so each card has more
    # horizontal breathing room and the staircase is easier to scan
    per_row = 2 if has_multi else 3
    cell_mm = fit_cells(per_row, cells_per_card, max_cell=max_cell)
    if cell_mm < 7:
        per_row = max(1, per_row - 1)
        cell_mm = fit_cells(per_row, cells_per_card, max_cell=max_cell)

    row_mm = cell_mm * 10 / 9
    carry_mm = max(3.5, cell_mm * 0.55)

    # tallest card in the section determines per-row vertical footprint
    max_op2_digits = max(len(str(p.operand2)) for p in problems)
    if max_op2_digits >= 2:
        rows = 2 + max_op2_digits + 1                  # op1, op2, N partials, answer
        extra = 0
    else:
        rows = 4                                        # carry, op1, op2, answer
        extra = carry_mm
    card_h = round(row_mm * rows + extra + 22)

    return {
        "op": "×",
        "digit_cols": digit_cols,
        "per_row": per_row,
        "cell_mm": cell_mm,
        "row_mm": row_mm,
        "carry_mm": carry_mm,
        "font_pt": font_for(cell_mm),
        "card_h": card_h,
    }


def render_card(p: Problem, number: int, layout: dict) -> str:
    if len(str(p.operand2)) >= 2:
        return _render_multidigit(p, number, layout)
    return _render_single_digit_multiplier(p, number, layout)


def _render_single_digit_multiplier(p: Problem, number: int, layout: dict) -> str:
    """ab × c — same shape as addition/subtraction."""
    cols = layout["digit_cols"]
    return (
        "<div class='card vertical'>"
        f"<div class='num'>{number}.</div>"
        "<table class='vert'>"
        f"<tr class='r-carry'><td class='op'></td>{empty_cells('carry', cols)}</tr>"
        f"<tr class='r-op'><td class='op'></td>{digit_cells(p.operand1, cols)}</tr>"
        f"<tr class='r-op rule'><td class='op'>{escape(p.operator)}</td>"
        f"{digit_cells(p.operand2, cols)}</tr>"
        f"<tr class='r-ans'><td class='op'></td>{empty_cells('ans', cols)}</tr>"
        "</table>"
        "</div>"
    )


def _render_multidigit(p: Problem, number: int, layout: dict) -> str:
    """ab × cd — partial-product staircase + final answer."""
    cols = layout["digit_cols"]
    op2_str = str(p.operand2)
    op2_digits = len(op2_str)
    width = max_partial_width(p)

    op1_cells = digit_cells(p.operand1, cols)
    op2_cells = digit_cells(p.operand2, cols)

    partial_rows = []
    for k in range(op2_digits):
        # k = 0 is the units multiplier (rightmost partial, no shift);
        # k = op2_digits - 1 is the leftmost partial (most shifted left)
        right_col = cols - k
        left_col = right_col - width + 1
        is_last = (k == op2_digits - 1)
        row_class = "r-partial rule" if is_last else "r-partial"
        cells: list[str] = []
        for ci in range(1, cols + 1):
            in_box = left_col <= ci <= right_col
            cell_class = "pp-box" if in_box else "pp-empty"
            cells.append(f"<td class='{cell_class}'></td>")
        partial_rows.append(
            f"<tr class='{row_class}'><td class='op'></td>{''.join(cells)}</tr>"
        )

    return (
        "<div class='card vertical mul'>"
        f"<div class='num'>{number}.</div>"
        "<table class='vert'>"
        f"<tr class='r-op'><td class='op'></td>{op1_cells}</tr>"
        f"<tr class='r-op rule'><td class='op'>{escape(p.operator)}</td>{op2_cells}</tr>"
        f"{''.join(partial_rows)}"
        f"<tr class='r-ans'><td class='op'></td>{empty_cells('ans', cols)}</tr>"
        "</table>"
        "</div>"
    )
