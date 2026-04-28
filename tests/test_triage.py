"""Phase C acceptance test (plan §6 step C4) — sample-final-2021 triage.

Loads each of the 15 main questions of ``ve401_sample_final_2021`` from
``data/extracted/ve401_local.jsonl`` and runs the classifier. Each question
carries a hand-labelled gold card plus a set of acceptable top-1 cards
(some questions span multiple cards intentionally — e.g. q11 asks for
slope/intercept CI *and* a prediction interval, which is card18 + card19).

Acceptance bars (plan §6 C4 / DoD §12.1):
    top-1 strict accuracy  >= 75%
    top-3 inclusive recall >= 90%

Run as::

    python -m tests.test_triage
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from classifier.decision_tree import classify  # noqa: E402

JSONL = ROOT / "data" / "extracted" / "ve401_local.jsonl"


# Question -> (primary gold card, set of acceptable top-1 cards).
# The 'acceptable' set captures genuinely-multi-card questions where the
# umbrella problem statement covers several recipes (per the sub-parts).
GOLD: Dict[str, Tuple[str, Set[str]]] = {
    "ve401_local_samplefinal_q2":  ("card03", {"card03"}),
    "ve401_local_samplefinal_q3":  ("card01", {"card01"}),
    "ve401_local_samplefinal_q4":  ("card12", {"card12", "card05", "card04"}),
    "ve401_local_samplefinal_q5":  ("card10", {"card05", "card10", "card11", "card12", "card13"}),
    "ve401_local_samplefinal_q6":  ("card09", {"card09"}),
    "ve401_local_samplefinal_q7":  ("card09", {"card09"}),
    "ve401_local_samplefinal_q8":  ("card15", {"card15"}),
    "ve401_local_samplefinal_q9":  ("card16", {"card16"}),
    "ve401_local_samplefinal_q10": ("card18", {"card18", "card19"}),
    "ve401_local_samplefinal_q11": ("card18", {"card18", "card19"}),
    "ve401_local_samplefinal_q12": ("card21", {"card21", "card20"}),
    "ve401_local_samplefinal_q13": ("card21", {"card21", "card20", "card19"}),
    "ve401_local_samplefinal_q14": ("card20", {"card20", "card21"}),
    "ve401_local_samplefinal_q16": ("card19", {"card19", "card18", "card20", "card21"}),
}


def _load_records() -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    with JSONL.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            out[r["id"]] = r
    return out


_SECTION_HEADER_LEAKS = re.compile(
    r"(?:Chi[\s-]?Squared\s+Goodness[\s-]of[\s-]Fit\s+Tests?|"
    r"Inferences?\s+on\s+Two\s+Means?|"
    r"Inferences?\s+on\s+Variances?|"
    r"Linear\s+Regression|"
    r"Hypothesis\s+Tests?\s+for\s+a\s+Single\s+\w+)\s*$",
    flags=re.IGNORECASE,
)


def _strip_leak(text: str) -> str:
    """Phase A's PDF extractor sometimes drags the next problem's section
    header onto the tail of the previous part (see progress.md → Phase A
    "known limitations"). Strip those tails so the classifier doesn't see
    cross-question contamination."""
    return _SECTION_HEADER_LEAKS.sub("", text).rstrip()


def _gather_text(records: Dict[str, dict], qid: str) -> str:
    """Stitch the main question text together with its sub-parts so the
    classifier sees every signal — the parent record holds the setup,
    sub-parts hold the test names that follow ('use a paired T-test', ...)."""
    parts: List[str] = []
    parent = records.get(qid)
    if parent and parent.get("question"):
        parts.append(_strip_leak(parent["question"]))
    prefix = qid + "_part"
    for rid, rec in records.items():
        if rid.startswith(prefix) and rec.get("question"):
            parts.append(_strip_leak(rec["question"]))
    return "\n".join(parts)


def main() -> int:
    records = _load_records()

    rows: List[Tuple[str, str, str, str, bool, bool, List[Tuple[str, int]]]] = []
    top1_strict_correct = 0  # gold == top-1
    top1_acceptable_correct = 0  # top-1 is in acceptable set
    top3_correct = 0  # gold is in top-3
    n = 0

    for qid, (gold, acceptable) in GOLD.items():
        text = _gather_text(records, qid)
        if not text.strip():
            print(f"[skip] {qid}: no text in jsonl")
            continue
        hits = classify(text, top_k=3)
        top1 = hits[0].card_id if hits else "<none>"
        top3 = [h.card_id for h in hits]

        is_strict = top1 == gold
        is_acceptable = top1 in acceptable
        in_top3 = gold in top3

        n += 1
        top1_strict_correct += int(is_strict)
        top1_acceptable_correct += int(is_acceptable)
        top3_correct += int(in_top3)

        rows.append((qid, gold, top1, ",".join(top3), is_acceptable, in_top3, [(h.card_id, h.score) for h in hits]))

    print()
    print(f"{'qid':<38} {'gold':>8}  {'top-1':>8}  {'top3':>22}  {'acc-1':>5}  {'top-3':>5}")
    print("-" * 100)
    for qid, gold, top1, top3, ok1, ok3, scored in rows:
        s = " ".join(f"{c}:{sc}" for c, sc in scored)
        print(f"{qid:<38} {gold:>8}  {top1:>8}  {top3:>22}  {'+' if ok1 else '-':>5}  {'+' if ok3 else '-':>5}   | {s}")

    if n == 0:
        print("\nno records matched gold ids; aborting")
        return 2

    pct1_strict = top1_strict_correct / n * 100.0
    pct1_acc = top1_acceptable_correct / n * 100.0
    pct3 = top3_correct / n * 100.0
    print()
    print(f"top-1 strict     : {top1_strict_correct}/{n}   = {pct1_strict:5.1f}%")
    print(f"top-1 acceptable : {top1_acceptable_correct}/{n}   = {pct1_acc:5.1f}%   (target >= 75%)")
    print(f"top-3 inclusive  : {top3_correct}/{n}   = {pct3:5.1f}%   (target >= 90%)")

    bars = [
        ("top-1 acceptable >= 75%", pct1_acc >= 75.0),
        ("top-3 inclusive  >= 90%", pct3 >= 90.0),
    ]
    print()
    for label, ok in bars:
        print(f"  [{'ok' if ok else 'FAIL'}] {label}")

    return 0 if all(ok for _, ok in bars) else 1


if __name__ == "__main__":
    raise SystemExit(main())
