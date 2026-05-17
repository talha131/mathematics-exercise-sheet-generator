"""
Division rendering.

Right now division uses a simple horizontal format:

    a ÷ b =  □

with a single answer box sized to the digit count of the actual quotient.
This is short (one row per card) so the worksheet fits 3 cards per row
comfortably.

This file is the place to add long-division (the bracket / "house"
layout) or remainder support later, without touching addition or
multiplication.
"""

from __future__ import annotations

from .generator import Problem
from .render_common import font_for


def section_digit_cols(problems: list[Problem]) -> int:
    """Division cards don't really use digit columns, but we expose the
    quotient's digit count so pagination and layout helpers have a number
    to work with."""
    return max((len(str(p.answer)) for p in problems), default=1)


def compute_layout(problems: list[Problem]) -> dict:
    digit_cols = section_digit_cols(problems)
    per_row = 3
    cell_mm = 9                                # nominal — division has its own sizing
    row_mm = 10
    card_h = round(row_mm + 18)                # one row + problem number + padding
    return {
        "op": "÷",
        "digit_cols": digit_cols,
        "per_row": per_row,
        "cell_mm": cell_mm,
        "row_mm": row_mm,
        "carry_mm": 0,
        "font_pt": 16,
        "card_h": card_h,
        "row_gap_mm": 12,
        "col_gap_mm": 10,
    }


def render_card(p: Problem, number: int, layout: dict) -> str:
    cell = layout["cell_mm"]
    box_w = max(2, len(str(p.answer)) + 1) * cell
    return (
        "<div class='card division'>"
        f"<div class='num'>{number}.</div>"
        "<div class='div-row'>"
        f"<span class='div-text'>{p.operand1} ÷ {p.operand2} =</span>"
        f"<span class='ans-box' style='width:{box_w:.2f}mm;'></span>"
        "</div>"
        "</div>"
    )
