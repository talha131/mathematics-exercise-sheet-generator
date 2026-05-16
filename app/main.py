"""
FastAPI backend for the math exercise sheet generator.

Endpoints:
    GET  /                   → serves the single-page form (static/index.html)
    POST /api/preview        → returns an HTML preview of the worksheet
    POST /api/generate       → returns a downloadable, print-ready PDF
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from .generator import GenerationRequest, OperationConfig
from .html_preview import render_preview
from .pdf_builder import build_pdf

app = FastAPI(title="Math Exercise Sheet Generator")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

OP_LABELS = {
    "addition": "Addition",
    "subtraction": "Subtraction",
    "multiplication": "Multiplication",
    "division": "Division",
}


class OperationPayload(BaseModel):
    enabled: bool = False
    count: int = Field(default=0, ge=0, le=200)
    min1: int = Field(default=0, ge=0, le=9999)
    max1: int = Field(default=9, ge=0, le=9999)
    min2: int = Field(default=0, ge=0, le=9999)
    max2: int = Field(default=9, ge=0, le=9999)

    @model_validator(mode="after")
    def _check_ranges(self):
        # only enforce min ≤ max when the operation is actually used —
        # this keeps "disabled" cards from blocking form submission
        if self.enabled and self.count > 0:
            if self.max1 < self.min1:
                raise ValueError(
                    "first number's max must be greater than or equal to its min"
                )
            if self.max2 < self.min2:
                raise ValueError(
                    "second number's max must be greater than or equal to its min"
                )
        return self


class GeneratePayload(BaseModel):
    title: str = Field(default="Math Practice", max_length=80)
    include_answer_key: bool = True
    seed: int | None = None
    addition: OperationPayload = OperationPayload()
    subtraction: OperationPayload = OperationPayload()
    multiplication: OperationPayload = OperationPayload()
    division: OperationPayload = OperationPayload()


def _validate_business_rules(p: GeneratePayload) -> None:
    """Catch errors that need a friendly, contextual message."""
    any_enabled = any(
        op.enabled and op.count > 0
        for op in (p.addition, p.subtraction, p.multiplication, p.division)
    )
    if not any_enabled:
        raise HTTPException(
            status_code=400,
            detail="Enable at least one operation and set a count greater than 0.",
        )
    if p.division.enabled and p.division.count > 0:
        d = p.division
        if d.min2 < 1:
            raise HTTPException(
                status_code=400,
                detail="Division: divisor minimum must be at least 1 "
                       "(can't divide by zero).",
            )
        # quick feasibility check — make sure SOME exact division exists in range
        feasible = False
        for b in range(d.min2, d.max2 + 1):
            if b == 0:
                continue
            q_lo = -(-d.min1 // b)
            q_hi = d.max1 // b
            if q_hi >= max(0, q_lo):
                feasible = True
                break
        if not feasible:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Division: no exact (no-remainder) problems fit those ranges. "
                    "Try widening the dividend or divisor range."
                ),
            )


def _to_request(p: GeneratePayload) -> GenerationRequest:
    def cfg(o: OperationPayload) -> OperationConfig:
        return OperationConfig(
            enabled=o.enabled,
            count=o.count,
            min1=o.min1, max1=o.max1,
            min2=o.min2, max2=o.max2,
        )
    return GenerationRequest(
        addition=cfg(p.addition),
        subtraction=cfg(p.subtraction),
        multiplication=cfg(p.multiplication),
        division=cfg(p.division),
        title=p.title,
        include_answer_key=p.include_answer_key,
        seed=p.seed,
    )


def _safe_filename(title: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_") or "worksheet"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{base}_{stamp}.pdf"


@app.post("/api/preview", response_class=HTMLResponse)
def preview(payload: GeneratePayload) -> HTMLResponse:
    _validate_business_rules(payload)
    html = render_preview(_to_request(payload))
    return HTMLResponse(content=html)


@app.post("/api/generate")
def generate(payload: GeneratePayload) -> Response:
    _validate_business_rules(payload)
    try:
        data = build_pdf(_to_request(payload))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    filename = _safe_filename(payload.title)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# serve any future static assets (e.g. CSS, JS files) from /static/
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
