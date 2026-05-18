"""
HTML preview / print source for the worksheet.

This module produces a single HTML document that serves both:
- the in-browser preview (the iframe in the form page),
- the downloadable / printable worksheet itself.

The HTML is paginated server-side into `<div class='page'>` blocks of fixed
A4 dimensions. CSS `@page` rules and `@media print` blocks turn those blocks
into actual page breaks when the user prints (browser Print dialog → Save
as PDF gives a clean A4 PDF); the screen styles add box-shadow and gutters
so the same DOM reads as "pages on a desk" in the iframe.

Each operation (Addition, Subtraction, Multiplication, Division) is treated
as an independent section with its OWN layout:

- it picks its own cards-per-row (e.g. 3 for addition, 2 for multi-digit
  multiplication) based on its own digit-column needs,
- it picks its own digit-cell size and font,
- it pages independently of other sections (and starts on a fresh page),
- it can use a completely different card layout (multi-digit multiplication
  has partial-product rows; division is horizontal).

The CSS is written once but parameterized via CSS custom properties
(`--cell-w`, `--cell-h`, `--font-size`, `--grid-cols`) set on each `.page`
element. That way every page renders according to its section's layout
without us having to emit per-section stylesheets.
"""

from __future__ import annotations

from html import escape
from typing import Iterable

from .generator import (
    GenerationRequest,
    Problem,
    generate,
    max_partial_width,
)
from . import render_div, render_mul

# ---------- page geometry ---------------------------------------------------

PAGE_HEIGHT_MM = 297
PAGE_WIDTH_MM = 210
PAGE_MARGIN_MM = 15
PAGE_CONTENT_H = PAGE_HEIGHT_MM - 2 * PAGE_MARGIN_MM        # 267
PAGE_CONTENT_W = PAGE_WIDTH_MM - 2 * PAGE_MARGIN_MM         # 180
COLUMN_GAP_MM = 6

H_HEADER_BLOCK = 24
H_SECTION_HEADING = 11
H_ANSWER_KEY_TITLE = 16
H_ANSWER_KEY_LINE = 6

SECTION_TITLES = {
    "+": "Addition",
    "-": "Subtraction",
    "×": "Multiplication",
    "÷": "Division",
}
GROUPING_ORDER = ["+", "-", "×", "÷"]


# ---------- section layouts -------------------------------------------------
#
# Each operator has its own layout function. They all return the same shape
# but pick numbers that make sense for that operation. Plumbing this through
# the rest of the file means each section in the worksheet can be sized
# independently.

def _fit_cells(per_row: int, cells_per_card: int, max_cell: float) -> float:
    """How wide can each digit cell be if we put per_row cards in a row?"""
    outer = (PAGE_CONTENT_W - (per_row - 1) * COLUMN_GAP_MM) / per_row
    return min(max_cell, (outer - 1) / cells_per_card)


def _font_for(cell_mm: float) -> int:
    return max(11, round(cell_mm * 2))   # 9mm → 18pt, 8mm → 16pt, 7mm → 14pt


def _section_digit_cols_add(problems: list[Problem]) -> int:
    n = 1
    for p in problems:
        n = max(n, len(str(p.operand1)), len(str(p.operand2)), len(str(p.answer)))
    return n


def _layout_addition(problems: list[Problem]) -> dict:
    """Addition + subtraction: 3-per-row grid, 9mm cells, 22mm row-gap.

    Card height — measured the way a browser actually renders it:

        problem number paragraph (11pt × 1.2 + 3pt margin):   ~5.7 mm
        carry row (carry_mm):                                 ~5   mm
        operand1 + operand2 + answer (3 × row_mm = 3 × 10mm): ~30   mm
        ─────────────────────────────────────────────────
        total content                                        ~40.7 mm

    Rounded to card_h = 41 mm. With a 22 mm row-gap and a 24 mm header
    + 11 mm section heading, 4 rows × 3 problems = 12 fit on page 1:
        4 × 41 + 3 × 22 + 35  =  265 mm  ≤  267 mm
    Pages 2 onward have no header so there's 37mm of bottom margin to
    spare.

    9mm cells / 18pt digits are the deliberate trade-off: the user
    explicitly prefers MORE vertical breathing room between rows over
    chunkier cells, given the carry-row stays. With 10mm cells the gap
    can only be 17mm. Smaller cells → bigger gap. Per the user.
    """
    digit_cols = _section_digit_cols_add(problems)
    cells_per_card = digit_cols + 1                 # +1 for the operator column
    per_row = 3
    cell_mm = _fit_cells(per_row, cells_per_card, max_cell=9)
    if cell_mm < 7:                                 # too cramped — drop a column
        per_row = 2
        cell_mm = _fit_cells(per_row, cells_per_card, max_cell=11)
    row_mm = cell_mm * 10 / 9
    carry_mm = max(3.5, cell_mm * 0.55)
    # 5.7mm for the problem-number paragraph + a small safety margin
    card_h = round(row_mm * 3 + carry_mm + 6)
    return {
        "op": "+",  # filled in by caller
        "digit_cols": digit_cols,
        "per_row": per_row,
        "cell_mm": cell_mm,
        "row_mm": row_mm,
        "carry_mm": carry_mm,
        "font_pt": _font_for(cell_mm),
        "card_h": card_h,
        "row_gap_mm": 22,                            # max gap with carry row at 12 per page
        "col_gap_mm": 12,
    }


# Multiplication's layout lives in render_mul — see app/render_mul.py.
_layout_multiplication = render_mul.compute_layout


# Division's layout lives in render_div — see app/render_div.py.
_layout_division = render_div.compute_layout


LAYOUTS = {
    "+": _layout_addition,
    "-": _layout_addition,
    "×": _layout_multiplication,
    "÷": _layout_division,
}


def _layout_for_section(op: str, problems: list[Problem]) -> dict:
    layout = LAYOUTS[op](problems)
    layout["op"] = op
    return layout


# ---------- per-card rendering ---------------------------------------------

def _digit_cells(value: int, cols: int) -> str:
    s = str(value)
    pad = cols - len(s)
    cells = ["<td class='dig'></td>"] * pad
    for ch in s:
        cells.append(f"<td class='dig'>{escape(ch)}</td>")
    return "".join(cells)


def _empty_cells(cls: str, cols: int) -> str:
    return "".join(f"<td class='{cls}'></td>" for _ in range(cols))


def _render_vertical(p: Problem, number: int, layout: dict) -> str:
    """Used for +, -, and single-digit-multiplier ×."""
    cols = layout["digit_cols"]
    return (
        "<div class='card vertical'>"
        f"<div class='num'>{number}.</div>"
        "<table class='vert'>"
        f"<tr class='r-carry'><td class='op'></td>{_empty_cells('carry', cols)}</tr>"
        f"<tr class='r-op'><td class='op'></td>{_digit_cells(p.operand1, cols)}</tr>"
        f"<tr class='r-op rule'><td class='op'>{escape(p.operator)}</td>"
        f"{_digit_cells(p.operand2, cols)}</tr>"
        f"<tr class='r-ans'><td class='op'></td>{_empty_cells('ans', cols)}</tr>"
        "</table>"
        "</div>"
    )


def _render_card(p: Problem, number: int, layout: dict) -> str:
    if p.operator == "÷":
        return render_div.render_card(p, number, layout)
    if p.operator == "×":
        return render_mul.render_card(p, number, layout)
    return _render_vertical(p, number, layout)


def _render_row(items: list[tuple[int, Problem]], layout: dict) -> str:
    parts = [_render_card(p, n, layout) for n, p in items]
    for _ in range(layout["per_row"] - len(items)):
        parts.append("<div class='card spacer'></div>")
    return f"<div class='grid'>{''.join(parts)}</div>"


# ---------- pagination ------------------------------------------------------

def _paginate_section(
    op: str,
    problems: list[Problem],
    numbering: dict[int, int],
    layout: dict,
    leading_room: int,
) -> list[list[dict]]:
    """
    Lay out one section's rows of cards across pages. `leading_room` is the
    height already consumed on the first page of this section (e.g. the
    Name/Date/Score header on page 1 of the worksheet); subsequent pages
    start fresh.

    Returns a list of pages; each page is a list of {"type": ..., ...} blocks.
    Each row-after-the-first-on-a-page costs `card_h + row_gap_mm` so the
    visual `row-gap` in the grid is reflected in pagination.
    """
    pages: list[list[dict]] = []
    current: list[dict] = []
    used = leading_room
    rows_on_current_page = 0
    per_row = layout["per_row"]
    card_h = layout["card_h"]
    row_gap_mm = layout.get("row_gap_mm", 6)

    n_rows = (len(problems) + per_row - 1) // per_row
    for ri in range(n_rows):
        slice_ = problems[ri * per_row: (ri + 1) * per_row]
        items = [(numbering[id(p)], p) for p in slice_]
        is_first_row_in_section = (ri == 0)
        heading_h = H_SECTION_HEADING if is_first_row_in_section else 0
        gap_before = row_gap_mm if rows_on_current_page > 0 else 0
        if current and used + heading_h + gap_before + card_h > PAGE_CONTENT_H:
            pages.append(current)
            current = []
            used = 0
            rows_on_current_page = 0
            gap_before = 0
        if is_first_row_in_section:
            current.append({"type": "section_h", "label": SECTION_TITLES[op]})
            used += H_SECTION_HEADING
        current.append({"type": "row", "items": items})
        used += gap_before + card_h
        rows_on_current_page += 1

    if current:
        pages.append(current)
    return pages


def _paginate_answer_key(ordered: list[Problem]) -> list[list[Problem]]:
    if not ordered:
        return []
    cols = 4
    available_h = PAGE_CONTENT_H - H_ANSWER_KEY_TITLE
    rows_per_page = max(1, available_h // H_ANSWER_KEY_LINE)
    per_page = rows_per_page * cols
    return [ordered[i:i + per_page] for i in range(0, len(ordered), per_page)]


def _group(
    problems: list[Problem],
) -> tuple[dict[str, list[Problem]], list[Problem], dict[int, int]]:
    groups: dict[str, list[Problem]] = {op: [] for op in GROUPING_ORDER}
    for p in problems:
        groups[p.operator].append(p)
    for op in groups:
        groups[op].sort(key=lambda x: x.difficulty)
    ordered = [p for op in GROUPING_ORDER for p in groups[op]]
    numbering = {id(p): i + 1 for i, p in enumerate(ordered)}
    return groups, ordered, numbering


# ---------- CSS -------------------------------------------------------------
#
# Written once, parameterized via CSS variables that each `.page` element
# sets via its inline `style="--cell-w: ...; --grid-cols: ...; ..."`.

CSS = f"""
  @page {{ size: A4; margin: 0; }}
  body {{
    margin: 0; font-family: Arial, "Helvetica Neue", sans-serif; color: #111;
  }}
  .page {{
    position: relative;
    width: {PAGE_WIDTH_MM}mm; min-height: {PAGE_HEIGHT_MM}mm;
    padding: {PAGE_MARGIN_MM}mm;
    background: white; box-sizing: border-box; margin: 0 auto;
    page-break-after: always; break-after: page;
  }}
  .page:last-child {{ page-break-after: auto; break-after: auto; }}
  @media screen {{
    body {{ background: #e8e9eb; padding: 16px; }}
    .page {{ box-shadow: 0 1px 4px rgba(0,0,0,0.18); margin-bottom: 18px; }}
  }}
  @media print {{
    .page-tag {{ display: none; }}
  }}
  .page-tag {{
    position: absolute; top: 6px; right: 10px;
    font-size: 10px; color: #999;
  }}
  .hdr {{ font-size: 11pt; margin-bottom: 6pt; letter-spacing: 0.3px; }}
  .title {{
    font-size: 18pt; font-weight: 700; text-align: center;
    margin: 4pt 0 10pt;
  }}
  .section-h {{ font-size: 13pt; font-weight: 700; margin: 14pt 0 8pt; }}
  .section-h:first-of-type {{ margin-top: 0; }}

  /* per-section layout values come from inline CSS variables on .page */
  .grid {{
    display: grid;
    grid-template-columns: var(--grid-cols, 1fr 1fr 1fr);
    column-gap: var(--col-gap, {COLUMN_GAP_MM}mm);
    row-gap: var(--row-gap, 6mm);
  }}
  .card .num {{ font-size: 11pt; font-weight: 700; margin-bottom: 3pt; }}
  .card.spacer {{ visibility: hidden; }}
  table.vert {{ border-collapse: collapse; table-layout: fixed; }}
  table.vert td {{
    width: var(--cell-w, 9mm);
    height: var(--cell-h, 10mm);
    text-align: center; vertical-align: middle; padding: 0;
    font-size: var(--font-size, 18pt);
    line-height: 1; box-sizing: border-box;
  }}
  table.vert td.op {{ font-weight: 700; }}
  table.vert tr.r-carry td {{ height: var(--carry-h, 5mm); }}
  table.vert tr.r-carry td.carry {{ border: 1px dashed #888; }}
  table.vert tr.rule td {{ border-bottom: 1.5pt solid #000; }}
  table.vert tr.r-ans td.ans {{ border: 1pt solid #000; }}
  table.vert tr.r-partial td.pp-box {{ border: 1pt solid #000; }}
  /* inactive cells in a partial row: a light dashed box so the student
     still sees a complete grid (no "missing" boxes), while the solid
     borders mark where this particular partial product should land */
  table.vert tr.r-partial td.pp-empty {{ border: 0.75pt dashed #b8b8b8; }}
  /* the rule under the LAST partial row needs to win over both pp-box's
     1pt bottom and pp-empty's dashed bottom, so it's drawn at full strength */
  table.vert tr.r-partial.rule td {{ border-bottom: 1.5pt solid #000; }}

  .div-row {{
    display: flex; align-items: center; gap: 4mm;
    font-size: var(--div-font, 16pt);
  }}
  .div-row .ans-box {{
    display: inline-block; height: var(--cell-h, 10mm);
    border: 1pt solid #000;
  }}

  .ak-title {{ text-align: center; font-size: 18pt; font-weight: 700; margin: 0 0 12pt; }}
  .ak-grid {{
    display: grid; grid-template-columns: 1fr 1fr 1fr 1fr;
    column-gap: 6mm; row-gap: 2mm; font-size: 11pt;
  }}
  .ak-grid > div {{ white-space: nowrap; }}
"""


def _page_style(layout: dict) -> str:
    """Inline CSS-variable declarations for a section's layout, attached to its .page."""
    grid_cols = " ".join(["1fr"] * layout["per_row"])
    row_gap = layout.get("row_gap_mm", 6)
    col_gap = layout.get("col_gap_mm", COLUMN_GAP_MM)
    return (
        f"--cell-w:{layout['cell_mm']:.3f}mm;"
        f"--cell-h:{layout['row_mm']:.3f}mm;"
        f"--font-size:{layout['font_pt']}pt;"
        f"--carry-h:{layout['carry_mm']:.3f}mm;"
        f"--div-font:{max(12, layout['font_pt'] - 2)}pt;"
        f"--grid-cols:{grid_cols};"
        f"--row-gap:{row_gap}mm;"
        f"--col-gap:{col_gap}mm;"
    )


# ---------- top-level render ------------------------------------------------

def _render_header() -> str:
    return (
        "<div class='hdr'>"
        "Name: ____________________________ &nbsp;&nbsp; "
        "Date: __________________ &nbsp;&nbsp; Score: ______"
        "</div>"
    )


def _render_block(block: dict, layout: dict) -> str:
    if block["type"] == "section_h":
        return f"<div class='section-h'>{escape(block['label'])}</div>"
    if block["type"] == "row":
        return _render_row(block["items"], layout)
    return ""


def render_preview(req: GenerationRequest) -> str:
    problems = generate(req)
    title = escape(req.title or "Math Practice")
    if not problems:
        return _empty_html(title)

    groups, ordered, numbering = _group(problems)

    # Paginate each operation independently using its own layout.
    section_pages: list[tuple[dict, list[dict]]] = []      # (layout, blocks-per-page)
    is_first_section = True
    for op in GROUPING_ORDER:
        ps = groups[op]
        if not ps:
            continue
        layout = _layout_for_section(op, ps)
        leading_room = H_HEADER_BLOCK if is_first_section else 0
        for blocks in _paginate_section(op, ps, numbering, layout, leading_room):
            section_pages.append((layout, blocks))
        is_first_section = False

    answer_key_pages = (
        _paginate_answer_key(ordered) if req.include_answer_key else []
    )
    total_pages = len(section_pages) + len(answer_key_pages)

    rendered_pages: list[str] = []
    for i, (layout, page_blocks) in enumerate(section_pages):
        parts = [f"<div class='page-tag'>Page {i + 1} of {total_pages}</div>"]
        if i == 0:
            parts.append(_render_header())
            parts.append(f"<div class='title'>{title}</div>")
        for block in page_blocks:
            parts.append(_render_block(block, layout))
        rendered_pages.append(
            f"<div class='page' style=\"{_page_style(layout)}\">"
            f"{''.join(parts)}</div>"
        )

    base_page = len(section_pages)
    for j, chunk in enumerate(answer_key_pages):
        cols = 4
        rows_per_col = (len(chunk) + cols - 1) // cols
        col_entries: list[list[str]] = [[] for _ in range(cols)]
        for k, p in enumerate(chunk):
            n = numbering[id(p)]
            col = k // rows_per_col if rows_per_col else 0
            col = min(col, cols - 1)
            col_entries[col].append(
                f"<div>{n}.&nbsp; {p.operand1} {escape(p.operator)} "
                f"{p.operand2} = {p.answer}</div>"
            )
        cols_html = "".join(
            f"<div>{''.join(entries)}</div>" for entries in col_entries
        )
        page_no = base_page + j + 1
        rendered_pages.append(
            "<div class='page'>"
            f"<div class='page-tag'>Page {page_no} of {total_pages}"
            f"&nbsp;·&nbsp;Answer Key</div>"
            "<div class='ak-title'>Answer Key</div>"
            f"<div class='ak-grid'>{cols_html}</div>"
            "</div>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>{title} — Preview</title>
<style>{CSS}</style></head>
<body>
{"".join(rendered_pages)}
</body></html>
"""


def _empty_html(title: str) -> str:
    return (
        f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title>"
        f"<style>{CSS}</style></head><body><div class='page'>"
        "<p>No problems generated. Enable at least one operation and set a count.</p>"
        "</div></body></html>"
    )
