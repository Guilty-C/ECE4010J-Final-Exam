"""Merge VE401-local extracted JSONLs into a single ve401_local.jsonl,
deduplicate by question fingerprint, validate the schema, and report
summary statistics.

Inputs (must already exist; see other extractors in this package):
    data/extracted/ve401_local.jsonl    (HTML exercises)
    data/extracted/ve401_pdf.jsonl      (homework + sample-final)

Output:
    data/extracted/ve401_local.jsonl    (overwritten with merged superset)

Crash-course (`crash_course.jsonl`) is kept as its own file because plan §5
treats it as a separate corpus stream — only the per-question banks merge
into `ve401_local`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import re

from extractors.common import (
    CHAPTER_SLIDE_ANCHOR,
    EXTRACTED_DIR,
    fingerprint,
    read_jsonl,
    validate_records,
    write_jsonl,
)


# Keyword → chapter inference, used only for records that have chapter=None
# (PDF homework + sample-final segments). Each pattern is a tight,
# course-specific phrase whose presence pins the chapter unambiguously.
# Order matters: the FIRST match wins, so put more specific patterns earlier.
# Order matters — surnames like "Pearson" appear inside compound names
# ("Neyman-Pearson"), so the more specific compound must be checked first.
_CHAPTER_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    # Compound proper-noun checks must come before single-word ones so
    # "Neyman-Pearson Decision Test" is not mis-routed by the "Pearson" tag.
    (re.compile(r"Neyman[\s\-]Pearson|operating\s+characteristic",
                re.IGNORECASE), "17"),
    (re.compile(r"\bBartlett", re.IGNORECASE), "32"),
    (re.compile(r"\bANOVA\b|\bSSTr\b", re.IGNORECASE), "31"),
    (re.compile(r"\bmodel\s+selection\b|\bPRESS\b|\bforward\s+selection\b|\bbackward\s+elimination\b",
                re.IGNORECASE), "30"),
    (re.compile(r"\bpartial\s+F|\bMLR\b|multiple\s+linear\s+regression",
                re.IGNORECASE), "29"),
    (re.compile(r"\bX\^?T\s*X|hat\s+matrix|\bpartial\s+regression",
                re.IGNORECASE), "28"),
    (re.compile(r"prediction\s+interval|new\s+observation|extrapolation",
                re.IGNORECASE), "27"),
    (re.compile(r"\bSLR\b|simple\s+linear\s+regression|S_xx|S_xy|S_yy|"
                r"\\beta_1|\\beta_0|fit\s+a\s+line",
                re.IGNORECASE), "26"),
    (re.compile(r"goodness[\s\-]of[\s\-]fit|chi-?squared?\s+test\s+of\s+independence|"
                r"contingency\s+table|test\s+of\s+homogeneity|\bGoF\b",
                re.IGNORECASE), "25"),
    # Pearson tightened to the correlation context — bare "Pearson" matches
    # too many surnames (Neyman-Pearson, Karl Pearson chi-squared, …).
    (re.compile(r"\bpaired\b|correlation|Fisher.*z\b|Pearson\s+(?:correlation|coeff|rho)",
                re.IGNORECASE), "24"),
    (re.compile(r"\bWelch|pooled|two[\s\-]sample\s+T", re.IGNORECASE), "23"),
    (re.compile(r"\bF[\s\-]test\b.*variances?|two\s+variances", re.IGNORECASE), "22"),
    (re.compile(r"proportion|defective\s+rate|p_0|\\hat\s*p", re.IGNORECASE), "21"),
    (re.compile(r"\bWilcoxon\b|sign\s+test|rank[\s\-]sum|Mann[\s\-]Whitney",
                re.IGNORECASE), "20"),
    (re.compile(r"Z[\s\-]test|T[\s\-]test|chi[\s\-]squared?\s+test\s+for\s+(?:one\s+)?variance",
                re.IGNORECASE), "19"),
    (re.compile(r"Fisher.*test\b|p[\s\-]value|significance\s+test", re.IGNORECASE), "16"),
    (re.compile(r"confidence\s+interval", re.IGNORECASE), "15"),
]


def infer_chapter(text: str) -> str | None:
    for pat, ch in _CHAPTER_KEYWORDS:
        if pat.search(text):
            return ch
    return None

HTML_PATH: Path = EXTRACTED_DIR / "ve401_local.jsonl"
PDF_PATH: Path = EXTRACTED_DIR / "ve401_pdf.jsonl"
MERGED_PATH: Path = EXTRACTED_DIR / "ve401_local.jsonl"


def merge() -> tuple[int, int, int]:
    """Return (n_total, n_after_dedup, n_collisions)."""
    if not HTML_PATH.exists():
        print(f"[error] missing HTML JSONL: {HTML_PATH}", file=sys.stderr)
        return (0, 0, 0)

    html_records = read_jsonl(HTML_PATH)
    pdf_records = read_jsonl(PDF_PATH) if PDF_PATH.exists() else []
    print(f"[info] html records: {len(html_records)}")
    print(f"[info] pdf records:  {len(pdf_records)}")

    combined: list[dict] = list(html_records) + list(pdf_records)

    # Dedupe by question fingerprint, keeping the first occurrence (HTML
    # entries come first and are higher quality than PDF-extracted ones).
    seen: dict[str, dict] = {}
    collisions = 0
    for r in combined:
        fp = fingerprint(r["question"])
        if fp in seen:
            collisions += 1
            continue
        seen[fp] = r
    deduped = list(seen.values())

    # Chapter inference for records that arrived without a chapter (PDF
    # homework + sample-final segments). We pattern-match the question text
    # against course-specific keywords; misses are left as None.
    inferred = 0
    for r in deduped:
        if r.get("chapter"):
            continue
        ch = infer_chapter(r["question"])
        if ch is None and r["solution_steps"]:
            joined = " ".join(s["content"] for s in r["solution_steps"])
            ch = infer_chapter(joined)
        if ch:
            r["chapter"] = ch
            inferred += 1
    if inferred:
        print(f"[info] chapter inferred from keywords for {inferred} records")

    # Chapter-anchor fallback for slide_refs: any record that knows its
    # chapter but has an empty slide_refs list inherits the canonical
    # primary slide for that chapter. Records with chapter=None (e.g.
    # sample-final entries that span chapters) are left untouched.
    fallback_applied = 0
    for r in deduped:
        if r["slide_refs"]:
            continue
        ch = r.get("chapter")
        if ch and ch in CHAPTER_SLIDE_ANCHOR:
            r["slide_refs"] = [CHAPTER_SLIDE_ANCHOR[ch]]
            fallback_applied += 1
    if fallback_applied:
        print(f"[info] chapter-anchor fallback applied to {fallback_applied} records")

    errs = validate_records(deduped)
    if errs:
        print("[error] schema validation failed after merge:", file=sys.stderr)
        for e in errs[:20]:
            print("  -", e, file=sys.stderr)
        return (len(combined), 0, collisions)

    write_jsonl(deduped, MERGED_PATH)
    print(f"[ok] wrote {len(deduped)} records to {MERGED_PATH}")
    print(f"     collisions skipped: {collisions}")

    # Stats
    by_source: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_chapter: dict[str, int] = {}
    with_sol = 0
    with_slides = 0
    with_rubric = 0
    for r in deduped:
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
        ch = r.get("chapter") or "—"
        by_chapter[ch] = by_chapter.get(ch, 0) + 1
        if r["solution_steps"]:
            with_sol += 1
        if r["slide_refs"]:
            with_slides += 1
        if r["rubric"]:
            with_rubric += 1
    n = len(deduped)
    print(f"     by source: {by_source}")
    print(f"     by type:   {by_type}")
    print(f"     by chapter: {dict(sorted(by_chapter.items()))}")
    print(f"     with solution_steps: {with_sol}/{n}"
          f" ({with_sol/max(n,1):.0%})")
    print(f"     with slide_refs:     {with_slides}/{n}"
          f" ({with_slides/max(n,1):.0%})")
    print(f"     with rubric:         {with_rubric}/{n}"
          f" ({with_rubric/max(n,1):.0%})")
    return (len(combined), len(deduped), collisions)


def main() -> int:
    n_total, n_dedup, _ = merge()
    if n_dedup == 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
