# Math Exercise Sheets

A small web app that generates print-ready A4 math worksheets for Grade 2–3
students. Teachers pick operations, set number ranges, preview the layout
side-by-side with the form, then either **print directly** (and save as PDF
via the browser's print dialog) or **download the HTML** to email or archive.

No native libraries needed — the browser handles all rendering and PDF export.

---

## Installation

The app uses [uv](https://docs.astral.sh/uv/) to manage Python and
dependencies. Install uv once for your platform:

### macOS / Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Windows (PowerShell)

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

uv installs Python automatically the first time you `uv sync`, so you don't
need to install Python yourself.

---

## Running the app

### macOS / Linux

From the project folder:

```bash
uv sync                              # install dependencies (first time, or after pulling updates)
uv run uvicorn app.main:app          # start the server
```

Then open <http://127.0.0.1:8000> in your browser. Press `Ctrl+C` in the
terminal to stop the server.

### Windows

The project ships with two double-clickable launchers in the project folder:

| File | What it does |
|------|--------------|
| **`sync.cmd`** | Installs / refreshes dependencies (`uv sync`). Run this once after cloning, and again whenever you pull new code. |
| **`run.cmd`**  | Starts the local server on <http://127.0.0.1:8000>. Press `Ctrl+C` in the window to stop. |

Both windows close automatically on success. If something fails (uv not
installed, port already in use, missing files, etc.) the window stays open
so you can read the error before it disappears.

If you'd rather use the terminal directly:

```powershell
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

---

## Using the app

1. Open <http://127.0.0.1:8000>.
2. Tick the operations you want, set number ranges and counts.
3. Click **Preview worksheet** — the page renders in the right pane exactly
   as it will print, with A4 page boundaries visible.
4. Click **Print / Save as PDF**. Your browser's print dialog opens; choose
   *Save as PDF* there for a PDF, or print to paper directly.
5. Or click **Download HTML** to save the worksheet as a standalone file you
   can email, archive, or open later in any browser and print from there.

---

## How it works

- `app/generator.py` — builds problems (+, −, ×, ÷) given operand ranges
  and sorts them by a digits-plus-regrouping difficulty heuristic.
- `app/html_preview.py` — top-level renderer; paginates the worksheet into
  A4 `<div class="page">` blocks and writes the CSS shared by every page.
  Each operation gets its own page break.
- `app/render_common.py` — shared page geometry and small cell helpers.
- `app/render_mul.py` — multiplication: its own layout (bigger cells, 2
  cards per row for multi-digit) and its own card shape (operands, rule,
  N partial-product rows, rule, final-answer boxes).
- `app/render_div.py` — division: horizontal `a ÷ b = ⬜` for now,
  separated so it can grow into long-division later.
- `app/main.py` — FastAPI app:
  - `GET /` serves the form,
  - `POST /api/preview` returns the HTML for the iframe preview,
  - `POST /api/generate` returns the same HTML with a download header.
- `static/index.html` — the form, the preview pane, and Print/Download
  buttons.

---

## Layout overview

A4 portrait, 15 mm margins, black on white. The worksheet has:

- **Header** with Name / Date / Score fields and a centred title.
- **Sections** per operation (Addition → Subtraction → Multiplication →
  Division), sorted easiest-to-hardest within each section. **Each
  operation starts on its own page.**
- Each problem is a card in a 3-column grid (2-column for multi-digit
  multiplication to give the staircase more room):
  - **+ / −**, and **× with a 1-digit multiplier**: thin dashed carry
    row, two operand rows, a horizontal rule, bordered answer-box cells.
  - **× with a 2+-digit multiplier**: operand rows, rule, *N*
    partial-product rows (one per digit of the multiplier, each shifted
    left by one column, sized to the widest partial; inactive cells get
    a light dashed border so every column has a box), rule, final-answer
    boxes.
  - **÷**: horizontal `a ÷ b = ⬜`.
- A separate **Answer Key** page at the end, four columns.

Smart pagination: rows of problems never split across pages, and each
section keeps its heading on the page with its first row.
