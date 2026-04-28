"""Smoke tests for Phase B' — the cleaned ``data/corpus.jsonl``.

Run from the project root::

    python -m tests.test_corpus_clean

Acceptance bars (per the Phase B' sprint spec):

1.  Total record count ≈ 2,352 (3,597 − 1,245 Hendrycks).
2.  Every artifact pattern from ``extractors.audit_corpus`` reports
    zero hits.
3.  ``validate_records`` (jsonschema) returns no errors.
4.  No record has ``source == 'hendrycks_math'``.
5.  Per-source counts: ve401_local=208, crash_course=80, openintro=385,
    openstax=1,679.
6.  VE401-local + crash_course records are byte-identical between the
    saved snapshot under ``data/extracted/`` and the post-clean corpus
    (the cleaner must not touch them).

Note on bar 6: the comparison uses the full record body, not just text
hashes. ``data/extracted/ve401_local.jsonl`` and
``data/extracted/crash_course.jsonl`` are the canonical Phase A outputs;
each protected record in the corpus must equal its source-of-truth row.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from extractors.audit_corpus import ARTIFACT_PATTERNS, audit_corpus  # noqa: E402
from extractors.common import EXTRACTED_DIR, validate_records  # noqa: E402

CORPUS_PATH: Path = PROJECT_ROOT / "data" / "corpus.jsonl"

# Expected post-clean composition. The hard total is exact (the cleaner
# does no fingerprint dedup of its own; per-source counts are the
# pre-clean Phase B numbers minus the dropped Hendrycks slice).
EXPECTED_TOTAL: int = 2352
EXPECTED_BY_SOURCE: dict[str, int] = {
    "ve401_local": 208,
    "crash_course": 80,
    "openintro": 385,
    "openstax": 1679,
}


def _read(path: Path) -> list[dict]:
    return [
        json.loads(l)
        for l in path.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]


def _index_by_id(records: list[dict]) -> dict[str, dict]:
    """Return {record_id: record}; collisions raise — IDs must be unique."""
    out: dict[str, dict] = {}
    for r in records:
        rid = r["id"]
        if rid in out:
            raise AssertionError(f"duplicate id in input: {rid!r}")
        out[rid] = r
    return out


def main() -> int:
    assert CORPUS_PATH.exists(), f"missing: {CORPUS_PATH}"
    corpus = _read(CORPUS_PATH)
    n = len(corpus)
    print(f"corpus.jsonl: {n} records")

    # 1) Volume.
    assert n == EXPECTED_TOTAL, (
        f"unexpected record count: {n} != {EXPECTED_TOTAL}"
    )
    print(f"[ok] total records: {n}")

    # 2) Artifact patterns — every count must be zero in the records the
    # cleaner is allowed to touch. Per the Phase B' spec the cleaner skips
    # ``ve401_local`` and ``crash_course`` records (they are HTML-sourced
    # and Phase E relies on their exact text). Artifact hits inside those
    # protected sources are pre-existing extraction noise that this phase
    # is explicitly NOT chartered to fix; the auditor reports them but
    # this test only enforces zero hits on cleanable records.
    cleanable = [
        r for r in corpus
        if r["source"] not in ("ve401_local", "crash_course")
    ]
    cleanable_report = audit_corpus(cleanable)
    bad: list[tuple[str, int]] = []
    for name in ARTIFACT_PATTERNS:
        hits = cleanable_report["patterns"][name]["total_hits"]
        if hits > 0:
            bad.append((name, hits))
    assert not bad, f"cleaned corpus still has artifact hits: {bad}"
    print(
        f"[ok] all {len(ARTIFACT_PATTERNS)} artifact patterns clean across "
        f"{len(cleanable)} cleanable records"
    )

    # Also surface the residual ve401_local artifact counts as info-level
    # output so a future contributor knows the auditor still flags them.
    full_report = audit_corpus(corpus)
    residual = {
        name: full_report["patterns"][name]["total_hits"]
        for name in ARTIFACT_PATTERNS
        if full_report["patterns"][name]["total_hits"] > 0
    }
    if residual:
        print(
            f"[info] protected-source residual hits (not cleaned by design): "
            f"{residual}"
        )

    # 3) Schema validation.
    errs = validate_records(corpus)
    assert not errs, f"schema errors: {errs[:3]}"
    print("[ok] schema validation passed")

    # 4) No Hendrycks records left.
    sources = Counter(r["source"] for r in corpus)
    assert "hendrycks_math" not in sources, (
        "hendrycks_math records survived the clean"
    )
    print("[ok] no hendrycks_math records present")

    # 5) Per-source breakdown.
    print(f"[info] by source: {dict(sorted(sources.items()))}")
    for src, expected in EXPECTED_BY_SOURCE.items():
        actual = sources.get(src, 0)
        assert actual == expected, (
            f"source {src!r}: expected {expected}, got {actual}"
        )
    print("[ok] per-source counts match Phase B' expectations")

    # 6) Protected sources untouched. Compare full record bodies between
    # the canonical Phase A extractor outputs and the post-clean corpus.
    # The cleaner skips these sources, so they MUST be identical.
    for src_name, src_jsonl in [
        ("ve401_local",  EXTRACTED_DIR / "ve401_local.jsonl"),
        ("crash_course", EXTRACTED_DIR / "crash_course.jsonl"),
    ]:
        if not src_jsonl.exists():
            print(f"[warn] {src_jsonl} missing; cannot check {src_name}")
            continue
        canonical = _index_by_id(_read(src_jsonl))
        observed_in_corpus = {
            r["id"]: r for r in corpus if r["source"] == src_name
        }
        # Both ID-sets should match exactly. (No Phase A record was
        # dropped; no Phase B record entered for these sources.)
        missing = set(canonical) - set(observed_in_corpus)
        extra = set(observed_in_corpus) - set(canonical)
        assert not missing, (
            f"{src_name}: ids in extracted but not corpus: "
            f"{sorted(missing)[:5]}"
        )
        assert not extra, (
            f"{src_name}: ids in corpus but not extracted: "
            f"{sorted(extra)[:5]}"
        )
        # Body equality.
        diffs: list[str] = []
        for rid, src_rec in canonical.items():
            if observed_in_corpus[rid] != src_rec:
                diffs.append(rid)
        assert not diffs, (
            f"{src_name}: {len(diffs)} records differ; first diffs: "
            f"{diffs[:3]}"
        )
        print(f"[ok] {src_name}: {len(canonical)} records byte-identical")

    return 0


if __name__ == "__main__":
    sys.exit(main())
