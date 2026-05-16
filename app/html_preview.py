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

from .generator import GenerationRequest, Problem, generate, max_digits

DIGIT_CELL_MM = 9
DIGIT_ROW_MM = 10
CARRY_ROW_MM = 5

# Page geometry — match the PDF output.
PAGE_HEIGHT_MM = 297
PAGE_MARGIN_MM = 15
PAGE_CONTENT_H = PAGE_HEIGHT_MM - 2 * PAGE_MARGIN_MM  # 267
PROBLEMS_PER_ROW = 3

# Approximate block heights (mm). Tuned by inspecting the rendered PDF so
# the preview shows the same number of rows per page that Word produces.
# Bumping these conservatively is safer (over-estimate = preview shows a page
# break slightly earlier than Word, never later, so the printed result fits).
H_HEADER_BLOCK = 24         # Name/Date/Score + title (first page only)
H_SECTION_HEADING = 11
H_VERTICAL_ROW = 67         # row of three boxed-digit cards (carry + 2 operands + answer + margins)
H_DIVISION_ROW = 38         # row of three horizontal division cards
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

    Each partial product gets its OWN width (the digit count of operand1 × that
    digit). Using a per-partial width prevents the leftmost partial from being
    forced into more columns than fit and overflowing into the operator column —
    e.g. 250 × 226's partials are 1500 (4-wide), 500 (3-wide), 500 (3-wide).
    """
    op2_str = str(p.operand2)
    op2_digits = len(op2_str)

    # rightmost-first: op2_str[-1] is the units digit (k=0), op2_str[0] is the
    # most-significant digit (k=op2_digits-1). The k-th partial product is
    # operand1 × digit_k and is shifted left by k columns.
    partials = []
    for k in range(op2_digits):
        digit = int(op2_str[-(k + 1)])
        product = p.operand1 * digit
        width = len(str(product)) if product != 0 else 1
        partials.append((k, width))

    op1_cells = _digit_cells(p.operand1, digit_cols)
    op2_cells = _digit_cells(p.operand2, digit_cols)

    partial_rows = []
    for idx, (k, width) in enumerate(partials):
        right_col = digit_cols - k                       # 1-indexed digit col
        left_col = right_col - width + 1
        is_last = (idx == len(partials) - 1)
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


def _render_division(p: Problem, number: int) -> str:
    box_w = max(2, len(str(p.answer)) + 1) * DIGIT_CELL_MM
    return (
        "<div class='card division'>"
        f"<div class='num'>{number}.</div>"
        "<div class='div-row'>"
        f"<span class='div-text'>{p.operand1} ÷ {p.operand2} =</span>"
        f"<span class='ans-box' style='width:{box_w}mm;'></span>"
        "</div>"
        "</div>"
    )


def _render_row(items: list[tuple[int, Problem]], digit_cols: int) -> str:
    """Render one row of (up to PROBLEMS_PER_ROW) problem cards inside a grid container."""
    parts = []
    for number, p in items:
        if p.operator == "÷":
            parts.append(_render_division(p, number))
        elif p.operator == "×" and len(str(p.operand2)) >= 2:
            parts.append(_render_multidigit_multiplication(p, number, digit_cols))
        else:
            parts.append(_render_vertical(p, number, digit_cols))
    # pad with invisible spacers so each row keeps PROBLEMS_PER_ROW columns
    for _ in range(PROBLEMS_PER_ROW - len(items)):
        parts.append("<div class='card spacer'></div>")
    return f"<div class='grid'>{''.join(parts)}</div>"


# ---------- pagination ----------

def _problem_height(p: Problem) -> int:
    if p.operator == "÷":
        return H_DIVISION_ROW
    if p.operator == "×" and len(str(p.operand2)) >= 2:
        # Tuned against the actual PDF output: a 2-digit × 2-digit card with
        # its 2 partial-product rows + final answer comes out to ~85-90mm in
        # Word, so 2 fit on the first page (under the header + section heading)
        # rather than 3. Each additional partial row adds ~11mm.
        op2_digits = len(str(p.operand2))
        return 90 + (op2_digits - 2) * 11
    return H_VERTICAL_ROW


def _row_height(items: list[tuple[int, Problem]]) -> int:
    # a row of three cards is as tall as the tallest card in it
    return max(_problem_height(p) for _, p in items)


def _paginate(
    groups: dict[str, list[Problem]],
    numbering: dict[int, int],
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
        n_rows = (len(problems) + PROBLEMS_PER_ROW - 1) // PROBLEMS_PER_ROW
        for ri in range(n_rows):
            slice_ = problems[ri * PROBLEMS_PER_ROW: (ri + 1) * PROBLEMS_PER_ROW]
            items = [(numbering[id(p)], p) for p in slice_]
            row_h = _row_height(items)
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

CSS = f"""
  /* Same HTML serves both the in-browser preview and WeasyPrint PDF output.
     @page rules + page-break rules apply when WeasyPrint renders, while
     @media screen rules give the iframe its "pages on a desk" look. */
  @page {{ size: A4; margin: 0; }}
  body {{
    margin: 0; font-family: Arial, "Helvetica Neue", sans-serif; color: #111;
  }}
  .page {{
    position: relative;
    width: 210mm; min-height: 297mm; padding: {PAGE_MARGIN_MM}mm;
    background: white; box-sizing: border-box; margin: 0 auto;
    page-break-after: always; break-after: page;
  }}
  .page:last-child {{
    page-break-after: auto; break-after: auto;
  }}
  @media screen {{
    body {{ background: #e8e9eb; padding: 16px; }}
    .page {{
      box-shadow: 0 1px 4px rgba(0,0,0,0.18); margin-bottom: 18px;
    }}
    /* hide the page tag in print (it's only useful in the live preview) */
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
    display: grid; grid-template-columns: 1fr 1fr 1fr;
    column-gap: 6mm; row-gap: 6mm;
    margin-bottom: 0;
  }}
  /* card footprints chosen so 3 vertical cards + section heading ≈ 232mm
     (matches the ~67mm-per-row footprint observed in the rendered PDF) */
  .card {{ min-height: 55mm; }}
  .card.division {{ min-height: 28mm; }}
  /* multi-digit multiplication: taller card with partial-product rows */
  .card.mul {{ min-height: 80mm; }}
  .card .num {{ font-size: 11pt; font-weight: 700; margin-bottom: 3pt; }}
  .card.spacer {{ visibility: hidden; min-height: 0; }}
  table.vert {{ border-collapse: collapse; table-layout: fixed; }}
  table.vert td {{
    width: {DIGIT_CELL_MM}mm; height: {DIGIT_ROW_MM}mm;
    text-align: center; vertical-align: middle; padding: 0;
    font-size: 18pt; line-height: 1; box-sizing: border-box;
  }}
  table.vert td.op {{ font-weight: 700; }}
  table.vert tr.r-carry td {{ height: {CARRY_ROW_MM}mm; }}
  table.vert tr.r-carry td.carry {{ border: 1px dashed #888; }}
  table.vert tr.rule td {{ border-bottom: 1.5pt solid #000; }}
  table.vert tr.r-ans td.ans {{ border: 1pt solid #000; }}
  /* partial-product rows for multi-digit multiplication */
  table.vert tr.r-partial td.pp-box {{ border: 1pt solid #000; }}
  table.vert tr.r-partial td.pp-empty {{ /* no border */ }}
  .div-row {{ display: flex; align-items: center; gap: 4mm; font-size: 16pt; }}
  .div-row .ans-box {{
    display: inline-block; height: {DIGIT_ROW_MM}mm;
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


def _render_block(block: dict, digit_cols: int) -> str:
    if block["type"] == "section_h":
        return f"<div class='section-h'>{escape(block['label'])}</div>"
    if block["type"] == "row":
        return _render_row(block["items"], digit_cols)
    return ""


def render_preview(req: GenerationRequest) -> str:
    problems = generate(req)
    title = escape(req.title or "Math Practice")
    if not problems:
        return _empty_html(title)

    groups, ordered, numbering = _group(problems)
    vertical = [p for p in problems if p.operator != "÷"]
    digit_cols = max_digits(vertical) if vertical else 1

    pages = _paginate(groups, numbering)
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
            parts.append(_render_block(block, digit_cols))
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
