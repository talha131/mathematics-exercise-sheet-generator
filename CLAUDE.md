# CLAUDE.md — project memory

Reading this file should be the first thing a fresh Claude session does
when working in this repo. It captures the *why* behind the code, the
constraints we've already discovered, and the conventions we've settled
on, so we don't relitigate the same trade-offs.

---

## What this project is

A small FastAPI web app that generates **print-ready A4 math worksheets**
for **Grade 2–3** students. A teacher fills in a form, previews the
worksheet in an iframe, then prints from the browser (or downloads the
HTML for archiving). Output goes through the browser's native print
dialog — saving as PDF is a one-click action there.

Primary user: **teachers** who want to print custom worksheets.
End reader: **young students** who write their work directly on the
printed page.

---

## Stack

- **Python ≥ 3.10**, managed by **uv**.
- **FastAPI** for the HTTP layer, **uvicorn** for the server.
- **No native libraries.** No WeasyPrint, no Cairo, no Pango, no
  LibreOffice, no python-docx. The browser is the renderer.
- Pure HTML/CSS for the worksheet. CSS Grid for layout, `@page` and
  `@media print` rules so the same DOM works on screen and on paper.
- Single-page form in `static/index.html` with vanilla JS — no front-end
  framework, no build step.

**Why no native libs:** earlier iterations used python-docx and then
WeasyPrint. Both had problems — python-docx forced us to fight Word's
table-rendering quirks for every layout tweak, and WeasyPrint demanded
Cairo/Pango/etc. and was the first thing to break on a fresh machine.
The browser is universally available, renders CSS Grid pixel-perfectly,
and its print dialog gives the user PDF-save for free. We don't want
to give that up.

### Output-format pivot history

| Era | Stack | Why it failed |
|-----|-------|---------------|
| **v1 — python-docx** | Generated `.docx` with nested tables; one outer table per problem-row, one inner table per problem card. Used `cantSplit` and `keep_with_next` for pagination. | Word's table-rendering is hostile to per-cell border control. Multi-digit multiplication's partial-product staircase was broken: cells had slightly different widths, the operator column was invaded when partials were uniform-width, the horizontal rule didn't span the row correctly. Every tweak fought Word. |
| **v2 — WeasyPrint** | Pivoted to rendering the same HTML used for the iframe preview straight to PDF with WeasyPrint. Pixel-perfect output, single source of truth for layout. | First time the user installed it on a fresh machine, WeasyPrint failed with "could not import some external libraries" (Cairo/Pango missing). The fix is a system package install — not acceptable for a teacher running this from a double-clickable launcher. |
| **v3 — browser-printed HTML (current)** | The form returns plain HTML. The user clicks **Print / Save as PDF** in the form, which calls `window.print()` on the preview iframe; the browser's own print dialog produces the PDF. **Zero native deps.** | This is where we are. Trade-off: one extra click in the print dialog. |

If anyone proposes going back to PDF generation or .docx output, the
default answer is "no, we already tried". Counter-cases would need to
solve the install problem for non-developer users.

---

## Architecture

```
app/
  generator.py        — problem generation (+, −, ×, ÷); difficulty heuristic
  main.py             — FastAPI app: GET /, POST /api/preview, POST /api/generate
  html_preview.py     — top-level renderer: pagination, CSS, page layout
  render_common.py    — shared page geometry + small HTML cell helpers
  render_mul.py       — multiplication renderer (single-digit + multi-digit cards)
  render_div.py       — division renderer
static/
  index.html          — single-page form + side-by-side preview pane
sync.cmd / run.cmd    — Windows double-clickable launchers
pyproject.toml        — uv project, ≥3.10
```

### How a render works

1. `generator.generate(req)` produces a list of `Problem` objects, sorted
   by an internal difficulty heuristic.
2. `html_preview.render_preview` groups problems by operator, in the
   fixed order `["+", "-", "×", "÷"]`.
3. For each operator's section, the relevant **layout function** (see
   below) decides cell width, font, cards-per-row, row-gap, etc.,
   based on **that section's problems only**.
4. **Each operation gets its own page break.** The first non-empty
   section uses page 1 (which carries the header); every later section
   begins a new page.
5. The section is paginated row-by-row using its own `card_h` and
   `row_gap_mm` so the actual visual gap and the paginator's
   bookkeeping stay in sync.
6. Each page is emitted as a `<div class='page'>` with **inline CSS
   custom properties** (`--cell-w`, `--cell-h`, `--font-size`,
   `--carry-h`, `--grid-cols`, `--row-gap`, `--col-gap`, `--div-font`)
   declared in `style="..."`. The shared `<style>` block reads those
   variables via `var(...)`. That's how one stylesheet handles multiple
   per-section layouts without per-section CSS.

### Per-operation modules

Every operation owns:

- a `compute_layout(problems) -> dict` that decides cell size,
  cards-per-row, row/column gaps, and a realistic `card_h` for the
  paginator,
- a `render_card(problem, number, layout) -> str` that produces the
  card HTML,
- its own section-digit-cols logic when the operator has special needs
  (multiplication reserves room for the partial-product staircase).

The dispatcher in `html_preview._render_card` picks the right module by
operator. Addition and subtraction share the inline functions in
`html_preview.py` because their card shape is identical (and there's
no need to import a third module just for that).

This split is *the* big architectural decision in the project. Tweaking
multiplication never has to touch addition's code, and vice versa.

---

## Card layouts

### `+`, `−`, and `×` with a 1-digit multiplier

```
1.                        <- problem number paragraph (~5.7mm)
 ┌──┬──┬──┐               <- thin dashed carry row (~5mm)
 │  │  │  │
 ├──┼──┼──┤
 │     6  3│               <- operand 1 row, digits right-aligned, no borders
 │+    2  1│               <- operand 2 row + operator; bottom border = horizontal rule
 ├──┼──┼──┤
 │  │  │  │               <- answer row, full solid borders
 └──┴──┴──┘
```

### `×` with a 2+-digit multiplier

```
1.                        <- problem number paragraph
 │     6  1  6│            <- operand 1
 │×    4  3  5│            <- operand 2 + operator; bottom border = rule
 ┊┊╶┄┄┄┄┄┄┄┄┄┄┊            <- partial row, units multiplier (k=0)
 │     □  □  □  □│         <- solid boxes where the digits land
 ┊  ╶┄┄┄┄┄┄┄┄┄┄┊            <- partial row, tens multiplier (k=1), shifted 1 left
 │  □  □  □  □  ┊
 ┊╶┄┄┄┄┄┄┄┄┄┄┄┄┊            <- partial row, hundreds multiplier (k=2), shifted 2 left; bottom border = rule
 │□  □  □  □  ┊  ┊
 │ □  □  □  □  □  □│       <- final answer row, full width
```

Key invariants:

- **Partial rows are uniform-width within a problem.** The width is
  `max_partial_width(p)` — the widest single-digit-times-operand1
  partial. Inactive cells in a partial row use a **dashed light-grey**
  border so every column still shows a box (the user explicitly asked
  for this — without it the layout reads as having "missing" boxes).
- **No carry row** for multi-digit multiplication. Carries are typically
  written above the operand inline, not in a separate row.
- `digit_cols` for the section is `max(operand_widths, answer_width,
  max_partial_width + (op2_digits - 1))`. The last term reserves enough
  columns so the leftmost (most-shifted) partial never overflows into
  the operator column.

### `÷`

Currently a simple horizontal `a ÷ b = ⬜` card with an answer box
sized to the quotient. `render_div.py` is the natural place to grow
this into long-division (the bracket) or remainder cards.

---

## Per-section concrete layout numbers

Useful when eyeballing a worksheet to see if it looks right.

| Section | per-row | cell mm | row mm | font pt | row-gap | col-gap | `card_h` (mm) |
|---------|--------:|--------:|-------:|--------:|--------:|--------:|--------------:|
| Addition / Subtraction        | 3 | 9 | 10 | 18 | 22 | 12 | 41 |
| Multiplication (1-digit ×)    | 3 | 9 | 10 | 18 | 14 | 10 | 41 |
| Multiplication (2-digit ×₂)   | 2 | 11 | 12.22 | 22 | 14 | 10 | 67 |
| Multiplication (3-digit ×₃)   | 2 | 11 | 12.22 | 22 | 14 | 10 | 79 |
| Division                      | 3 | 9 | 10 | 16 | 12 | 10 | 28 |

For multi-digit × the rule is `card_h = round(row_mm × (op2_digits + 3) + 6)`,
where the `+ 6` is the ~5.7 mm problem-number paragraph plus a small
safety margin. The earlier `+ 10` over-budgeted by ~4 mm and forced
3-digit × 2-digit worksheets to put 4 cards on page 1 / 2 on page 2 —
now they fit 6 per page on page 1.

Note: addition's `row_gap_mm = 22` is the **maximum possible** with
the carry row kept and 12 problems per page. Bumping cells to 10mm
shrinks the gap to 17mm; dropping the carry row would free another
~5mm of gap. Cell-vs-gap is the trade-off lever for this section.

Each section sets these via inline CSS variables on its `.page` element.
The `compute_layout` in the relevant module recomputes them every
render — they're not constants — so if `digit_cols` is unusually wide,
cells shrink to fit. The numbers above are what you see in a typical
worksheet (3-digit operands or smaller).

---

## Layout math (memorize these numbers)

A4 portrait, 15 mm margins → **180 mm × 267 mm content area.**

Header on page 1: `H_HEADER_BLOCK = 24 mm` (Name/Date/Score line +
title). Section heading: `H_SECTION_HEADING = 11 mm`.

### Addition card height — measured the way the browser renders it

With the current 9 mm cells / 18 pt digits:

```
problem-number paragraph (11pt × 1.2 line-height + 3pt margin) ~ 5.7 mm
carry row (carry_mm = cell_mm × 0.55)                          ~ 5 mm
operand1 + operand2 + answer (3 × row_mm = 3 × 10mm)            30 mm
                                                                ─────
total content                                                  ~40.7 mm
```

We round to **41 mm** for `card_h`. The historical `card_h = 57` formula
had a phantom `+22` mm padding that the browser never actually
rendered, which is why the user kept seeing "no breathing space" —
pagination thought the rows were already at the page limit and refused
to leave any gap.

### Pagination budget for "12 problems per page"

12 cards = 4 rows × 3 columns. Constraint on page 1 (with header):

```
4 × card_h + 3 × row_gap + 35 (header + section heading)  ≤  267
```

With `card_h = 41`: `3 × row_gap ≤ 52`, so the **max row-gap is 17 mm**
at 10 mm cells. That's where addition sits now (266 mm used, 1 mm
spare). On non-header pages: `4 × 45 + 3 × 17 = 231 ≤ 267`, with
36 mm of bottom margin to spare.

If the user wants *bigger* gaps than 17 mm we either drop to 9 per
page or shrink the cells (back to 9 mm at 18 pt yields a max gap of
~22 mm — the previous configuration).

*Currently the project is on the 9mm-cell, 22mm-gap variant — the
user explicitly chose that bigger-gap configuration after seeing the
10mm-cell one.*


### Multiplication

- 1-digit multiplier → uses the addition shape, same numbers.
- Multi-digit multiplier → cells go to 11 mm (22 pt font) at
  **2 cards per row** so the staircase is easy to scan. `digit_cols`
  for the section accounts for the partial staircase width as
  described above.

`render_mul.compute_layout` computes `card_h = row_mm × (op2_digits + 3)
+ 6` for multi-digit problems (op1, op2, N partials, final answer).
Row-gap is 14 mm; column-gap is 10 mm. The constant tail mirrors
addition's `+ 6`: the problem-number paragraph is ~5.7 mm and the
remaining ~0.3 mm is safety. We tried `+ 10` first and pagination cut
6-problem 3-digit × 2-digit pages in half.

### Division

Simple horizontal cards, 3 per row, row-gap 12 mm, column-gap 10 mm.

---

## Generator (`app/generator.py`)

### Inputs

A `GenerationRequest` carries an `OperationConfig` for each operator:

```python
OperationConfig(
    enabled=True,
    count=N,                # 0..200
    min1, max1, min2, max2, # 0..9999
    no_zero_digits=False,       # exclude operands containing '0'
    no_repeated_digits=False,   # exclude operands with any digit repeat
)
```

Plus `title`, `include_answer_key`, and `seed` (optional — for
reproducible problem sets in tests).

The two `no_*_digits` flags live on every `OperationConfig` for schema
uniformity, but only `_gen_multiplication` honours them today (the UI
exposes them on the multiplication card only). When either flag is on,
the generator builds the pool of valid values up front via
`valid_values(lo, hi, no_zero, no_repeated)` and picks operands from
the pool — rejection sampling would also work but precomputing keeps it
fast when constraints make values sparse (e.g. 101–999 with both flags
on leaves 504 of the 899 integers).

### Per-operator generation rules

- **Addition** — straight `random.randint` on the two ranges. No special
  cases.
- **Subtraction** — generates `(a, b)` and **swaps** if `b > a` so the
  answer is always non-negative. Grade 2–3 isn't ready for negatives.
- **Multiplication** — straight random by default. Honours
  `no_zero_digits` (operands containing `0` are excluded, e.g. 300 and
  301 are out, 317 is fine) and `no_repeated_digits` (operands with
  any digit repeat are excluded, e.g. 311 is out, 317 is fine). Both
  can be combined; the HTTP layer rejects requests where the chosen
  range and constraints leave no valid values. Multi-digit cases fall
  out naturally when the teacher widens `max2`.
- **Division** — generates **exact** division (no remainder). Strategy:
  pick divisor `b ∈ [min2, max2]` (clamping `min2 ≥ 1`), then a quotient
  `q` such that `a = b × q` lies in `[min1, max1]`. If the divisor range
  makes any exact problem impossible, retry up to 30 times before
  falling back. The endpoint in `main.py` also runs a **feasibility
  check** up front and returns a clear 400 if no exact division can fit
  the requested ranges.

### Difficulty heuristic

`Problem.difficulty` is `digits(op1) + digits(op2)` plus a +1 bonus if
the column-wise computation would require **regrouping** (carry for
addition, borrow for subtraction). Multiplication / division add a
half-point per digit of the answer. The full problem list is sorted
ascending by difficulty inside `_group()` so each section runs
easiest-first.

### `max_digits()` and `max_partial_width()`

`max_digits(problems)` returns the digit-column count any layout needs
in order to fit operands, answers, **and** (for multi-digit ×) the
shifted partial-product staircase. Always use it when computing
`digit_cols` for a section; don't roll your own.

`max_partial_width(p)` is the uniform width every partial-product row
in a multi-digit multiplication card should be drawn at.

---

## HTTP API (`app/main.py`)

Three endpoints. Validation and rendering responsibilities are split:

- `GET /` → serves `static/index.html`.
- `POST /api/preview` → returns the rendered worksheet HTML for the
  iframe. Used by the **Preview worksheet** button.
- `POST /api/generate` → returns the same HTML with a
  `Content-Disposition: attachment; filename="{title}_{stamp}.html"`
  header so the browser downloads it. Used by the **Download HTML**
  button.

### Validation pipeline

Two layers of validation:

1. **Pydantic** (`OperationPayload`, `GeneratePayload`). Field-level
   bounds (`ge=0, le=9999`, etc.) and a `model_validator` on
   `OperationPayload` that enforces `max1 ≥ min1` and `max2 ≥ min2`
   *only when the operation is enabled with count > 0*. That last
   condition matters — we don't want a disabled section's stale defaults
   to block submission.
2. **`_validate_business_rules(payload)`** runs inside both endpoints
   for things that aren't expressible as field-level validators:
   - At least one operation must be enabled with a count > 0.
   - Multiplication: when `no_zero_digits` or `no_repeated_digits` is
     on, scan `valid_values(min1, max1, …)` and `valid_values(min2,
     max2, …)`; if either pool is empty, return a 400 naming which
     operand range is unsatisfiable so the user knows what to widen.
   - Division: `min2 ≥ 1`, and a feasibility scan to make sure some
     exact division actually exists in the given ranges. Otherwise we
     return a helpful 400 telling the user to widen the dividend or
     divisor range, instead of letting the generator silently fall back.

### Error wire format

Pydantic validation failures arrive at the frontend as a 422 with a
**list** of `{type, loc, msg, input, ctx}` objects under `detail`.
Business-rules failures are 400 with `detail` as a plain string. The
frontend's `formatErrors()` (in `static/index.html`) handles both —
trimming the `"Value error, "` prefix Pydantic prepends and joining `loc`
into a human label like `Addition: first number's max must be ≥ its
min`. If you change the validator's `msg` strings, the frontend doesn't
need updating; it just shows whatever text comes back.

---

## Frontend (`static/index.html`)

Single page, vanilla JS, no build step.

### Form structure

- The operation cards are **generated from a JS `OPS` array**, not
  hand-written. Each entry has `id, label, defaultEnabled, defaults
  (count/min1/max1/min2/max2), optional labels override (Dividend /
  Divisor for ÷), optional legend text, optional extras (array of
  per-op checkbox flags)`. To add an operation in the UI, add an entry
  to `OPS` — that's it.
- Per-operation **extras** are extra checkboxes rendered under the
  number-range rows, separated by a dashed line. Each extra has `id`
  (must match a payload field on `OperationPayload`), `label`, and
  optional `hint`. Multiplication uses this to expose `no_zero_digits`
  and `no_repeated_digits`. `readOp` includes every extra's value in
  the JSON payload, and disabling the op-card disables its extras too.
- Each operation card has a checkbox at the top. When unchecked, the
  card collapses (`.body` hidden via `[data-enabled="false"] .body
  {display:none}`) and its number inputs are disabled. The form is
  short and scannable.
- Number ranges are laid out as **two rows per operation** — "First
  number: min ___ max ___" and "Second number: min ___ max ___" —
  rather than a wide single row of five inputs. Easier to scan, easier
  on narrow screens.

### Preview / Print / Download flow

1. **Preview worksheet** calls `/api/preview`, drops the returned HTML
   into the iframe via `srcdoc`, switches the placeholder out, and
   enables the Print and Download buttons.
2. **Print / Save as PDF** calls `frame.contentWindow.print()`. The
   browser's print dialog handles paper size, the user picks
   "Save as PDF" there if they want a file.
3. **Download HTML** calls `/api/generate` (same payload as preview)
   and triggers a blob download with the server-supplied filename.

A `form input` listener disables both action buttons whenever any field
changes after a successful preview, with the status message "Settings
changed — click Preview to refresh." This prevents downloading a stale
worksheet.

### Status line

Three states styled differently: neutral (`.status`), `.status.error`
(red), `.status.success` (green). Errors that come back as a list (from
`formatErrors`) are rendered as a `<ul>` with one item per loc.

---

## Pinned user preferences (= requirements)

These were established during back-and-forth with the user and should
NOT be relitigated:

- **12 problems per page on addition / subtraction.** Not 9, not 15.
  The current `card_h = 41` and `row_gap = 22` are tuned exactly so 12
  fit on page 1 (with the header) and on every subsequent page.
- **Each operation gets its own page break.** Addition ends → flush →
  Subtraction starts on a new page, even if the previous page had
  room. The user wants this for navigation.
- **Multi-digit multiplication uses uniform-width partial rows.** The
  earlier per-partial-width version produced a visible zigzag in the
  staircase. Uniform width = clean staircase, only the *shift* changes
  per row.
- **Every cell in a partial-product row must have a visible border.**
  Inactive cells use a *light dashed* border (the active cells stay
  solid). The user explicitly reported "missing boxes" when inactive
  cells had no border — they want a complete grid.
- **No editable .docx output.** The user confirmed they don't need
  Word output; the print → save-as-PDF flow is enough.
- **Browser-printed HTML, not server-side PDF.** No native deps.
- **Per-operation independent layout.** Multiplication's needs (bigger
  cells, 2 per row, partial staircase) don't get to dictate addition's
  cell size or row count.
- **Multiplication digit-shape filters are opt-in.** `no_zero_digits`
  and `no_repeated_digits` default off so the existing defaults
  (2–12 × 2–12) behave exactly as before. When the teacher enables
  them, the generator filters operands but does not retry to hit the
  count if the pool runs out — the HTTP layer's feasibility check is
  the safety net.
- **6 multi-digit × cards per page is the target density** at the
  user's reference shape (101–999 × 11–99). Row-gap 14 mm and cell
  size 11 mm / 22 pt are tuned so this fits on page 1 with the header.
  Don't bump `card_h` back up without re-running that case.

---

## Pagination

`_paginate_section` does the work, per operation:

- Each row-after-the-first on a page costs `card_h + row_gap_mm`. The
  paginator's budget and the CSS grid's actual `row-gap` are in sync;
  that's a property to preserve.
- A section heading consumes `H_SECTION_HEADING` once, on the first
  page of that section.
- If the next row + heading + gap would overflow, flush the page and
  start fresh.
- Rows within a section never get split. `_paginate_section` ensures
  this because it only ever flushes between rows.

---

## CSS variables in use

Set on each `<div class='page'>` via inline `style="..."`:

| Variable      | Purpose                                            |
|---------------|----------------------------------------------------|
| `--cell-w`    | Width of a digit cell (mm)                         |
| `--cell-h`    | Height of an operand/answer row (mm)               |
| `--font-size` | Digit font size (pt)                               |
| `--carry-h`   | Height of the thin carry row (mm)                  |
| `--div-font`  | Font size for the horizontal division card (pt)    |
| `--grid-cols` | Value for grid-template-columns (`1fr 1fr 1fr`…)   |
| `--row-gap`   | Vertical gap between rows of cards (mm)            |
| `--col-gap`   | Horizontal gap between cards within a row (mm)     |

Default fallbacks are encoded in the CSS via `var(--row-gap, 6mm)` etc.,
in case a page somehow forgets to set one.

---

## Pitfalls already encountered (do not repeat)

1. **Don't budget `card_h` larger than what the browser renders.** This
   bit us twice. If `card_h` is inflated, pagination cuts pages early
   and the user sees rows visibly touching with empty space at the
   bottom of the page. Always measure the way the browser will render:
   `num-paragraph + table rows`. A 1–2 mm safety margin is fine; +22
   is too much.
2. **Don't share `digit_cols` across operations.** Earlier the
   worksheet used a single `digit_cols` computed across all sections,
   which meant a 3-digit × 3-digit multiplication forced 6-column
   addition cards. Each section now decides its own.
3. **Don't force uniform partial-product widths without enlarging
   `digit_cols` first.** Uniform widths give a clean staircase, but
   the leftmost partial sits at shift `op2_digits − 1` and will
   overflow the operator column if `digit_cols` wasn't reserved for
   it. `max_digits` includes `max_partial_width + op2_digits - 1` for
   this reason.
4. **Don't bake `column-gap` or `row-gap` into the static CSS.** They
   need to be per-section. Use the inline CSS variables.
5. **Don't rely on LibreOffice to preview the HTML.** LibreOffice's
   `writer_web_pdf_Export` doesn't render CSS Grid. To verify visuals,
   open the HTML in a real browser (or use the `mcp__visualize__show_widget`
   tool to render it inline). And when using `show_widget`, mirror the
   *actual* DOM structure the app emits — not a simplified one. We
   debugged a "no breathing space" issue for several rounds because
   the widget tests put all cards inside one `<div class='grid'>`
   while the real app wrapped *each row of 3 cards* in its own grid,
   making CSS `row-gap` ineffective. Always reproduce the real layout.
6. **Don't render in Word/docx.** That path is abandoned and shouldn't
   come back without an extremely good reason. Word's table rendering
   is hostile to the staircase and per-cell border control we need.
7. **`uv sync` may try to download Python 3.12+ on first run.** That's
   fine on a fresh machine — set `UV_PYTHON_DOWNLOADS=never` and
   `UV_PYTHON=/usr/bin/python3.10` only if there's no Internet.
8. **In Cowork sessions, file tools and the Linux sandbox can see
   different snapshots of this repo.** The Read/Write/Edit tools talk
   to the real Windows filesystem; the bash sandbox mounts a copy
   that doesn't always reflect file-tool writes (and on at least one
   session showed a truncated `app/generator.py` to bash while the
   file tools saw the complete file). To run / test changes in bash,
   write a working copy into the outputs folder via the file tools
   (`Write` to a path under `…/outputs/`) and `python3 -c …` against
   that. To commit, run `git status` from bash first to confirm it
   sees your edits; if it doesn't, refresh by writing the files back
   into the repo via the file tools and re-checking.
9. **The Windows checkout uses CRLF; HEAD is LF.** Without `git
   config core.autocrlf input`, every file looks fully modified in
   `git diff`. Run that config once per fresh clone (or once per
   sandbox) before committing so the diff shows only real changes.

---

## Workflow

### Develop

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. Edits to Python autoreload; edits to
`static/index.html` are picked up on the next `/api/preview` call.

On Windows, double-clicking `run.cmd` does the same thing plus spawns
a minimized 2-second-delay helper that opens the URL in the default
browser once uvicorn has had time to bind. Delete that
`start "" /min cmd /c "timeout /t 2 …"` line if you ever want to run
headless.

### When changing layout

- For per-card visuals (borders, fonts, row order inside a card):
  edit the relevant `render_*.render_card` function.
- For sizing/spacing (cells, font, gaps, density): edit the relevant
  `compute_layout` function.
- For pagination behaviour: edit `html_preview._paginate_section`.

### When the user reports a visual bug

Render the exact problematic case using `mcp__visualize__show_widget`
with the actual generated HTML. **Don't** just verify via Python-level
output — the *Python* renderer might be correct while the *browser* is
doing something I didn't expect (or vice versa). Lesson learned: I
assumed 16mm row-gap was applied because the HTML said so, when the
user kept reporting "no breathing space". The lesson was: when in doubt
about visuals, look at pixels.

### Adding a new operation

1. Drop a `render_<op>.py` module with `compute_layout`,
   `render_card`, and (if needed) `section_digit_cols`.
2. Register the operator in `html_preview.LAYOUTS` and
   `html_preview._render_card`.
3. Add an entry to `GROUPING_ORDER` and `SECTION_TITLES`.
4. If the new operation needs its own CSS classes, add them to the
   static `CSS` block in `html_preview.py` (which is already
   parameterized via `var(--…)`).
5. Update `generator.py` to produce problems for the new operator
   and add a generator config in `OperationConfig` if needed.

### Committing

Run `git add -A && git commit -m "..."` with a clear subject + body.
Earlier commits in this repo are good examples — concrete subject,
prose body explaining the *why*, sometimes a table when it helps. We
commit after every meaningful step rather than batching.

---

## What's NOT in scope yet (open items)

These came up in discussion but weren't implemented:

- **Inline per-field error messages.** Pydantic returns errors with a
  `loc` like `["body", "addition", "max1"]`; the frontend already
  parses them into readable strings, but it shows them in a global
  status line. Showing them next to the offending input would be a
  ~30-line JS change plus a bit of CSS.
- **Font/cell-size knob in the UI.** Currently each section's sizing
  is computed automatically. A teacher might want a Grade 2 / Grade 3
  preset, or a custom size override.
- **Long-division layout for `÷`.** Currently horizontal `a ÷ b = ⬜`.
  `render_div.py` is set up to grow into the bracket layout when we
  decide that's worth doing.
- **Remainder support for `÷`.** Generator currently produces exact
  divisions only.
- **Digit-shape constraints for addition / subtraction / division.**
  The `no_zero_digits` / `no_repeated_digits` flags live on every
  `OperationConfig` already but only `_gen_multiplication` honours
  them. If a teacher asks for the same on +/−/÷, wire it into those
  generators and add the checkboxes to those ops' `extras` in `OPS`.

---

## Quick reference: where things live

| Concern                                | File                            |
|----------------------------------------|---------------------------------|
| Adding a new operator                  | `app/render_<op>.py` + register in `app/html_preview.py` |
| Tuning addition / subtraction layout   | `app/html_preview.py::_layout_addition` |
| Tuning multiplication                  | `app/render_mul.py` |
| Tuning division                        | `app/render_div.py` |
| Page geometry constants                | `app/render_common.py` |
| Page-level CSS                         | `app/html_preview.py::CSS` |
| Form / preview UX                      | `static/index.html` |
| HTTP endpoints                         | `app/main.py` |
| Problem generation + difficulty        | `app/generator.py` |
| Windows launchers                      | `sync.cmd`, `run.cmd` |
| Cross-platform install + run docs      | `README.md` |

---

*Last updated 2026-05-19 — multiplication digit-shape filters
(`no_zero_digits` / `no_repeated_digits`), multi-digit × card_h budget
tightened from `+10` to `+6` (so 3-digit × 2-digit fits 6 per page),
`run.cmd` now auto-launches the browser.*
