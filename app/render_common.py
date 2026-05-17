"""
Shared helpers used by every per-operation renderer.

Page geometry, a few small HTML-cell utilities, and the routines that
size digit cells to fit a chosen cards-per-row count. Each renderer
module (`render_add`, `render_mul`, `render_div`) imports from here.
"""

from __future__ import annotations

from html import escape

PAGE_HEIGHT_MM = 297
PAGE_WIDTH_MM = 210
PAGE_MARGIN_MM = 15
PAGE_CONTENT_H = PAGE_HEIGHT_MM - 2 * PAGE_MARGIN_MM        # 267
PAGE_CONTENT_W = PAGE_WIDTH_MM - 2 * PAGE_MARGIN_MM         # 180
COLUMN_GAP_MM = 6


def fit_cells(per_row: int, cells_per_card: int, max_cell: float) -> float:
    """How wide can each digit cell be if we put per_row cards in a row?"""
    outer = (PAGE_CONTENT_W - (per_row - 1) * COLUMN_GAP_MM) / per_row
    return min(max_cell, (outer - 1) / cells_per_card)


def font_for(cell_mm: float) -> int:
    """A digit font size that scales with the cell — 9mm→18pt, 11mm→22pt."""
    return max(11, round(cell_mm * 2))


def digit_cells(value: int, cols: int) -> str:
    """A row of `cols` table cells, right-aligning the digits of `value`."""
    s = str(value)
    pad = cols - len(s)
    cells = ["<td class='dig'></td>"] * pad
    for ch in s:
        cells.append(f"<td class='dig'>{escape(ch)}</td>")
    return "".join(cells)


def empty_cells(cls: str, cols: int) -> str:
    """A row of `cols` empty cells with the given CSS class."""
    return "".join(f"<td class='{cls}'></td>" for _ in range(cols))
