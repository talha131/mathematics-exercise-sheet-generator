# Math Exercise Sheets

A small web app that generates print-ready A4 math worksheets for Grade 2–3
students. Teachers pick operations, set number ranges, preview the layout
side-by-side with the form, then either **print directly** (and save as PDF
via the browser's print dialog) or **download the HTML** to email or archive.

No native libraries needed — the browser handles all rendering and PDF export.

## Setup (uv)

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000>.

That's it — no Cairo, no Pango, no LibreOffice, no Word. Pure Python on the
server, HTML/CSS in the browser.

## Using it

1. Tick the operations you want, set number ranges and counts.
2. Click **Preview worksheet** — the page renders in the right pane exactly
   as it will print, with A4 page boundaries visible.
3. Click **Print / Save as PDF**. Your browser's print dialog opens; choose
   *Save as PDF* there to get a PDF, or print to paper directly.
4. Or click **Download HTML** to save the worksheet as a standalone file.
   You can email it, archive it, or open it later in any browser and print
   from there.

## How it works

- `app/generator.py` — builds problems (+, −, ×, ÷) given operand ranges
  and sorts them by a digits-plus-regrouping difficulty heuristic.
- `app/html_preview.py` — renders the worksheet as a single self-contained
  HTML document, pre-paginated into A4-sized `<div class="page">` blocks.
  CSS `@page` rules + `@media print` blocks turn those blocks into real
  page breaks when the browser prints.
- `app/main.py` — FastAPI app:
  - `GET  /`             serves the form
  - `POST /api/preview`  returns the HTML for the iframe preview
  - `POST /api/generate` returns the same HTML with a download header
- `static/index.html` — the form, the preview pane, and Print/Download
  buttons.

## Layout

A4 portrait, 15 mm margins, black on white. The worksheet has:

- Header with **Name / Date / Score** fields and a centred title.
- Sections per operation (Addition → Subtraction → Multiplication → Division),
  sorted easiest-to-hardest within each section.
- Each problem is a card in a 3-column grid:
  - **+, −, × (1-digit multiplier)**: thin dashed carry row, two operand
    rows with digits in cells, a horizontal rule, and bordered answer-box
    cells.
  - **× with 2+ digit multiplier**: operand rows, rule, *N* partial-product
    rows (one per digit of the multiplier, each shifted left and sized to
    the actual partial-product width), rule, final-answer boxes.
  - **÷**: horizontal `a ÷ b = ⬜`.
- A separate **Answer Key** page at the end, four columns.

Smart pagination: rows of problems never split across pages, and a section
heading always travels with its first row.
