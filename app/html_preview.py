"""
HTML preview of the worksheet.

Produces a standalone HTML page that visually mirrors the .docx output so a
teacher can see what they'll print *before* downloading the file. The same
problem generation + grouping logic is shared with the DOCX builder.
"""

from __future__ import annotations

from html import escape

from .generator import GenerationRequest, Problem, generate, max_digits

DIGIT_CELL_MM = 9
DIGIT_ROW_MM = 10
CARRY_ROW_MM = 5

SECTION_TITLES = {
    "+": "Addition",
    "-": "Subtraction",
    "×": "Multiplication",
    "÷": "Division",
}
GROUPING_ORDER = ["+", "-", "×", "÷"]


def _digit_cells(value: int, cols: int) -> str:
    s = str(value)
    pad = cols - len(s)
    out = []
    for _ in range(pad):
        out.append("<td class='dig'></td>")
    for ch in s:
        out.append(f"<td class='dig'>{escape(ch)}</td>")
    return "".join(out)


def _empty_cells(cls: str, cols: int) -> str:
    return "".join(f"<td class='{cls}'></td>" for _ in range(cols))


def _render_vertical(p: Problem, number: int, digit_cols: int) -> str:
    return (
        "<div class='card'>"
        f"<div class='num'>{number}.</div>"
        "<table class='vert'>"
        # carry row
        f"<tr class='r-carry'><td class='op'></td>{_empty_cells('carry', digit_cols)}</tr>"
        # operand 1
        f"<tr class='r-op'><td class='op'></td>{_digit_cells(p.operand1, digit_cols)}</tr>"
        # operand 2 with rule beneath
        f"<tr class='r-op rule'><td class='op'>{escape(p.operator)}</td>"
        f"{_digit_cells(p.operand2, digit_cols)}</tr>"
        # answer
        f"<tr class='r-ans'><td class='op'></td>{_empty_cells('ans', digit_cols)}</tr>"
        "</table>"
        "</div>"
    )


def _render_division(p: Problem, number: int) -> str:
    box_w = max(2, len(str(p.answer)) + 1) * DIGIT_CELL_MM
    return (
        "<div class='card'>"
        f"<div class='num'>{number}.</div>"
        "<div class='div-row'>"
        f"<span class='div-text'>{p.operand1} ÷ {p.operand2} =</span>"
        f"<span class='ans-box' style='width:{box_w}mm;'></span>"
        "</div>"
        "</div>"
    )


def _group(problems: list[Problem]) -> tuple[dict[str, list[Problem]], list[Problem]]:
    groups: dict[str, list[Problem]] = {op: [] for op in GROUPING_ORDER}
    for p in problems:
        groups[p.operator].append(p)
    for op in groups:
        groups[op].sort(key=lambda x: x.difficulty)
    ordered = [p for op in GROUPING_ORDER for p in groups[op]]
    return groups, ordered


CSS = f"""
  body {{
    background: #e8e9eb; margin: 0; padding: 16px;
    font-family: Arial, "Helvetica Neue", sans-serif; color: #111;
  }}
  .page {{
    width: 210mm; min-height: 297mm; padding: 15mm; background: white;
    box-sizing: border-box; margin: 0 auto 16px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.15);
  }}
  .hdr {{ font-size: 11pt; margin-bottom: 6pt; }}
  .hdr-line {{ letter-spacing: 0.5px; }}
  .title {{
    font-size: 18pt; font-weight: 700; text-align: center;
    margin: 4pt 0 10pt;
  }}
  .section-h {{ font-size: 13pt; font-weight: 700; margin: 14pt 0 8pt; }}
  .grid {{
    display: grid; grid-template-columns: 1fr 1fr 1fr;
    column-gap: 6mm; row-gap: 11mm;
  }}
  .card .num {{ font-size: 11pt; font-weight: 700; margin-bottom: 3pt; }}
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
  .ak-grid div {{ white-space: nowrap; }}
"""


def render_preview(req: GenerationRequest) -> str:
    problems = generate(req)
    title = escape(req.title or "Math Practice")
    if not problems:
        return _empty_html(title)

    groups, ordered = _group(problems)
    vertical = [p for p in problems if p.operator != "÷"]
    digit_cols = max_digits(vertical) if vertical else 1

    sections_html: list[str] = []
    num = 1
    for op in GROUPING_ORDER:
        section = groups[op]
        if not section:
            continue
        cards = []
        for p in section:
            if op == "÷":
                cards.append(_render_division(p, num))
            else:
                cards.append(_render_vertical(p, num, digit_cols))
            num += 1
        sections_html.append(
            f"<div class='section'>"
            f"<div class='section-h'>{SECTION_TITLES[op]}</div>"
            f"<div class='grid'>{''.join(cards)}</div>"
            "</div>"
        )

    answer_key_html = ""
    if req.include_answer_key and ordered:
        # column-major fill so reading order is left-to-right per row visually
        cols = 4
        rows_per_col = (len(ordered) + cols - 1) // cols
        col_entries: list[list[str]] = [[] for _ in range(cols)]
        for i, p in enumerate(ordered):
            col = i // rows_per_col if rows_per_col else 0
            col = min(col, cols - 1)
            col_entries[col].append(
                f"<div>{i + 1}.&nbsp; {p.operand1} {escape(p.operator)} "
                f"{p.operand2} = {p.answer}</div>"
            )
        cols_html = "".join(
            f"<div>{''.join(entries)}</div>" for entries in col_entries
        )
        answer_key_html = (
            "<div class='page'>"
            "<div class='ak-title'>Answer Key</div>"
            f"<div class='ak-grid'>{cols_html}</div>"
            "</div>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>{title} — Preview</title>
<style>{CSS}</style></head>
<body>
<div class='page'>
  <div class='hdr'><span class='hdr-line'>Name: ____________________________ &nbsp;&nbsp;
       Date: __________________ &nbsp;&nbsp; Score: ______</span></div>
  <div class='title'>{title}</div>
  {''.join(sections_html)}
</div>
{answer_key_html}
</body></html>
"""


def _empty_html(title: str) -> str:
    return (
        f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title>"
        f"<style>{CSS}</style></head><body><div class='page'>"
        "<p>No problems generated. Enable at least one operation and set a count.</p>"
        "</div></body></html>"
    )
