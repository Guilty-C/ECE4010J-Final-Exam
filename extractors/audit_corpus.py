"""Read-only auditor for ``data/corpus.jsonl`` artifact patterns.

Phase B' adds this script alongside ``clean_corpus.py``: the auditor measures
the prevalence of six classes of PDF / HTML extraction artifacts in the
unified corpus, both before and after the cleaner runs. It writes a JSON
report to ``data/audit_before.json`` (or ``audit_after.json`` — the output
filename is chosen automatically based on whether each artifact count is
zero) and prints the same summary to stdout.

The auditor itself is read-only: it never opens ``corpus.jsonl`` for write
and never modifies any record.

Patterns audited
----------------
Six independent regexes, each annotated with a short rationale. The exact
shapes are documented inline next to ``ARTIFACT_PATTERNS`` below; the
short summary is:

1. ``decimal_colon``  — pdfminer drops the period in numbers like ``0.37`` →
   ``0:37``. Filtered to skip cascading ``2:30:45`` style timestamps via a
   negative lookbehind on ``\d:``.
2. ``not_equal``      — Greek-glyph drop rendering ``≠`` as ``6=``.
3. ``dist_semicolon`` — distribution-bracket parameter separators that
   should be commas, e.g. ``N(0; 1)`` instead of ``N(0, 1)``.
4. ``cid_token``      — pdfminer.six leftover ``(cid:NN)`` glyph stubs.
5. ``link_residual``  — empty/self-closing CNXML ``<link/>`` cross-refs that
   the OpenStax extractor missed.
6. ``test_spacing``   — spurious whitespace around the hyphen in test names
   such as ``T -test`` (only counted when whitespace exists; ``T-test``
   is NOT a hit).

Output
------
JSON of the form::

    {
      "corpus_path": "...",
      "n_records": 3597,
      "by_source": { "openstax": 1679, ... },
      "patterns": {
         "decimal_colon": {
            "total_hits": 284,
            "records_affected": 217,
            "by_source": {"ve401_local": 213, "openstax": 7, ...},
            "examples": [ "...0:37 hours..." ]
         },
         ...
      }
    }

CLI
---
::

    python -m extractors.audit_corpus               # auto-pick before/after
    python -m extractors.audit_corpus --out X.json  # explicit output
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Pattern

from extractors.common import PROJECT_ROOT, read_jsonl

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

CORPUS_PATH: Path = PROJECT_ROOT / "data" / "corpus.jsonl"
AUDIT_BEFORE_PATH: Path = PROJECT_ROOT / "data" / "audit_before.json"
AUDIT_AFTER_PATH:  Path = PROJECT_ROOT / "data" / "audit_after.json"

# --------------------------------------------------------------------------- #
# Pattern definitions
# --------------------------------------------------------------------------- #

# 1) decimal-as-colon — only fires when the colon is between a single digit
#    and *two or more* digits, AND is not preceded by ``\d:``. The lookbehind
#    rejects cascade matches inside timestamps (``2:30:45`` → only ``2:30``
#    matches, then the second ``:45`` is rejected because position is
#    preceded by ``0:``). True positives: ``0:37`` from PDF-extracted
#    ``0.37``. Known false positives that pass: leading-digit time-of-day
#    forms like ``1:22`` or ``8:55 am`` — accepted as a cost of keeping the
#    regex simple; the cleaner restricts itself to non-VE401 sources where
#    the hit volume is small (~10 in openintro+openstax).
RE_DECIMAL_COLON: Pattern[str] = re.compile(r"(?<!\d:)(\d):(\d{2,})")

# 2) ASCII inequality — ``\b6=`` matches the Greek-glyph drop signature.
#    Naive ``\b`` matches between digit and ``=`` so it can fire on real
#    arithmetic like ``5\cdot 6=30``. The auditor counts all matches; the
#    cleaner is restricted to non-Hendrycks, non-VE401 sources where this
#    pattern has zero true OR false hits in the current corpus, so the
#    looseness has no operational impact.
RE_NOT_EQUAL: Pattern[str] = re.compile(r"\b6=")

# 3) distribution-bracket semicolons — finds the parenthesised parameter
#    list of a named distribution and flags it if it contains a literal ``;``.
#    The non-greedy ``[^()]*?`` avoids spanning unrelated parentheses; the
#    explicit ``;`` filter selects only true positives. The cleaner uses a
#    two-pass version (find spans, replace ``;`` inside) to stay tight.
_DIST_NAMES = r"(?:N|Bin|Poisson|Exp|chi\^?2|t|F|Geom|HG|U)"
RE_DIST_SEMICOLON: Pattern[str] = re.compile(
    rf"\b{_DIST_NAMES}\([^()]*?;[^()]*?\)"
)

# 4) pdfminer cid leftover (e.g. ``(cid:107)`` for unmapped glyphs)
RE_CID_TOKEN: Pattern[str] = re.compile(r"\(cid:\d+\)")

# 5) OpenStax empty cross-reference residuals — ``<link target-id="..."/>``
#    or ``<link/>``. The OpenStax extractor already substitutes these; this
#    audit finds anything missed.
RE_LINK_RESIDUAL: Pattern[str] = re.compile(r"<link[^>]*?/?>")

# 6) spaced test names — ``T -test``, ``T- test``, ``T - test``. We must
#    only count when *some* whitespace surrounds the hyphen; ``T-test`` is
#    fine. We use two alternations and intentionally drop the no-space case.
RE_TEST_SPACING: Pattern[str] = re.compile(
    r"\b[A-Za-z]\s+-\s*test\b|\b[A-Za-z]\s*-\s+test\b"
)

#: Ordered map ``name → compiled pattern`` driving the audit.
ARTIFACT_PATTERNS: dict[str, Pattern[str]] = {
    "decimal_colon":  RE_DECIMAL_COLON,
    "not_equal":      RE_NOT_EQUAL,
    "dist_semicolon": RE_DIST_SEMICOLON,
    "cid_token":      RE_CID_TOKEN,
    "link_residual":  RE_LINK_RESIDUAL,
    "test_spacing":   RE_TEST_SPACING,
}


# --------------------------------------------------------------------------- #
# Iteration helpers
# --------------------------------------------------------------------------- #

def iter_text_fields(rec: dict[str, Any]) -> Iterable[tuple[str, str]]:
    """Yield ``(field_label, text)`` for every audit-eligible string field.

    Audited fields per spec: ``question``, every ``solution_steps[*].content``,
    ``final_answer``, ``trail_of_thought``. Strings are skipped when missing
    or empty (``None`` or zero-length); only string values are yielded.
    """
    q = rec.get("question")
    if isinstance(q, str) and q:
        yield "question", q
    for i, step in enumerate(rec.get("solution_steps") or []):
        content = step.get("content") if isinstance(step, dict) else None
        if isinstance(content, str) and content:
            yield f"solution_steps[{i}].content", content
    fa = rec.get("final_answer")
    if isinstance(fa, str) and fa:
        yield "final_answer", fa
    tot = rec.get("trail_of_thought")
    if isinstance(tot, str) and tot:
        yield "trail_of_thought", tot


# --------------------------------------------------------------------------- #
# Audit core
# --------------------------------------------------------------------------- #

def audit_corpus(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute the artifact-frequency report.

    Time complexity: O(N * F * P) where N = records, F = audited fields per
    record (~3–4 on average), P = number of patterns (6). Each regex scans
    the field once; with N≈3,600 the total work is well under a second.

    Returns a dict shaped per the module docstring.
    """
    by_source = Counter(r.get("source", "<unknown>") for r in records)

    pattern_report: dict[str, Any] = {}
    for name, pat in ARTIFACT_PATTERNS.items():
        total_hits = 0
        affected_records: set[str] = set()
        per_source_hits: Counter = Counter()
        examples: list[dict[str, str]] = []
        for rec in records:
            rec_id = rec.get("id", "<no-id>")
            rec_src = rec.get("source", "<unknown>")
            rec_had_hit = False
            for field_label, text in iter_text_fields(rec):
                # `findall` would return all matches as strings/tuples; we
                # use `finditer` so we can collect short context snippets
                # for the first few examples without an extra pass.
                matches = list(pat.finditer(text))
                if not matches:
                    continue
                total_hits += len(matches)
                per_source_hits[rec_src] += len(matches)
                rec_had_hit = True
                if len(examples) < 8:
                    m = matches[0]
                    s = max(0, m.start() - 30)
                    e = min(len(text), m.end() + 30)
                    examples.append({
                        "id": rec_id,
                        "source": rec_src,
                        "field": field_label,
                        "context": text[s:e],
                    })
            if rec_had_hit:
                affected_records.add(rec_id)
        pattern_report[name] = {
            "total_hits": total_hits,
            "records_affected": len(affected_records),
            "by_source": dict(sorted(per_source_hits.items())),
            "examples": examples,
        }

    return {
        "corpus_path": str(CORPUS_PATH),
        "n_records": len(records),
        "by_source": dict(sorted(by_source.items())),
        "patterns": pattern_report,
    }


# --------------------------------------------------------------------------- #
# Pretty-printer
# --------------------------------------------------------------------------- #

def print_report(report: dict[str, Any]) -> None:
    """Emit a compact human-readable summary on stdout."""
    print(f"corpus: {report['corpus_path']}")
    print(f"records: {report['n_records']}")
    print(f"by source: {report['by_source']}")
    print("artifact pattern hits:")
    print(f"  {'pattern':<16}  {'total_hits':>10}  {'records':>8}  by_source")
    for name, p in report["patterns"].items():
        bys = ",".join(f"{s}={n}" for s, n in p["by_source"].items())
        print(
            f"  {name:<16}  {p['total_hits']:>10}  "
            f"{p['records_affected']:>8}  {bys or '-'}"
        )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _choose_default_output(report: dict[str, Any]) -> Path:
    """Pick the output path based on observable corpus state.

    Heuristic: presence of any ``hendrycks_math`` records means we are
    looking at the pre-clean corpus (Phase B's hendrycks slice has not
    been dropped yet); their absence means we are looking at the
    post-clean corpus. This is the only state-bit that lets us
    distinguish before/after without an explicit CLI flag, because
    artifact counts in ``ve401_local`` records remain non-zero by
    design (the cleaner is contractually forbidden from touching them).
    """
    has_hendrycks = report["by_source"].get("hendrycks_math", 0) > 0
    return AUDIT_BEFORE_PATH if has_hendrycks else AUDIT_AFTER_PATH


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument(
        "--out", type=Path, default=None,
        help="Output JSON path (default: data/audit_before.json or "
             "data/audit_after.json depending on whether the corpus is "
             "already clean).",
    )
    ap.add_argument(
        "--corpus", type=Path, default=CORPUS_PATH,
        help=f"Corpus JSONL to audit (default: {CORPUS_PATH}).",
    )
    args = ap.parse_args(argv)

    if not args.corpus.exists():
        print(f"[error] corpus not found: {args.corpus}", file=sys.stderr)
        return 1

    records = read_jsonl(args.corpus)
    report = audit_corpus(records)
    out_path: Path = args.out or _choose_default_output(report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print_report(report)
    print(f"[ok] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
