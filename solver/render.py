"""Render a five-segment Markdown answer for a VE401 question.

This is the orchestration layer for Phase E:

1. classify the question via :mod:`classifier.triage` (Phase C);
2. extract numerical givens via :mod:`solver.extract_givens`;
3. look up the matching test card's template in :mod:`solver.templates`;
4. fill placeholders, evaluate the test statistic when ``compute`` is
   available, and emit a Markdown blob with the canonical five
   sections (Setup / Hypotheses / Statistic / Computation / Decision)
   plus slide refs and a brief retrieval pointer.

Plan §6 step E3 (and the MVP DoD §12.1 #2: "answer skeleton consistency
≥ 12/14") is the calibration target — every output must contain the five
section headers, the test card's name, and the slide ref(s) cited by the
taxonomy. The Computation section may degrade gracefully to a symbolic
formula when not all numerical givens were supplied.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from classifier.decision_tree import classify, ClassifyHit, card_meta
from solver.extract_givens import extract_givens, normalise_text, Givens
from solver.templates import TEMPLATES, get_template


# --------------------------------------------------------------------------- #
# Output dataclass                                                             #
# --------------------------------------------------------------------------- #


@dataclass
class SolveResult:
    """Bundle returned by :func:`solve` so callers can inspect the
    intermediate stages (classifier hits, givens, retrieval refs) instead
    of being forced through the rendered string only."""

    card_id: str
    card_title: str
    classify_hits: List[ClassifyHit] = field(default_factory=list)
    givens: Optional[Givens] = None
    markdown: str = ""
    statistic_value: Optional[float] = None
    related_record_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "card_id": self.card_id,
            "card_title": self.card_title,
            "classify_hits": [
                {"card_id": h.card_id, "score": h.score, "title": h.title}
                for h in self.classify_hits
            ],
            "givens": self.givens.to_dict() if self.givens else None,
            "statistic_value": self.statistic_value,
            "related_record_ids": list(self.related_record_ids),
            "markdown": self.markdown,
        }


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


_FALLBACK_TEMPLATE = {
    "name": "Generic VE401 hypothesis test",
    "slide_refs": [],
    "chapter": "?",
    "setup": (
        "Identify the test family (one-sample, two-sample, paired, "
        "non-parametric, regression, ANOVA, ...) and the relevant slide."
    ),
    "hypotheses_fmt": "H_0: <state>  vs.  H_1: <state>  ({tail}).",
    "statistic": "Statistic and its null distribution per the relevant slide.",
    "computation_fmt": "Plug in the numerical givens once they are read off.",
    "decision_fmt": "Reject H_0 if the statistic falls in the rejection region at level {alpha}.",
    "compute": None,
    "stat_symbol": "?",
    "stat_kind": "generic",
}


def _alt_op(tail: str, *, kind: str = "neq") -> str:
    """Return the H_1 operator string matching the inferred tail.

    For a "two-sided" tail we emit ``≠`` (or ``!=`` if the question text
    used plain ASCII). One-sided tails get ``>`` / ``<``. The user can
    always override after reading.
    """
    if tail == "two-sided":
        return "!="
    if tail in ("right-tailed",):
        return ">"
    if tail in ("left-tailed",):
        return "<"
    if tail == "one-sided":
        return ">"
    return "!="


def _fmt(v, fmt: str = "{:g}") -> str:
    if v is None:
        return "?"
    try:
        return fmt.format(v)
    except (TypeError, ValueError):
        return str(v)


def _safe_format(template: str, mapping: dict) -> str:
    """Format using a defaultdict-style fallback so missing keys come out
    as the literal token ``{key}`` removed in favour of ``?``."""

    class _D(dict):
        def __missing__(self, key):
            return "?"

    try:
        return template.format_map(_D(mapping))
    except (IndexError, KeyError, ValueError):
        return template


# --------------------------------------------------------------------------- #
# Render                                                                       #
# --------------------------------------------------------------------------- #


def _build_mapping(g: Givens, template: dict, statistic_value: Optional[float]) -> dict:
    """Construct the substitution dictionary used by ``str.format_map``.

    Beyond the raw givens we synthesise a few derived/display fields that
    the per-card templates reference:

    - ``alt_op``: the H_1 operator string driven by inferred tail
    - ``tail``: the tail label
    - ``alpha``: defaults to 0.05 if not extracted
    - ``df``:    n - 1 when n is given
    - ``z_val``/``t_val``/``chi2_val``: numerical statistic if computed
    - ``s_squared_disp`` / ``sigma_0_squared_disp``: friendly display
    - ``observed_disp`` / ``n_obs``: GoF helpers
    - ``reject_rule``: a VE401-style rejection-region string
    """
    raw = dict(g.raw)
    tail = g.tail or "two-sided"
    if "alpha" not in raw:
        raw["alpha"] = 0.05  # VE401 default

    derived = {"alt_op": _alt_op(tail), "tail": tail}
    if "n" in raw:
        derived["df"] = int(raw["n"]) - 1

    # Statistic-value renders
    sv = _fmt(statistic_value, "{:.4g}") if statistic_value is not None else "(insufficient givens)"
    derived["z_val"] = sv
    derived["t_val"] = sv
    derived["chi2_val"] = sv

    # Variance display: prefer the variance form (s^2, sigma_0^2) over the
    # raw sigma so the formula reads the way the slide writes it.
    s_sq = raw.get("s_squared")
    if s_sq is None and raw.get("s") is not None:
        s_sq = raw["s"] ** 2
    derived["s_squared_disp"] = _fmt(s_sq) if s_sq is not None else "?"

    sig0_sq = raw.get("sigma_0_squared")
    if sig0_sq is None and raw.get("sigma_0") is not None:
        sig0_sq = raw["sigma_0"] ** 2
    if sig0_sq is None and raw.get("sigma_squared") is not None:
        sig0_sq = raw["sigma_squared"]
    if sig0_sq is None and raw.get("sigma") is not None:
        sig0_sq = raw["sigma"] ** 2
    derived["sigma_0_squared_disp"] = _fmt(sig0_sq) if sig0_sq is not None else "?"

    # ρ_0 display for correlation cards
    rho0 = raw.get("rho_0", 0)
    derived["rho_0_disp"] = _fmt(rho0)

    # GoF helpers
    counts = list(g.observed_counts or [])
    if counts:
        derived["observed_disp"] = ", ".join(str(c) for c in counts)
        derived["n_obs"] = sum(counts)
    else:
        derived["observed_disp"] = "?"
        derived["n_obs"] = _fmt(raw.get("n"))

    # Rejection-region phrasing
    kind = template.get("stat_kind") or "z"
    derived["reject_rule"] = _reject_rule(tail, kind)

    mapping = {**raw, **derived}
    # Format every numerical value with %g for inline display.
    formatted = {}
    for k, v in mapping.items():
        if isinstance(v, float):
            formatted[k] = _fmt(v)
        else:
            formatted[k] = v
    return formatted


def _reject_rule(tail: str, kind: str) -> str:
    """VE401-style rejection-region phrasing, parameterised by statistic."""
    a = "alpha"
    if kind == "z":
        if tail == "two-sided":
            return f"|z| > z_{{{a}/2}}"
        if tail == "right-tailed":
            return f"z > z_{{{a}}}"
        if tail == "left-tailed":
            return f"z < -z_{{{a}}}"
    if kind == "t":
        if tail == "two-sided":
            return f"|t| > t_{{{a}/2,\\,n-1}}"
        if tail == "right-tailed":
            return f"t > t_{{{a},\\,n-1}}"
        if tail == "left-tailed":
            return f"t < -t_{{{a},\\,n-1}}"
    if kind in ("chi2",):
        if tail == "two-sided":
            return (
                f"chi^2 > chi^2_{{{a}/2,\\,n-1}}  or  "
                f"chi^2 < chi^2_{{1-{a}/2,\\,n-1}}"
            )
        if tail == "right-tailed":
            return f"chi^2 > chi^2_{{{a},\\,n-1}}"
        if tail == "left-tailed":
            return f"chi^2 < chi^2_{{1-{a},\\,n-1}}"
    if kind == "chi2-gof":
        return f"chi^2 > chi^2_{{{a},\\,k-1-m}}"
    if kind == "chi2-table":
        return f"chi^2 > chi^2_{{{a},\\,(r-1)(c-1)}}"
    if kind == "F":
        if tail == "two-sided":
            return (
                f"F > F_{{{a}/2,\\,n_1-1,\\,n_2-1}}  or  "
                f"F < 1/F_{{{a}/2,\\,n_2-1,\\,n_1-1}}"
            )
        return f"F > F_{{{a},\\,df_1,\\,df_2}}"
    return "the statistic falls in the rejection region"


def render_markdown(
    card_id: str,
    givens: Givens,
    *,
    classify_hits: Optional[Sequence[ClassifyHit]] = None,
) -> Tuple[str, Optional[float]]:
    """Render the five-segment Markdown answer for a single card.

    Returns ``(markdown, statistic_value)`` where ``statistic_value`` is
    the numeric test statistic when the template's ``compute`` callable
    succeeded (i.e. all required givens were present), else ``None``.
    """
    template = get_template(card_id) or _FALLBACK_TEMPLATE
    stat_value: Optional[float] = None
    if template.get("compute"):
        try:
            stat_value = template["compute"]({"raw": givens.raw, "observed_counts": givens.observed_counts})
        except Exception:  # noqa: BLE001 — defensive: bad givens never crash the renderer
            stat_value = None

    mapping = _build_mapping(givens, template, stat_value)

    setup = template.get("setup", "")
    hypotheses = _safe_format(template.get("hypotheses_fmt", ""), mapping)
    statistic = template.get("statistic", "")
    computation = _safe_format(template.get("computation_fmt", ""), mapping)
    decision = _safe_format(template.get("decision_fmt", ""), mapping)

    name = template.get("name") or (card_meta(card_id) or {}).get("title") or card_id
    chapter = template.get("chapter") or (card_meta(card_id) or {}).get("chapter") or "?"
    slide_refs = template.get("slide_refs") or (card_meta(card_id) or {}).get("slide_refs") or []
    slide_str = (
        ", ".join(f"slide {s}" for s in slide_refs) if slide_refs else "(no slide ref)"
    )

    classify_block = ""
    if classify_hits:
        rows = ", ".join(f"{h.card_id} ({h.score})" for h in classify_hits[:3])
        classify_block = f"\n*Classifier top-3:* {rows}\n"

    md = (
        f"# {name}  *(card {card_id}, ch{chapter})*\n"
        f"*Slide refs:* {slide_str}\n"
        f"{classify_block}\n"
        f"## Setup\n{setup}\n\n"
        f"## Hypotheses\n{hypotheses}\n\n"
        f"## Statistic\n{statistic}\n\n"
        f"## Computation\n{computation}\n\n"
        f"## Decision\n{decision}\n"
    )
    return md, stat_value


def solve(
    question: str,
    *,
    top_k_cards: int = 3,
    related_records: int = 0,
) -> SolveResult:
    """Full pipeline: question → classified card → rendered Markdown.

    Parameters
    ----------
    question:
        Free-form question text. LaTeX wrappers ``\\(...\\)`` are accepted.
    top_k_cards:
        How many candidate cards to keep on :class:`SolveResult.classify_hits`.
    related_records:
        If > 0, also call :func:`retriever.retrieve` and include the top
        ``related_records`` record_ids on the result for downstream use.
        Defaults to 0 to keep the pipeline cheap and offline-friendly
        (no corpus load).
    """
    if not question or not question.strip():
        return SolveResult(
            card_id="",
            card_title="(empty question)",
            markdown="**No question supplied.**",
        )

    # The classifier's regex triggers were tuned against records that
    # contain LaTeX wrappers like ``\(\sigma=2.0\)``. A user typing the
    # same content into the CLI uses the same wrappers but Python's
    # plain-text regexes only see them as literal backslash-paren noise,
    # so we strip them once here. Using the same normaliser as the givens
    # extractor keeps the two stages aligned on identical text.
    norm_question = normalise_text(question)
    hits = classify(norm_question, top_k=top_k_cards)
    primary = hits[0].card_id if hits else ""
    primary_title = hits[0].title if hits else "(no card)"

    givens = extract_givens(question)

    if not primary:
        md = (
            "# Unclassified question\n\n"
            "The triage classifier could not match this question to any of "
            "the 25 VE401 test cards. Please rephrase or supply more context.\n"
        )
        return SolveResult(
            card_id="",
            card_title=primary_title,
            classify_hits=hits,
            givens=givens,
            markdown=md,
        )

    md, stat = render_markdown(primary, givens, classify_hits=hits)

    related: List[str] = []
    if related_records > 0:
        try:
            from retriever import retrieve  # local import to avoid corpus load when unused
            for rh in retrieve(question, top_k=related_records):
                related.append(rh.record_id)
        except Exception:  # noqa: BLE001
            pass

    return SolveResult(
        card_id=primary,
        card_title=primary_title,
        classify_hits=hits,
        givens=givens,
        markdown=md,
        statistic_value=stat,
        related_record_ids=related,
    )


__all__ = ["solve", "render_markdown", "SolveResult"]
