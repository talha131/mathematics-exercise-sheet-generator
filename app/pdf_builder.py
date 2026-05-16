"""
PDF generation using WeasyPrint.

Renders the same HTML used for the in-browser preview straight to a PDF so
the printed file matches the preview exactly — single source of truth for
layout. WeasyPrint applies the @page and @media print rules in the preview's
CSS to produce a paginated A4 document.
"""

from __future__ import annotations

from io import BytesIO

from weasyprint import HTML

from .generator import GenerationRequest
from .html_preview import render_preview


def build_pdf(req: GenerationRequest) -> bytes:
    html = render_preview(req)
    buf = BytesIO()
    HTML(string=html).write_pdf(target=buf)
    return buf.getvalue()
