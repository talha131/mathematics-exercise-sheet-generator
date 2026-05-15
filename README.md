# Math Exercise Sheets

A small web app that generates print-ready A4 math worksheets (Word `.docx`)
for Grade 2–3 students. Teachers pick operations, set number ranges, and
download a worksheet with boxed-digit working space plus an answer key.

## Setup (uv)

```bash
# from the project root
uv sync          # installs FastAPI, uvicorn, python-docx, pydantic
uv run uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000>.

## How it works

- `app/generator.py` — builds problems (+, −, ×, ÷) given operand ranges and
  sorts them by a digits-plus-regrouping difficulty heuristic.
- `app/docx_builder.py` — emits A4 portrait `.docx` with a header row,
  numbered problems laid out in a 3-column grid of boxed-digit "cards" (thin
  carry row, two operand rows, a horizontal rule, then bordered answer
  boxes), plus a separate Answer Key page.
- `app/main.py` — FastAPI app that serves the form and returns the `.docx`.
- `static/index.html` — single-page form.

## Print notes

Output is A4, black-and-white, 15 mm margins. Open the file in Word /
LibreOffice / Pages and print as-is.
