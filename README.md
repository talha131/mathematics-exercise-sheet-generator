# Math Exercise Sheets

A small web app that generates print-ready A4 math worksheets (PDF) for
Grade 2–3 students. Teachers pick operations, set number ranges, preview
the layout in the browser, then download a PDF that exactly matches what
they saw.

## Setup (uv)

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000>.

### System dependencies

WeasyPrint needs Cairo, Pango and GDK-PixBuf. On macOS:

```bash
brew install pango libffi
```

On Debian/Ubuntu:

```bash
sudo apt install libpango-1.0-0 libpangoft2-1.0-0
```

## How it works

- `app/generator.py` — builds problems (+, −, ×, ÷) given operand ranges
  and sorts them by a digits-plus-regrouping difficulty heuristic.
- `app/html_preview.py` — renders the worksheet as a single HTML page,
  pre-paginated into `<div class="page">` blocks. The same HTML serves
  both the in-browser preview and the PDF output. CSS `@media print`
  rules turn the page divs into actual page breaks when WeasyPrint runs.
- `app/pdf_builder.py` — calls WeasyPrint to convert the HTML to PDF.
- `app/main.py` — FastAPI app:
  - `GET  /`            serves the form
  - `POST /api/preview` returns the HTML preview
  - `POST /api/generate` returns the PDF
- `static/index.html` — single-page form with a side-by-side preview pane.

## Layout

A4 portrait, 15 mm margins, black on white. The worksheet has:

- Header with **Name / Date / Score** fields and a centred title.
- Sections per operation (Addition → Subtraction → Multiplication → Division),
  sorted easiest-to-hardest within each section.
- Each problem is a card in a 3-column grid:
  - **+, −**: thin dashed carry row, two operand rows with digits in cells,
    a horizontal rule, and bordered answer-box cells.
  - **× with 2+ digit multiplier**: operand rows, rule, *N* partial-product
    rows (one per digit of the multiplier, each shifted left and sized to the
    actual partial-product width), rule, final-answer boxes.
  - **× with 1-digit multiplier**: same layout as +/−.
  - **÷**: horizontal `a ÷ b = ⬜`.
- A separate **Answer Key** page (or pages) at the end, four columns.

Smart pagination: rows of problems never split across pages, and a section
heading always travels with its first row.
