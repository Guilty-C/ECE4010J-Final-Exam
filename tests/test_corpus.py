"""Smoke tests for Phase B — the unified ``data/corpus.jsonl``.

Run from the project root:
    python -m tests.test_corpus

Plan §6 acceptance criteria for Phase B:

* corpus total record count ≥ 1,200
* schema consistency 100% (every record validates)
* no duplicate questions (fingerprint collisions resolved by merge)

Additional sanity checks we add here:

* every Phase A source is still represented in the corpus (i.e. the
  merge did not silently drop a partition)
* every external Phase B source contributed at least one record
* ``source_priority`` is bounded to {1, 2, 3} and obeys plan §5.3
  (priority 1 = ve401_local + crash_course)
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from extractors.common import (  # noqa: E402
    EXTRACTED_DIR,
    fingerprint,
    validate_records,
)

CORPUS_PATH: Path = PROJECT_ROOT / "data" / "corpus.jsonl"


def _read(path: Path) -> list[dict]:
    return [
        json.loads(l)
        for l in path.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]


def main() -> int:
    assert CORPUS_PATH.exists(), f"missing: {CORPUS_PATH}"
    records = _read(CORPUS_PATH)
    n = len(records)
    print(f"corpus.jsonl: {n} records")

    # 1. schema validation
    errs = validate_records(records)
    assert not errs, f"schema errors: {errs[:3]}"
    print("[ok] schema validation passed")

    # 2. volume floor (plan §6 Phase B: ≥ 1,200)
    assert n >= 1_200, f"corpus too small: {n} < 1200"
    print(f"[ok] volume floor (>=1200): {n}")

    # 3. fingerprint uniqueness — the merge should have killed every
    # collision. We re-check here so a future bug in `merge_corpus.py`
    # can't slip past unnoticed.
    fps = [fingerprint(r["question"]) for r in records]
    dup_count = sum(c - 1 for c in Counter(fps).values() if c > 1)
    assert dup_count == 0, f"corpus has {dup_count} duplicate questions"
    print("[ok] no fingerprint duplicates")

    # 4. every expected source is present.
    by_source = Counter(r["source"] for r in records)
    print(f"[info] by source: {dict(sorted(by_source.items()))}")

    # ve401_local + crash_course are the priority-1 sources from Phase A.
    # We don't require every external source to be present — the project
    # explicitly allows running the merge with a subset of corpora — but
    # we DO want to know if Phase A regressed silently.
    assert by_source.get("ve401_local", 0) > 0, "ve401_local missing"
    assert by_source.get("crash_course", 0) > 0, "crash_course missing"
    print("[ok] Phase A sources still present after Phase B merge")

    # 5. external source contribution. At least one of the three external
    # corpora should have landed; the plan §6 acceptance threshold of
    # 1,200 records cannot be hit from the local 288 records alone.
    ext_total = (
        by_source.get("openintro", 0)
        + by_source.get("openstax", 0)
        + by_source.get("hendrycks_math", 0)
    )
    assert ext_total >= 900, f"external contribution too low: {ext_total}"
    print(f"[ok] external corpora contributed {ext_total} records")

    # 6. source_priority bounded and consistent with plan §5.3.
    by_priority = Counter(r["source_priority"] for r in records)
    print(f"[info] by source_priority: {dict(sorted(by_priority.items()))}")
    assert set(by_priority).issubset({1, 2, 3}), \
        f"unexpected priority: {set(by_priority)}"

    p1_sources = {
        r["source"] for r in records if r["source_priority"] == 1
    }
    assert p1_sources == {"ve401_local", "crash_course"}, \
        f"priority 1 sources: {p1_sources}"
    print("[ok] source_priority partitioning consistent with plan §5.3")

    return 0


if __name__ == "__main__":
    sys.exit(main())
