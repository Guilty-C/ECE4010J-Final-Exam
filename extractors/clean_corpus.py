"""Idempotent corpus cleaner — Phase B'.

Reads ``data/corpus.jsonl``, drops every record whose ``source`` is
``hendrycks_math`` (per the user's explicit instruction — that subset is
off-topic for the VE401 syllabus), normalises six classes of
PDF/HTML extraction artifacts on the remaining external sources, and
overwrites ``data/corpus.jsonl`` in place.

Inputs / outputs
----------------
* INPUT  ``data/corpus.jsonl``        — Phase B output, 3,597 records
* OUTPUT ``data/corpus.jsonl``        — overwritten, ≈ 2,352 records

The original per-source ``data/extracted/hendrycks_math.jsonl`` is left on
disk untouched (per the user's request to "保留 jsonl"); only the merged
corpus is rewritten.

Design contract
---------------
1.  **Source whitelist.** VE401-local sources (``ve401_local``,
    ``crash_course``) are HTML-sourced and already canonical; the cleaner
    yields them through verbatim. The Phase E renderer relies on their
    exact text for slide-numbered formula citations, so any mutation here
    would risk Phase E regressions.
2.  **Idempotent.** Every rule is shaped so that running the cleaner twice
    produces the same output as running it once. (Verified by an in-script
    fixed-point check on the first few records.)
3.  **Schema-preserving.** Field set / types per record are unchanged; we
    only rewrite string contents inside ``question``,
    ``solution_steps[*].content``, ``final_answer``, ``trail_of_thought``.
    Identifiers, sources, chapters, slide refs, topic tags, rubrics, and
    traps are passed through untouched.

Rules (applied in this order)
-----------------------------
The order matters: ``decimal_colon`` runs before ``dist_semicolon`` so a
parenthesised parameter list with both a colon and a semicolon (extremely
rare; not observed in the current corpus) is normalised to commas+periods
rather than colons+commas.

1.  ``decimal_colon``  ``(?<!\d:)(\d):(\d{2,})``  →  ``\1.\2``
2.  ``not_equal``      ``\b6=``                    →  ``!=``
3.  ``dist_semicolon`` (named-distribution span)  →  ``;`` → ``,``
4.  ``cid_token``      ``\(cid:\d+\)``            →  ``""``
5.  ``link_residual``  ``<link[^>]*?/?>``         →  ``[Table/Figure]``
6.  ``test_spacing``   ``\b([A-Za-z])\s*-\s*test\b`` (with whitespace)  →  ``\1-test``

Implementation note for ``dist_semicolon``
------------------------------------------
A naive single-pass regex like
``r'\b(N|Bin|...)\(([^)]*?);([^)]*?)\)'`` over-matches when the parameter
list contains an unrelated nested expression that happens to balance — and
under-matches when there are multiple semicolons in the same span (only
the first would be replaced). We therefore implement this rule as a
**two-pass scan**: first locate every parenthesised distribution span
with ``re.finditer``, then run ``str.replace(';', ',')`` on the contents
of each span and splice the cleaned span back into the original string.
This handles N parameters and N semicolons cleanly.

CLI
---
::

    python -m extractors.clean_corpus               # in-place clean
    python -m extractors.clean_corpus --dry-run     # report, do not write
    python -m extractors.clean_corpus --out X.jsonl # write to alt path
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Pattern

from extractors.common import (
    PROJECT_ROOT,
    read_jsonl,
    validate_records,
    write_jsonl,
)

# --------------------------------------------------------------------------- #
# Paths and configuration
# --------------------------------------------------------------------------- #

CORPUS_PATH: Path = PROJECT_ROOT / "data" / "corpus.jsonl"

#: Sources whose records are skipped by the cleaner (passed through
#: verbatim). ``ve401_local`` and ``crash_course`` are HTML-derived and
#: relied on by Phase E for exact-text formula matches.
PROTECTED_SOURCES: frozenset[str] = frozenset({"ve401_local", "crash_course"})

#: Sources to drop entirely from the corpus.
DROPPED_SOURCES: frozenset[str] = frozenset({"hendrycks_math"})


# --------------------------------------------------------------------------- #
# Substitution rules (excluding dist_semicolon, which is a two-pass scan)
# --------------------------------------------------------------------------- #

# Each entry is ``(name, compiled_pattern, replacement)``. Order matters; see
# module docstring for rationale.
_SUBSTITUTION_RULES: list[tuple[str, Pattern[str], str]] = [
    # 1) decimal_colon — see audit_corpus.py for the negative lookbehind that
    #    prevents cascade matches on ``2:30:45``-style timestamps.
    ("decimal_colon", re.compile(r"(?<!\d:)(\d):(\d{2,})"), r"\1.\2"),
    # 2) not_equal — Greek-glyph drop.
    ("not_equal",     re.compile(r"\b6="),                   r"!="),
    # 4) cid_token — pdfminer.six unmapped-glyph leftover.
    ("cid_token",     re.compile(r"\(cid:\d+\)"),            r""),
    # 5) link_residual — empty CNXML cross-reference. The OpenStax
    #    extractor already substitutes ``[Table/Figure]`` for known cases;
    #    this catches anything missed.
    ("link_residual", re.compile(r"<link[^>]*?/?>"),         r"[Table/Figure]"),
    # 6) test_spacing — the spec asks us to flag ONLY when whitespace
    #    surrounds the hyphen. Two alternations cover the 'left', 'right',
    #    and 'both' subcases. The capture group preserves the leading
    #    letter (``T``, ``z``, ``F``, ...) verbatim.
    ("test_spacing",
        re.compile(r"\b([A-Za-z])\s+-\s*test\b|\b([A-Za-z])\s*-\s+test\b"),
        None),  # special replacement: see _apply_test_spacing
]

# --------------------------------------------------------------------------- #
# Distribution-bracket span detector (two-pass rule)
# --------------------------------------------------------------------------- #

_DIST_NAMES = r"(?:N|Bin|Poisson|Exp|chi\^?2|t|F|Geom|HG|U)"

# Find spans of the form ``DistName(...)`` where the body has no nested
# parens. Non-greedy + ``[^()]*`` gives the smallest balanced span. We
# require word-boundary on the left so ``Sin(``, ``cos(``, etc. do not
# match. Allow optional whitespace between the name and ``(``.
_DIST_SPAN_RE: Pattern[str] = re.compile(
    rf"\b{_DIST_NAMES}\s*\([^()]*\)"
)


def _apply_dist_semicolon(text: str) -> tuple[str, int]:
    """Replace ``;`` with ``,`` only inside named-distribution parens.

    Returns ``(new_text, n_replacements)``. Idempotent: a second pass
    finds zero spans containing ``;``.
    """
    if ";" not in text:
        return text, 0
    n_repl = 0
    out_parts: list[str] = []
    pos = 0
    for m in _DIST_SPAN_RE.finditer(text):
        out_parts.append(text[pos:m.start()])
        span = m.group(0)
        if ";" in span:
            count_in_span = span.count(";")
            span = span.replace(";", ",")
            n_repl += count_in_span
        out_parts.append(span)
        pos = m.end()
    if pos == 0:
        # No spans matched anywhere — nothing to do, return unchanged
        # (shares identity with input for the common no-hit case).
        return text, 0
    out_parts.append(text[pos:])
    return "".join(out_parts), n_repl


def _apply_test_spacing(text: str) -> tuple[str, int]:
    """Collapse ``T -test`` / ``T- test`` / ``T - test`` → ``T-test``.

    Captured letter is in either group 1 or group 2 depending on which
    alternation fired. We pick whichever is non-None.
    """
    n_repl = 0

    def _sub(m: "re.Match[str]") -> str:
        nonlocal n_repl
        n_repl += 1
        letter = m.group(1) or m.group(2)
        return f"{letter}-test"

    # Pull the compiled pattern out of the rules list to keep the truth in
    # a single place.
    pat = next(p for name, p, _ in _SUBSTITUTION_RULES if name == "test_spacing")
    new_text = pat.sub(_sub, text)
    return new_text, n_repl


# --------------------------------------------------------------------------- #
# Per-string apply
# --------------------------------------------------------------------------- #

def _clean_string_one_pass(
    text: str, counters: Counter | None = None
) -> tuple[str, int]:
    """Apply all six rules to a string once; return (result, n_repl)."""
    if not text:
        return text, 0
    total = 0
    out = text
    for name, pat, repl in _SUBSTITUTION_RULES:
        if name == "test_spacing":
            new, n = _apply_test_spacing(out)
        elif repl is None:
            continue  # only test_spacing uses the sentinel
        else:
            new, n = pat.subn(repl, out)
        if n and counters is not None:
            counters[name] += n
        total += n
        out = new
    # dist_semicolon (two-pass scan over named-distribution spans)
    out, n_dist = _apply_dist_semicolon(out)
    if n_dist and counters is not None:
        counters["dist_semicolon"] += n_dist
    total += n_dist
    return out, total


def clean_string(text: str, counters: Counter | None = None) -> str:
    """Apply all six rules to a single string until fixed-point.

    Most rules are single-pass idempotent (re-running them produces no
    further changes). The exception is ``decimal_colon`` on cascading
    timestamps: ``1:22:28`` gets normalised to ``1.22:28`` on pass 1
    (the negative lookbehind blocks ``2:28`` because position-1's ``\\d:``
    boundary still exists), then to ``1.22.28`` on pass 2 (the lookbehind
    no longer triggers because the preceding char is now ``.``).

    Bounding the loop matters for safety: if a future rule somehow
    inserted text that re-triggered itself, the loop would never
    terminate. We iterate for at most ``max_passes`` (8) and assert
    convergence — well above the 3 passes any cascade in this corpus
    requires (longest observed: 1:22:28 → 1.22:28 → 1.22.28, fixed in 2).

    If ``counters`` is supplied, every successful replacement across all
    passes accumulates into the counter so the caller sees real total
    impact, not just first-pass impact.
    """
    if not text:
        return text
    out = text
    for _pass in range(8):
        out, n = _clean_string_one_pass(out, counters)
        if n == 0:
            return out
    # Reaching here means a rule re-fires after 8 iterations — should be
    # impossible with the current rule set; treat as a code-smell bug.
    raise AssertionError(
        "clean_string did not converge in 8 passes — possible non-monotone "
        "rule was added to _SUBSTITUTION_RULES."
    )


# --------------------------------------------------------------------------- #
# Per-record apply
# --------------------------------------------------------------------------- #

def clean_record(rec: dict[str, Any], counters: Counter | None = None) -> dict[str, Any]:
    """Return a cleaned shallow copy of ``rec``. Protected sources untouched.

    The function returns a *new* dict so the caller can choose to compare
    pre/post and so we never accidentally retain a reference to the
    original mutable JSON object.
    """
    if rec.get("source") in PROTECTED_SOURCES:
        return dict(rec)  # shallow copy keeps identity invariants clean

    out = dict(rec)

    # question
    q = out.get("question")
    if isinstance(q, str):
        out["question"] = clean_string(q, counters)

    # solution_steps[*].content (rebuild list to avoid mutating original
    # nested dicts which may be shared with the caller's record).
    steps = out.get("solution_steps") or []
    new_steps: list[dict[str, Any]] = []
    for step in steps:
        if isinstance(step, dict):
            new_step = dict(step)
            content = new_step.get("content")
            if isinstance(content, str):
                new_step["content"] = clean_string(content, counters)
            new_steps.append(new_step)
        else:
            # Schema disallows non-dict steps but defensive: pass through.
            new_steps.append(step)
    out["solution_steps"] = new_steps

    # final_answer
    fa = out.get("final_answer")
    if isinstance(fa, str):
        out["final_answer"] = clean_string(fa, counters)

    # trail_of_thought
    tot = out.get("trail_of_thought")
    if isinstance(tot, str):
        out["trail_of_thought"] = clean_string(tot, counters)

    return out


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #

def clean_corpus(
    records: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, int]]:
    """Run drops + cleans over an iterable of records.

    Returns (cleaned_records, source_drop_counts, rule_application_counts).
    """
    counters: Counter = Counter()
    drops: Counter = Counter()
    out: list[dict[str, Any]] = []
    for rec in records:
        src = rec.get("source")
        if src in DROPPED_SOURCES:
            drops[src] += 1
            continue
        out.append(clean_record(rec, counters))
    return out, dict(drops), dict(counters)


# --------------------------------------------------------------------------- #
# Self-check: idempotency
# --------------------------------------------------------------------------- #

def assert_idempotent(records: list[dict[str, Any]], k: int = 50) -> None:
    """Spot-check that re-cleaning the first ``k`` records is a no-op.

    Raises ``AssertionError`` if the cleaner is not idempotent — this is a
    development-time guarantee; the script aborts before overwriting the
    corpus if it ever fires.
    """
    sample = records[:k]
    once = [clean_record(r) for r in sample]
    twice = [clean_record(r) for r in once]
    if once != twice:
        # Find the offending record/field for a useful error message.
        for a, b in zip(once, twice):
            if a != b:
                raise AssertionError(
                    f"cleaner not idempotent on id={a.get('id')!r}; "
                    f"diff in question or steps."
                )
        raise AssertionError("cleaner not idempotent (exact mismatch unknown)")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument(
        "--corpus", type=Path, default=CORPUS_PATH,
        help=f"Input/output corpus JSONL (default: {CORPUS_PATH}).",
    )
    ap.add_argument(
        "--out", type=Path, default=None,
        help="Alternate output path. Defaults to overwriting --corpus.",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Compute stats and report changes but do not write the output.",
    )
    args = ap.parse_args(argv)

    if not args.corpus.exists():
        print(f"[error] corpus not found: {args.corpus}", file=sys.stderr)
        return 1

    in_records = read_jsonl(args.corpus)
    print(f"[info] read {len(in_records)} records from {args.corpus}")

    cleaned, drops, rule_hits = clean_corpus(in_records)
    print(f"[info] dropped sources: {drops}")
    print(f"[info] rule replacement counts: {rule_hits}")
    print(f"[info] output records: {len(cleaned)}")

    # Idempotency self-check — cheap, runs on a 50-record sample.
    assert_idempotent(cleaned)
    print("[ok] idempotency self-check passed (50-record sample)")

    # Schema validation — refuse to write a broken corpus.
    errs = validate_records(cleaned)
    if errs:
        print("[error] cleaned corpus failed schema validation:", file=sys.stderr)
        for e in errs[:10]:
            print("  -", e, file=sys.stderr)
        return 2
    print("[ok] schema validation passed")

    if args.dry_run:
        print("[info] --dry-run: not writing output")
        return 0

    out_path: Path = args.out or args.corpus
    n = write_jsonl(cleaned, out_path)
    print(f"[ok] wrote {n} records to {out_path}")

    # Per-source breakdown post-clean (mirrors merge_corpus.py output for
    # easy diffing in the progress log).
    by_source = Counter(r["source"] for r in cleaned)
    print(f"     by source: {dict(sorted(by_source.items()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
