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
"""

from __future__ import annotations

from html import escape

from .generator import (
    GenerationRequest,
    Problem,
    generate,
    max_digits,
    max_partial_width,
)

# Page geometry.
PAGE_HEIGHT_MM = 297
PAGE_WIDTH_MM = 210
PAGE_MARGIN_MM = 15
PAGE_CONTENT_H = PAGE_HEIGHT_MM - 2 * PAGE_MARGIN_MM    # 267
PAGE_CONTENT_W = PAGE_WIDTH_MM - 2 * PAGE_MARGIN_MM     # 180
COLUMN_GAP_MM = 6

# Caps / defaults for digit cells. The actual values are computed adaptively
# so a card with N digit columns always fits inside its outer grid cell.
MAX_DIGIT_CELL_MM = 9
MIN_DIGIT_CELL_MM = 6
DEFAULT_FONT_PT = 18
CARRY_ROW_RATIO = 0.5     # carry row is half the height of a regular row


def _layout_for(digit_cols: int) -> tuple[int, float, float, int]:
    """
    Pick how many problem cards go in a row and how big each digit cell is,
    given the maximum digit-column count any problem needs.

    Returns (problems_per_row, cell_mm, row_mm, font_pt).

    The card width is (digit_cols + 1) × cell_mm (+1 for the operator column).
    We size the cells so that problems_per_row cards fit inside the page's
    content width with COLUMN_GAP_MM between them; we drop from 3 cards/row
    to 2 cards/row once even a 6mm cell wouldn't fit at 3 cards/row.
    """
    for per_row in (3, 2, 1):
        outer = (PAGE_CONTENT_W - (per_row - 1) * COLUMN_GAP_MM) / per_row
        # leave ~1 mm slack so border-collapse doesn't push the card past its
        # grid cell on subpixel-rendering browsers
        cell = (outer - 1) / (digit_cols + 1)
        if cell >= MIN_DIGIT_CELL_MM:
            cell = min(MAX_DIGIT_CELL_MM, cell)
            row = cell * (10 / 9)              # keep the same aspect as 9 × 10mm
            font = max(11, round(cell * 2))    # 9mm → 18pt, 8mm → 16pt, 7mm → 14pt
            return per_row, cell, row, font
    # extremely wide worksheets fall back to 1-per-row with the smallest cell
    cell = MIN_DIGIT_CELL_MM
    return 1, cell, cell * (10 / 9), max(11, round(cell * 2))

# Block heights (mm) for the standard 9mm-cell layout. They scale linearly
# with row_mm in `_problem_height` below.
H_HEADER_BLOCK = 24         # Name/Date/Score + title (first page only)
H_SECTION_HEADING = 11
H_VERTICAL_ROW_AT_9MM = 67  # carry + 2 operands + answer row + margins
H_DIVISION_ROW_AT_9MM = 38
H_MUL_2DIG_AT_9MM = 90      # multi-digit mul with 2-digit operand2
H_MUL_PER_EXTRA_AT_9MM = 11 # extra height per additional digit beyond 2-digit
H_ANSWER_KEY_TITLE = 16
H_ANSWER_KEY_LINE = 6

SECTION_TITLES = {
    "+": "Addition",
    "-": "Subtraction",
    "×": "Multiplication",
    "÷": "Division",
}
GROUPING_ORDER = ["+", "-", "×", "÷"]


# ---------- per-card rendering ----------

def _digit_cells(value: int, cols: int) -> str:
    s = str(value)
    pad = cols - len(s)
    cells = ["<td class='dig'></td>"] * pad
    for ch in s:
        cells.append(f"<td class='dig'>{escape(ch)}</td>")
    return "".join(cells)


def _empty_cells(cls: str, cols: int) -> str:
    return "".join(f"<td class='{cls}'></td>" for _ in range(cols))


def _render_vertical(p: Problem, number: int, digit_cols: int) -> str:
    return (
        "<div class='card vertical'>"
        f"<div class='num'>{number}.</div>"
        "<table class='vert'>"
        f"<tr class='r-carry'><td class='op'></td>{_empty_cells('carry', digit_cols)}</tr>"
        f"<tr class='r-op'><td class='op'></td>{_digit_cells(p.operand1, digit_cols)}</tr>"
        f"<tr class='r-op rule'><td class='op'>{escape(p.operator)}</td>"
        f"{_digit_cells(p.operand2, digit_cols)}</tr>"
        f"<tr class='r-ans'><td class='op'></td>{_empty_cells('ans', digit_cols)}</tr>"
        "</table>"
        "</div>"
    )


def _render_multidigit_multiplication(p: Problem, number: int, digit_cols: int) -> str:
    """Multi-digit × multi-digit with N partial-product rows and a final answer.

    All partial-product rows are drawn at the SAME width within a problem
    (the maximum digit count of any partial), so the staircase is regular —
    only the *shift* changes between rows. `max_digits()` ensures
    `digit_cols` is big enough that even the leftmost (most-shifted) partial
    fits inside the digit columns and doesn't bleed into the operator column.

    Example, 341 × 516: partials are 2046, 341, 1705. Max width = 4, so
    every partial gets 4 boxes; the rows step left by 0, 1, 2 columns.
    """
    op2_str = str(p.operand2)
    op2_digits = len(op2_str)
    width = max_partial_width(p)

    op1_cells = _digit_cells(p.operand1, digit_cols)
    op2_cells = _digit_cells(p.operand2, digit_cols)

    partial_rows = []
    for k in range(op2_digits):
        right_col = digit_cols - k                       # 1-indexed digit col
        left_col = right_col - width + 1
        is_last = (k == op2_digits - 1)
        row_class = "r-partial rule" if is_last else "r-partial"
        cells = []
        for ci in range(1, digit_cols + 1):
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
        f"<tr class='r-ans'><td class='op'></td>{_empty_cells('ans', digit_cols)}</tr>"
        "</table>"
        "</div>"
    )


def _render_division(p: Problem, number: int, cell_mm: float) -> str:
    box_w = max(2, len(str(p.answer)) + 1) * cell_mm
    return (
        "<div class='card division'>"
        f"<div class='num'>{number}.</div>"
        "<div class='div-row'>"
        f"<span class='div-text'>{p.operand1} ÷ {p.operand2} =</span>"
        f"<span class='ans-box' style='width:{box_w:.2f}mm;'></span>"
        "</div>"
        "</div>"
    )


def _render_row(
    items: list[tuple[int, Problem]],
    digit_cols: int,
    per_row: int,
    cell_mm: float,
) -> str:
    """Render one row of (up to per_row) problem cards inside a grid container."""
    parts = []
    for number, p in items:
        if p.operator == "÷":
            parts.append(_render_division(p, number, cell_mm))
        elif p.operator == "×" and len(str(p.operand2)) >= 2:
            parts.append(_render_multidigit_multiplication(p, number, digit_cols))
        else:
            parts.append(_render_vertical(p, number, digit_cols))
    # pad with invisible spacers so each row keeps per_row columns
    for _ in range(per_row - len(items)):
        parts.append("<div class='card spacer'></div>")
    return f"<div class='grid'>{''.join(parts)}</div>"


# ---------- pagination ----------

def _problem_height(p: Problem, row_mm: float) -> int:
    scale = row_mm / 10.0
    if p.operator == "÷":
        return round(H_DIVISION_ROW_AT_9MM * scale)
    if p.operator == "×" and len(str(p.operand2)) >= 2:
        op2_digits = len(str(p.operand2))
        base = H_MUL_2DIG_AT_9MM + (op2_digits - 2) * H_MUL_PER_EXTRA_AT_9MM
        return round(base * scale)
    return round(H_VERTICAL_ROW_AT_9MM * scale)


def _row_height(items: list[tuple[int, Problem]], row_mm: float) -> int:
    # a row of cards is as tall as the tallest card in it
    return max(_problem_height(p, row_mm) for _, p in items)


def _paginate(
    groups: dict[str, list[Problem]],
    numbering: dict[int, int],
    per_row: int,
    row_mm: float,
) -> list[list[dict]]:
    """
    Walk through sections row-by-row, emitting page boundaries when adding the
    next row (plus any incoming section heading) would overflow.

    `numbering` maps id(problem) -> 1-based worksheet number.

    Returns a list of pages; each page is a list of "block" dicts of the form
        {"type": "section_h", "label": "..."}
        {"type": "row", "items": [(number, problem), ...]}
    The header block is omitted here — the caller adds it before page 1.
    """
    pages: list[list[dict]] = []
    current: list[dict] = []
    used = H_HEADER_BLOCK  # first page has the header

    for op in GROUPING_ORDER:
        problems = groups[op]
        if not problems:
            continue
        # Each operation starts on its own page. The first non-empty section
        # uses page 1 (which already includes the header); every later section
        # flushes the current page and begins a new one.
        if current:
            pages.append(current)
            current = []
            used = 0
        n_rows = (len(problems) + per_row - 1) // per_row
        for ri in range(n_rows):
            slice_ = problems[ri * per_row: (ri + 1) * per_row]
            items = [(numbering[id(p)], p) for p in slice_]
            row_h = _row_height(items, row_mm)
            needs_heading = (ri == 0)
            extra = H_SECTION_HEADING if needs_heading else 0
            if current and used + extra + row_h > PAGE_CONTENT_H:
                pages.append(current)
                current = []
                used = 0
            if needs_heading:
                current.append({"type": "section_h", "label": SECTION_TITLES[op]})
                used += H_SECTION_HEADING
            current.append({"type": "row", "items": items})
            used += row_h

    if current:
        pages.append(current)
    return pages


def _paginate_answer_key(ordered: list[Problem]) -> list[list[Problem]]:
    """Split the ordered answer list into pages of ~40 lines each (4 cols × ~10 rows)."""
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


# ---------- CSS ----------

def _build_css(per_row: int, cell_mm: float, row_mm: float, font_pt: int) -> str:
    """
    CSS is parameterized on the chosen layout so the same template works for
    a 3-cards-per-row addition worksheet AND a 2-cards-per-row 3-digit-×-3-digit
    multiplication worksheet. Each digit cell is `cell_mm` wide, operand/answer
    rows are `row_mm` tall, digits inside boxes render at `font_pt` points.
    """
    carry_mm = max(3.5, cell_mm * 0.55)        # thin carry row
    grid_cols = " ".join(["1fr"] * per_row)
    div_font_pt = max(12, font_pt - 2)
    return f"""
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
  .page:last-child {{
    page-break-after: auto; break-after: auto;
  }}
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
  .section-h:first-child {{ margin-top: 0; }}
  .grid {{
    display: grid; grid-template-columns: {grid_cols};
    column-gap: {COLUMN_GAP_MM}mm; row-gap: 6mm;
    margin-bottom: 0;
  }}
  .card .num {{ font-size: 11pt; font-weight: 700; margin-bottom: 3pt; }}
  .card.spacer {{ visibility: hidden; }}
  table.vert {{ border-collapse: collapse; table-layout: fixed; }}
  table.vert td {{
    width: {cell_mm:.3f}mm; height: {row_mm:.3f}mm;
    text-align: center; vertical-align: middle; padding: 0;
    font-size: {font_pt}pt; line-height: 1; box-sizing: border-box;
  }}
  table.vert td.op {{ font-weight: 700; }}
  table.vert tr.r-carry td {{ height: {carry_mm:.3f}mm; }}
  table.vert tr.r-carry td.carry {{ border: 1px dashed #888; }}
  table.vert tr.rule td {{ border-bottom: 1.5pt solid #000; }}
  table.vert tr.r-ans td.ans {{ border: 1pt solid #000; }}
  table.vert tr.r-partial td.pp-box {{ border: 1pt solid #000; }}
  table.vert tr.r-partial td.pp-empty {{ /* no border */ }}
  .div-row {{
    display: flex; align-items: center; gap: 4mm;
    font-size: {div_font_pt}pt;
  }}
  .div-row .ans-box {{
    display: inline-block; height: {row_mm:.3f}mm;
    border: 1pt solid #000;
  }}
  .ak-title {{ text-align: center; font-size: 18pt; font-weight: 700; margin: 0 0 12pt; }}
  .ak-grid {{
    display: grid; grid-template-columns: 1fr 1fr 1fr 1fr;
    column-gap: 6mm; row-gap: 2mm; font-size: 11pt;
  }}
  .ak-grid > div {{ white-space: nowrap; }}
"""


# ---------- top-level render ----------

def _render_header() -> str:
    return (
        "<div class='hdr'>"
        "Name: ____________________________ &nbsp;&nbsp; "
        "Date: __________________ &nbsp;&nbsp; Score: ______"
        "</div>"
    )


def _render_block(block: dict, digit_cols: int, per_row: int, cell_mm: float) -> str:
    if block["type"] == "section_h":
        return f"<div class='section-h'>{escape(block['label'])}</div>"
    if block["type"] == "row":
        return _render_row(block["items"], digit_cols, per_row, cell_mm)
    return ""


def render_preview(req: GenerationRequest) -> str:
    problems = generate(req)
    title = escape(req.title or "Math Practice")
    if not problems:
        return _empty_html(title)

    groups, ordered, numbering = _group(problems)
    vertical = [p for p in problems if p.operator != "÷"]
    digit_cols = max_digits(vertical) if vertical else 1
    per_row, cell_mm, row_mm, font_pt = _layout_for(digit_cols)
    css = _build_css(per_row, cell_mm, row_mm, font_pt)

    pages = _paginate(groups, numbering, per_row, row_mm)
    answer_key_pages = (
        _paginate_answer_key(ordered) if req.include_answer_key else []
    )

    total_pages = len(pages) + len(answer_key_pages)
    rendered_pages: list[str] = []

    for i, page_blocks in enumerate(pages):
        parts = [f"<div class='page-tag'>Page {i + 1} of {total_pages}</div>"]
        if i == 0:
            parts.append(_render_header())
            parts.append(f"<div class='title'>{title}</div>")
        for block in page_blocks:
            parts.append(_render_block(block, digit_cols, per_row, cell_mm))
        rendered_pages.append(f"<div class='page'>{''.join(parts)}</div>")

    base_page = len(pages)
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
<style>{css}</style></head>
<body>
{"".join(rendered_pages)}
</body></html>
"""


def _empty_html(title: str) -> str:
    # use the default layout for the empty page — nothing to size against
    _, cell_mm, row_mm, font_pt = _layout_for(3)
    css = _build_css(3, cell_mm, row_mm, font_pt)
    return (
        f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title>"
        f"<style>{css}</style></head><body><div class='page'>"
        "<p>No problems generated. Enable at least one operation and set a count.</p>"
        "</div></body></html>"
    )
