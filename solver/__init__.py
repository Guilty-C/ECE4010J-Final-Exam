"""Phase E — template fill + render (plan §6 step E).

The solver turns a natural-language VE401 exam question into a five-segment
Markdown answer (Setup / Hypotheses / Statistic / Computation / Decision)
that follows the course's slide conventions. It composes Phase C
(``classifier.triage``) with Phase D (``retriever.retrieve``), pulls
common numerical givens from the question text via regex, and renders the
matching test card's template.

Public API:

* :func:`solve` — one-shot pipeline: question text → rendered Markdown.
* :func:`render_markdown` — render a specific card_id from a givens dict.
* :func:`extract_givens` — regex extractor for common quantities.
"""
from __future__ import annotations

from solver.extract_givens import extract_givens, Givens
from solver.render import solve, render_markdown, SolveResult

__all__ = [
    "solve",
    "render_markdown",
    "extract_givens",
    "Givens",
    "SolveResult",
]
