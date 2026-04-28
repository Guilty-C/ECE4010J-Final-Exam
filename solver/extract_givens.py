"""Regex-based extractor for common VE401 question parameters.

Plan §6 step E1 says: "identify placeholders like ``{n}``, ``{x_bar}``,
``{sigma}``; use regex to extract numerical values from user input." This
module is exactly that — no NLP, no LLM, just a careful set of regexes
that recognise both LaTeX-style (``\\sigma = 2.0``, ``\\bar x = 24.3``)
and plain-ASCII (``sigma=2.0``, ``x-bar = 24.3``) phrasing.

We are deliberately conservative: a missed parameter surfaces as a literal
``?`` in the rendered solution rather than a confidently-wrong fabricated
number. Phase F's CLI is responsible for telling the user "I read these
values; correct any that look wrong" before computing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional


# --------------------------------------------------------------------------- #
# Pre-processing                                                               #
# --------------------------------------------------------------------------- #

# LaTeX delimiters and inline math markers we strip so that
# ``\(\sigma = 2.0\)`` is treated the same as ``sigma = 2.0``.
_LATEX_STRIP = re.compile(r"\\\(|\\\)|\\\[|\\\]|\$\$|\$")
# Backslash before a Greek letter or operator that does not change meaning
# once the LaTeX wrappers are gone.
_LATEX_BACKSLASH_TOK = re.compile(
    r"\\(sigma|mu|alpha|beta|gamma|delta|chi|rho|bar|hat|sqrt|frac|cdot|times|le|ge|leq|geq|approx|sim|neq|pm)\b"
)


def normalise_text(text: str) -> str:
    """Public alias of :func:`_normalise` so the renderer can re-use the
    same LaTeX-stripping rules before invoking the classifier. Keeping a
    single normaliser ensures givens-extraction and classifier triage
    see identical text."""
    return _normalise(text)


def _normalise(text: str) -> str:
    """Drop LaTeX wrappers so plain-string regexes can match.

    Only strips the wrapper syntax — we keep the body so ``\\bar x`` becomes
    ``bar x`` (still recognisable) and ``\\sigma`` becomes ``sigma``.
    """
    if not text:
        return ""
    s = _LATEX_STRIP.sub(" ", text)
    s = _LATEX_BACKSLASH_TOK.sub(lambda m: m.group(1), s)
    # \(\bar x\) leaves "bar x" — collapse to "x_bar" so the patterns below
    # can match a single token.
    s = re.sub(r"\bbar\s*x\b", "x_bar", s)
    s = re.sub(r"\bbar\s*X\b", "x_bar", s)
    s = re.sub(r"\bbar\s*d\b", "d_bar", s)
    s = re.sub(r"\bbar\s*y\b", "y_bar", s)
    # x̄ / X̄ unicode glyphs.
    s = s.replace("x̄", "x_bar").replace("X̄", "x_bar")
    s = s.replace("ȳ", "y_bar").replace("Ȳ", "y_bar")
    s = s.replace("d̄", "d_bar").replace("D̄", "d_bar")
    # Greek glyphs we recognise.
    s = s.replace("σ", "sigma").replace("Σ", "Sigma")
    s = s.replace("μ", "mu").replace("Μ", "mu")
    s = s.replace("α", "alpha").replace("Α", "alpha")
    s = s.replace("β", "beta").replace("Β", "beta")
    s = s.replace("ρ", "rho").replace("χ", "chi")
    return s


# --------------------------------------------------------------------------- #
# Extraction                                                                   #
# --------------------------------------------------------------------------- #


_NUM = r"-?\d+(?:\.\d+)?"

# Each (key, regex) pair. The first capturing group is the value. Order
# matters: more-specific patterns come first so they win over generic
# fallbacks (e.g. ``mu_0`` before bare ``mu``).
_PATTERNS: Dict[str, list] = {
    # one-sample
    "n": [
        rf"\bn\s*=\s*({_NUM})\b",
        rf"sample\s+(?:size|of)\s+(?:n\s*=\s*)?({_NUM})\b",
    ],
    "x_bar": [
        rf"\bx_bar\s*=\s*({_NUM})",
        rf"sample\s+mean\s*(?:of|=|is)?\s*({_NUM})",
    ],
    "s": [
        rf"\bs\s*=\s*({_NUM})\b",
        rf"sample\s+standard\s+deviation\s*(?:of|=|is)?\s*({_NUM})",
        rf"\bs_d\s*=\s*({_NUM})\b",
    ],
    "s_squared": [
        rf"\bs\^?\s*2\s*=\s*({_NUM})\b",
        rf"\bs\s*\*\*\s*2\s*=\s*({_NUM})",
        rf"sample\s+variance\s*(?:of|=|is)?\s*({_NUM})",
    ],
    "sigma": [
        rf"\bsigma\s*=\s*({_NUM})\b",
        rf"(?:standard\s+deviation|std\.?\s+dev\.?)\s+(?:of|=|is)\s*({_NUM})",
        rf"known\s+(?:standard\s+deviation|sigma|σ)\s*(?:of|=|is)?\s*({_NUM})",
    ],
    "sigma_squared": [
        rf"\bsigma\^?\s*2\s*=\s*({_NUM})",
        rf"variance\s*(?:of|=|is)\s*({_NUM})",
    ],
    "mu_0": [
        rf"\bmu_0\s*=\s*({_NUM})",
        rf"\bmu\s*=\s*({_NUM})\b",   # plain mu in H_0 typically means mu_0
        rf"target\s+mean\s*(?:of|=|is)?\s*({_NUM})",
        rf"hypothesi[sz]ed\s+mean\s*(?:of|=|is)?\s*({_NUM})",
    ],
    "sigma_0": [
        rf"\bsigma_0\s*=\s*({_NUM})",
    ],
    "sigma_0_squared": [
        rf"\bsigma_0\^?\s*2\s*=\s*({_NUM})",
    ],
    "alpha": [
        rf"\balpha\s*=\s*({_NUM})\b",
        rf"significance\s+level\s+(?:of\s+)?({_NUM})",
        rf"at\s+the\s+(\d+(?:\.\d+)?)\s*%",   # convert later
        rf"at\s+(\d+(?:\.\d+)?)\s*%\s+(?:significance|level)",
    ],
    # proportion
    "p_0": [
        rf"\bp_0\s*=\s*({_NUM})",
        rf"hypothesi[sz]ed\s+proportion\s*(?:of|=|is)?\s*({_NUM})",
    ],
    "p_hat": [
        rf"\bp_hat\s*=\s*({_NUM})",
        rf"sample\s+proportion\s*(?:of|=|is)?\s*({_NUM})",
    ],
    "x": [
        rf"\b(?:observed|number\s+of)\s+(?:successes?|defectives?)\s*(?:=|of|is)?\s*(\d+)",
    ],
    # two-sample
    "n1": [rf"\bn_?1\s*=\s*(\d+)"],
    "n2": [rf"\bn_?2\s*=\s*(\d+)"],
    "x_bar1": [rf"\bx_bar_?1\s*=\s*({_NUM})", rf"\bx_bar_A\s*=\s*({_NUM})"],
    "x_bar2": [rf"\bx_bar_?2\s*=\s*({_NUM})", rf"\bx_bar_B\s*=\s*({_NUM})"],
    "s1": [rf"\bs_?1\s*=\s*({_NUM})\b"],
    "s2": [rf"\bs_?2\s*=\s*({_NUM})\b"],
    "sigma1": [rf"\bsigma_?1\s*=\s*({_NUM})\b"],
    "sigma2": [rf"\bsigma_?2\s*=\s*({_NUM})\b"],
    # paired
    "d_bar": [
        rf"\bd_bar\s*=\s*({_NUM})",
        rf"mean\s+(?:of\s+the\s+)?differences?\s*(?:=|is|of)?\s*({_NUM})",
    ],
    # regression (light — full SLR/MLR is deferred; we just surface what we can)
    "b0": [rf"\bb_?0\s*=\s*({_NUM})", rf"intercept\s*(?:=|is)?\s*({_NUM})"],
    "b1": [rf"\bb_?1\s*=\s*({_NUM})", rf"slope\s*(?:=|is)?\s*({_NUM})"],
    "R_squared": [
        rf"\bR\^?\s*2\s*=\s*({_NUM})",
        rf"R-?squared?\s*(?:=|is|of)?\s*({_NUM})",
    ],
}


# Tail / direction. We pick the strongest signal that fires; default to
# two-sided if nothing matches, which is the VE401 default.
_TAIL_PATTERNS = [
    ("two-sided", re.compile(r"two[\s-]sided|two[\s-]tailed", re.IGNORECASE)),
    ("two-sided", re.compile(r"differs?\s+from|not\s+equal", re.IGNORECASE)),
    ("right-tailed", re.compile(r"right[\s-]tailed|upper[\s-]tailed", re.IGNORECASE)),
    ("right-tailed", re.compile(r"exceeds?|greater\s+than|more\s+than|larger\s+than", re.IGNORECASE)),
    ("left-tailed", re.compile(r"left[\s-]tailed|lower[\s-]tailed", re.IGNORECASE)),
    ("left-tailed", re.compile(r"less\s+than|smaller\s+than|at\s+most|no\s+more\s+than", re.IGNORECASE)),
    ("one-sided", re.compile(r"one[\s-]sided|one[\s-]tailed", re.IGNORECASE)),
]


def _detect_tail(text: str) -> str:
    for label, rx in _TAIL_PATTERNS:
        if rx.search(text):
            return label
    return "two-sided"


# Categorical observed counts for chi-square GoF: capture sequences like
# "90 yellow, 35 green, 25 white" or "90, 35, 25 in three categories".
_CATEGORICAL_RE = re.compile(
    r"\b(\d+)\s+(?:[a-zA-Z][a-zA-Z\-]*)(?:\s*,\s*(\d+)\s+[a-zA-Z][a-zA-Z\-]*){2,}\b"
)


_NON_CATEGORY_WORDS = frozenset(
    {
        "categories", "groups", "samples", "trials",
        "observations", "people", "subjects", "ratio",
        "ratios", "level", "levels", "percent", "percents",
        "data", "values", "tests", "alpha", "minutes", "seconds",
        "hours", "days", "weeks", "years", "degrees", "decimal",
        "decimals", "predicted", "expected",
    }
)


def _extract_observed_counts(text: str) -> list:
    """Pull a sequence of category counts (≥ 3 categories).

    For χ² GoF the user usually writes ``"90 yellow, 35 green, 25 white"``.
    We grab every integer adjacent to an alphabetic label across the
    whole match span, returning the list of integers.

    Two pre-cleans guard against false positives:

    * colon-separated ratios (``9:3:4``) are wiped before pair matching,
      so the trailing ``4 ratio`` in ``"the predicted 9:3:4 ratio"`` does
      not look like a category;
    * a stop-list of common non-category nouns (``ratio``, ``data``,
      ``categories``, …) is consulted at every step, including the
      initial triple, so a non-category word never anchors a count.
    """
    if not text:
        return []
    # Wipe colon-ratios so "9:3:4 ratio" doesn't seed a "4 ratio" pair.
    cleaned = re.sub(r"\b\d+(?:\s*:\s*\d+){1,}\b", " ", text)

    pair_iter = [
        m for m in re.finditer(r"\b(\d{1,5})\s+([A-Za-z][A-Za-z\-]{2,})\b", cleaned)
        if m.group(2).lower() not in _NON_CATEGORY_WORDS
    ]
    if len(pair_iter) < 3:
        return []

    counts: list = []
    spans = pair_iter
    for i in range(len(spans) - 2):
        triple = spans[i : i + 3]
        if triple[2].start() - triple[0].end() > 200:
            continue
        counts = [int(triple[k].group(1)) for k in range(3)]
        end = triple[2].end()
        for m in spans[i + 3 :]:
            if m.start() - end > 200:
                break
            counts.append(int(m.group(1)))
            end = m.end()
        break
    return counts


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #


@dataclass
class Givens:
    """Numerical parameters extracted from a question."""

    raw: Dict[str, float] = field(default_factory=dict)
    tail: str = "two-sided"
    observed_counts: list = field(default_factory=list)
    text: str = ""

    def get(self, key: str, default=None):
        return self.raw.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self.raw

    def __getitem__(self, key: str):
        return self.raw[key]

    def to_dict(self) -> dict:
        return {
            "raw": dict(self.raw),
            "tail": self.tail,
            "observed_counts": list(self.observed_counts),
        }


def _coerce(key: str, raw_value: str) -> Optional[float]:
    try:
        v = float(raw_value)
    except (TypeError, ValueError):
        return None
    # "at the 5%" → α = 0.05
    if key == "alpha" and v > 1.0:
        v = v / 100.0
    return v


def extract_givens(text: str) -> Givens:
    """Extract numerical givens from a question string.

    The returned :class:`Givens` exposes a flat dict ``raw`` of recognised
    parameters (``n``, ``x_bar``, ``s``, ``sigma``, ``mu_0``, ``alpha``, …),
    a ``tail`` string in {two-sided, right-tailed, left-tailed, one-sided},
    and an ``observed_counts`` list for chi-square GoF inputs. Missing
    quantities are simply absent from the dict — the renderer will surface
    them as ``?`` in the formatted output.
    """
    norm = _normalise(text or "")
    out: Dict[str, float] = {}
    for key, pats in _PATTERNS.items():
        for pat in pats:
            m = re.search(pat, norm, flags=re.IGNORECASE)
            if not m:
                continue
            v = _coerce(key, m.group(1))
            if v is None:
                continue
            out[key] = v
            break
    tail = _detect_tail(text or "")
    counts = _extract_observed_counts(text or "")
    return Givens(raw=out, tail=tail, observed_counts=counts, text=text or "")


__all__ = ["extract_givens", "Givens", "normalise_text"]
