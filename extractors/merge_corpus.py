"""Merge every per-source JSONL into the unified ``data/corpus.jsonl``.

This is the Phase B exit point: ``corpus.jsonl`` is the single file the
classifier, retriever, and trainer all read from in later phases.

Inputs (each optional — missing files are skipped with a warning, so this
script is safe to run before every external corpus has been extracted):

* ``data/extracted/ve401_local.jsonl``    — VE401 HTML + PDF (priority 1)
* ``data/extracted/crash_course.jsonl``   — 25 cards + traps + drills (1)
* ``data/extracted/hendrycks_math.jsonl`` — Counting & Probability (3)
* ``data/extracted/openintro.jsonl``      — OpenIntro Stats 4e (2)
* ``data/extracted/openstax.jsonl``       — OpenStax Intro Stats 2e (2)

Output:

* ``data/corpus.jsonl`` — deduped union of all of the above

Dedupe policy
-------------
Records are deduplicated by question fingerprint (SHA-1 of normalised
question text, see ``common.fingerprint``). When two records collide we
keep the one with the lower ``source_priority`` value (= higher priority,
since priority 1 = VE401 local, the gold standard). This guards against
the (unlikely) case where an external corpus accidentally republishes a
VE401 problem.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from extractors.common import (
    EXTRACTED_DIR,
    PROJECT_ROOT,
    fingerprint,
    read_jsonl,
    validate_records,
    write_jsonl,
)

CORPUS_PATH: Path = PROJECT_ROOT / "data" / "corpus.jsonl"

# Order matters only as documentation; merging is symmetric and the
# tie-breaker is `source_priority`. We list the priority-1 sources first
# so that, all else equal, they appear earlier in the output.
INPUTS: list[Path] = [
    EXTRACTED_DIR / "ve401_local.jsonl",
    EXTRACTED_DIR / "crash_course.jsonl",
    EXTRACTED_DIR / "openintro.jsonl",
    EXTRACTED_DIR / "openstax.jsonl",
    EXTRACTED_DIR / "hendrycks_math.jsonl",
]


def merge() -> int:
    combined: list[dict[str, Any]] = []
    per_source: dict[str, int] = {}
    for path in INPUTS:
        if not path.exists():
            print(f"[warn] skipping missing input: {path.name}", file=sys.stderr)
            continue
        records = read_jsonl(path)
        per_source[path.name] = len(records)
        combined.extend(records)
        print(f"[info] {path.name}: {len(records)} records")

    if not combined:
        print("[error] no input JSONLs found; nothing to merge.", file=sys.stderr)
        return 1

    # Dedupe by fingerprint, preferring the lower source_priority on
    # collision. `source_priority` is required by the schema, so direct
    # access is safe.
    seen: dict[str, dict[str, Any]] = {}
    collisions = 0
    for r in combined:
        fp = fingerprint(r["question"])
        existing = seen.get(fp)
        if existing is None:
            seen[fp] = r
            continue
        collisions += 1
        if r["source_priority"] < existing["source_priority"]:
            seen[fp] = r
    deduped = list(seen.values())

    errs = validate_records(deduped)
    if errs:
        print("[error] schema validation failed after merge:", file=sys.stderr)
        for e in errs[:20]:
            print("  -", e, file=sys.stderr)
        return 2

    n = write_jsonl(deduped, CORPUS_PATH)
    print(f"[ok] wrote {n} records to {CORPUS_PATH}")
    print(f"     collisions skipped: {collisions}")

    # Stats
    by_source: dict[str, int] = {}
    by_priority: dict[int, int] = {}
    by_type: dict[str, int] = {}
    with_sol = 0
    with_slides = 0
    with_rubric = 0
    for r in deduped:
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1
        by_priority[r["source_priority"]] = by_priority.get(r["source_priority"], 0) + 1
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
        if r["solution_steps"]:
            with_sol += 1
        if r["slide_refs"]:
            with_slides += 1
        if r["rubric"]:
            with_rubric += 1

    print(f"     inputs: {per_source}")
    print(f"     by source: {dict(sorted(by_source.items()))}")
    print(f"     by source_priority: {dict(sorted(by_priority.items()))}")
    print(f"     by type: {dict(sorted(by_type.items()))}")
    print(f"     with solution_steps: {with_sol}/{n} "
          f"({with_sol/max(n,1):.0%})")
    print(f"     with slide_refs:     {with_slides}/{n} "
          f"({with_slides/max(n,1):.0%})")
    print(f"     with rubric:         {with_rubric}/{n} "
          f"({with_rubric/max(n,1):.0%})")
    return 0


if __name__ == "__main__":
    sys.exit(merge())
