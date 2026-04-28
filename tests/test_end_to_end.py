"""Phase F MVP gate (plan §6 step F3 / DoD §12.1).

Runs ``solver.solve()`` end-to-end on the 14 main-question records of
``ve401_sample_final_2021`` and checks the three MVP acceptance bars:

* **Card identification** — top-1 card is in the gold-acceptable set
  for at least 14 of the 16 source questions
  (the JSONL has 14 records; q1 is a multiple-choice umbrella whose
  sub-parts are graded separately, q15 is absent from the source PDF).
* **Skeleton consistency** — the rendered Markdown contains all five
  canonical sections (Setup / Hypotheses / Statistic / Computation /
  Decision) as well as a slide-ref line, for ≥ 12/14 questions.
* **Per-question latency** — each call to ``solve()`` returns in under
  2 s on warm caches.

Run as::

    python -m tests.test_end_to_end
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from solver import solve  # noqa: E402

JSONL = ROOT / "data" / "extracted" / "ve401_local.jsonl"


# Same gold mapping the Phase C test uses. We re-state it locally rather
# than import from tests.test_triage so this MVP gate is self-contained
# and would still run if the triage test were ever removed/refactored.
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


SECTION_HEADERS = ("## Setup", "## Hypotheses", "## Statistic", "## Computation", "## Decision")
SLIDE_REF_RE = re.compile(r"^\*Slide refs:\*", flags=re.MULTILINE)


_SECTION_HEADER_LEAKS = re.compile(
    r"(?:Chi[\s-]?Squared\s+Goodness[\s-]of[\s-]Fit\s+Tests?|"
    r"Inferences?\s+on\s+Two\s+Means?|"
    r"Inferences?\s+on\s+Variances?|"
    r"Linear\s+Regression|"
    r"Hypothesis\s+Tests?\s+for\s+a\s+Single\s+\w+)\s*$",
    flags=re.IGNORECASE,
)


def _strip_leak(text: str) -> str:
    return _SECTION_HEADER_LEAKS.sub("", text).rstrip()


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


def _gather_text(records: Dict[str, dict], qid: str) -> str:
    """Concatenate the umbrella question with all of its sub-part records,
    same as the Phase C test does. Sub-parts carry the test names that
    follow ('use a paired T-test', ...) which the umbrella may not."""
    parts: List[str] = []
    parent = records.get(qid)
    if parent and parent.get("question"):
        parts.append(_strip_leak(parent["question"]))
    prefix = qid + "_part"
    for rid, rec in records.items():
        if rid.startswith(prefix) and rec.get("question"):
            parts.append(_strip_leak(rec["question"]))
    return "\n".join(parts)


def _check_skeleton(md: str) -> Tuple[bool, List[str]]:
    """A rendered answer is 'consistent' iff it has all five canonical
    section headers and a slide-ref line. Returns (ok, missing_labels)."""
    missing: List[str] = []
    for h in SECTION_HEADERS:
        if h not in md:
            missing.append(h.lstrip("# "))
    if not SLIDE_REF_RE.search(md):
        missing.append("Slide-refs line")
    return (not missing), missing


def main() -> int:
    records = _load_records()

    # Per-question results
    rows: List[Tuple[str, str, str, bool, bool, List[str], float]] = []
    n = 0
    card_ok_acceptable = 0
    skeleton_ok = 0
    latencies: List[float] = []

    for qid, (gold, acceptable) in GOLD.items():
        text = _gather_text(records, qid)
        if not text.strip():
            print(f"[skip] {qid}: no text in jsonl")
            continue

        t0 = time.perf_counter()
        result = solve(text)
        dt = time.perf_counter() - t0

        n += 1
        latencies.append(dt)

        top1 = result.card_id or "<none>"
        is_acceptable = top1 in acceptable
        card_ok_acceptable += int(is_acceptable)

        ok, missing = _check_skeleton(result.markdown)
        skeleton_ok += int(ok)

        rows.append((qid, gold, top1, is_acceptable, ok, missing, dt))

    if n == 0:
        print("\nno records matched gold ids; aborting")
        return 2

    # Print the per-question table.
    print()
    print(f"{'qid':<38} {'gold':>8}  {'top-1':>8}  {'card?':>5}  {'skel?':>5}  {'time(ms)':>8}  missing")
    print("-" * 110)
    for qid, gold, top1, ok_card, ok_skel, missing, dt in rows:
        miss_str = ",".join(missing) if missing else ""
        print(
            f"{qid:<38} {gold:>8}  {top1:>8}  "
            f"{'+' if ok_card else '-':>5}  {'+' if ok_skel else '-':>5}  "
            f"{dt * 1000:8.1f}  {miss_str}"
        )

    pct_card = card_ok_acceptable / n * 100.0
    pct_skel = skeleton_ok / n * 100.0
    max_dt_ms = max(latencies) * 1000.0
    avg_dt_ms = sum(latencies) / len(latencies) * 1000.0

    print()
    print(f"records evaluated  : {n} (of 16 source questions; q1 is MCQ-umbrella, q15 absent)")
    print(f"card-id acceptable : {card_ok_acceptable}/{n}   = {pct_card:5.1f}%   "
          f"(MVP gate >= 14/16 of source = {14/16*100:.1f}%)")
    print(f"skeleton 5-section : {skeleton_ok}/{n}   = {pct_skel:5.1f}%   "
          f"(MVP gate >= 12/14 = {12/14*100:.1f}%)")
    print(f"latency (avg/max)  : {avg_dt_ms:.1f} ms / {max_dt_ms:.1f} ms   (MVP gate < 2000 ms)")

    bars = [
        # The MVP gate is "≥14 of 16 source questions identify the right type".
        # We have 14 type-bearing records in the JSONL; therefore the bar
        # collapses to 14/14 acceptable here.
        (f"card-id acceptable >= 14 of 16 source questions",
         card_ok_acceptable >= 14),
        (f"skeleton consistency >= 12/14",
         skeleton_ok >= 12),
        (f"max latency < 2000 ms",
         max_dt_ms < 2000.0),
    ]
    print()
    for label, ok in bars:
        print(f"  [{'ok' if ok else 'FAIL'}] {label}")

    return 0 if all(ok for _, ok in bars) else 1


if __name__ == "__main__":
    raise SystemExit(main())
