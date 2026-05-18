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

## Layout math (memorize these numbers)

A4 portrait, 15 mm margins → **180 mm × 267 mm content area.**

Header on page 1: `H_HEADER_BLOCK = 24 mm` (Name/Date/Score line +
title). Section heading: `H_SECTION_HEADING = 11 mm`.

### Addition card height — measured the way the browser renders it

```
problem-number paragraph (11pt × 1.2 line-height + 3pt margin) ~ 5.7 mm
carry row                                                       ~ 5   mm
operand1 + operand2 + answer (3 × 10mm)                           30   mm
                                                                ─────
                                                                 40.7 mm
```

We round to **41 mm** for `card_h`. The historical `card_h = 57`
formula had a phantom `+22` mm padding that the browser never actually
rendered, which is why the user kept seeing "no breathing space" —
pagination thought the rows were already at the page limit and refused
to leave any gap.

### Pagination budget for "12 problems per page"

12 cards = 4 rows × 3 columns. Constraint on page 1 (with header):

```
4 × card_h + 3 × row_gap + 35 (header + section heading)  ≤  267
```

With `card_h = 41`: `3 × row_gap ≤ 68`, so the **max row-gap is 22 mm**.
That's where addition sits now.

On non-header pages: `4 × 41 + 3 × 22 = 230 ≤ 267`, with 37 mm of
bottom margin to spare.

If the user later asks for *bigger* gaps than 22 mm we either drop to
9 per page or shrink the cards.

### Multiplication

- 1-digit multiplier → uses the addition shape, same numbers.
- Multi-digit multiplier → cells go to 11 mm (22 pt font) at
  **2 cards per row** so the staircase is easy to scan. `digit_cols`
  for the section accounts for the partial staircase width as
  described above.

`render_mul.compute_layout` computes `card_h = row_mm × (op2_digits + 3)
+ 10` for multi-digit problems (op1, op2, N partials, final answer).
Row-gap is 14 mm; column-gap is 10 mm.

### Division

Simple horizontal cards, 3 per row, row-gap 12 mm, column-gap 10 mm.

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
   tool to render it inline).
6. **Don't render in Word/docx.** That path is abandoned and shouldn't
   come back without an extremely good reason. Word's table rendering
   is hostile to the staircase and per-cell border control we need.
7. **`uv sync` may try to download Python 3.12+ on first run.** That's
   fine on a fresh machine — set `UV_PYTHON_DOWNLOADS=never` and
   `UV_PYTHON=/usr/bin/python3.10` only if there's no Internet.

---

## Workflow

### Develop

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. Edits to Python autoreload; edits to
`static/index.html` are picked up on the next `/api/preview` call.

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
- **Auto-open browser** when `run.cmd` starts. Intentionally left to
  the user; trivially added (`start http://127.0.0.1:8000`) if you
  want it.

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

*Last updated to reflect the layout pass on 2026-05-17.*
