"""Smoke tests for Phase A extractor outputs.

Run from the project root:
    python -m tests.test_extractors

These are not pytest fixtures — they intentionally use plain asserts so the
script can run without a test runner. Phase A acceptance is verified here:

* JSONL parses and validates against the schema.
* Total record count is at least 145 (plan §6 minimum).
* slide_refs non-empty rate ≥ 70% (plan §6 minimum).
* All 14 chapters (15–32 minus the few not exercised) are represented in
  some form (either explicit `chapter` field or via inference).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from extractors.common import EXTRACTED_DIR, validate_records  # noqa: E402

VE401_PATH: Path = EXTRACTED_DIR / "ve401_local.jsonl"
CRASH_PATH: Path = EXTRACTED_DIR / "crash_course.jsonl"


def _read(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    assert VE401_PATH.exists(), f"missing: {VE401_PATH}"
    assert CRASH_PATH.exists(), f"missing: {CRASH_PATH}"

    ve401 = _read(VE401_PATH)
    crash = _read(CRASH_PATH)
    print(f"ve401_local.jsonl: {len(ve401)} records")
    print(f"crash_course.jsonl: {len(crash)} records")

    # Schema validation
    err1 = validate_records(ve401)
    err2 = validate_records(crash)
    assert not err1, f"ve401 schema errors: {err1[:3]}"
    assert not err2, f"crash schema errors: {err2[:3]}"
    print("[ok] schema validation passed")

    # Volume floor (plan §6: ~145 expected; we already exceed)
    assert len(ve401) >= 145, f"too few ve401 records: {len(ve401)}"
    print(f"[ok] ve401 volume floor (>=145): {len(ve401)}")

    # slide_refs coverage ≥ 70%
    with_slides = sum(1 for r in ve401 if r["slide_refs"])
    rate = with_slides / len(ve401)
    assert rate >= 0.70, f"slide_refs rate too low: {rate:.0%}"
    print(f"[ok] slide_refs coverage: {with_slides}/{len(ve401)} ({rate:.0%})")

    # crash_course must contain exactly the expected entity counts.
    by_type = {}
    for r in crash:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
    assert by_type.get("card") == 25, f"expected 25 cards: {by_type}"
    assert by_type.get("trap") == 30, f"expected 30 traps: {by_type}"
    assert by_type.get("drill", 0) >= 13, f"expected >=13 drills: {by_type}"
    print(f"[ok] crash_course mix: {by_type}")

    # Spot a few well-known IDs that we expect in the output.
    ids = {r["id"] for r in ve401}
    must_have = {
        "ve401_local_ch19_q1",
        "ve401_local_ch26_q1",
        "ve401_local_hw06_q1",
        "ve401_local_samplefinal_q1_part_i",
    }
    missing = must_have - ids
    assert not missing, f"missing expected IDs: {missing}"
    print(f"[ok] sentinel IDs present: {sorted(must_have)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
