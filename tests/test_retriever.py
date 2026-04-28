"""Phase D acceptance test (plan §6 step D3).

Two bars:

1.  ``retrieve_for_card(card_id)`` returns >= 1 template for **every** one of
    the 25 crash-course test cards. This is the literal D3 wording:
    "each card_id can recall at least 1 corresponding template".

2.  Free-text ``retrieve(query)`` puts a VE401-local template in the top-3 on
    a small smoke-test set of canonical questions covering the core test
    families (Z, T, chi-squared GoF, paired-T, SLR). Sanity-checks that the
    BM25 + classifier pipeline doesn't collapse on real wording.

Run as::

    python -m tests.test_retriever
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from classifier.decision_tree import all_card_ids, card_meta  # noqa: E402
from retriever.retrieve import get_retriever  # noqa: E402


# Canonical free-text queries — written in students' wording, not VE401's.
SMOKE_QUERIES: List[Tuple[str, str]] = [
    (
        "z-test sigma known",
        "A bottling line is calibrated so that the fill volume is normally "
        "distributed with known standard deviation sigma = 2 mL. The target "
        "mean is mu0 = 25 mL. A random sample of n = 25 bottles gives x_bar "
        "= 24.3 mL. At alpha = 0.05, test H0: mu = 25 vs H1: mu != 25.",
    ),
    (
        "t-test sigma unknown",
        "A random sample of 12 batteries gives a sample mean lifetime of "
        "47.5 hours and a sample standard deviation of 3.2 hours. Test at "
        "the 5% level whether the true mean lifetime exceeds 45 hours.",
    ),
    (
        "chi-square goodness of fit",
        "A geneticist counts 90 yellow, 35 green, 25 white seeds and asks "
        "whether the data fit the predicted 9:3:4 ratio. Test goodness of "
        "fit at alpha = 0.05 using the Pearson chi-square statistic.",
    ),
    (
        "paired t-test",
        "Twelve subjects had their cholesterol measured before and after a "
        "diet change. Use a paired T-test to decide whether the diet "
        "significantly reduced cholesterol.",
    ),
    (
        "simple linear regression",
        "We fit a simple linear regression of fuel consumption on engine "
        "displacement. Report the least-squares slope and intercept and a "
        "95% confidence interval for the slope.",
    ),
]


def main() -> int:
    print("Loading retriever (this classifies every record once; ~1-2 s)...")
    R = get_retriever()
    print(f"  corpus size : {len(R.records):>4}")
    print(f"  cards       : {len(R.by_card):>4}")
    print(f"  tags indexed: {len(R.by_tag):>4}")
    print(f"  slide refs  : {len(R.by_slide_ref):>4}")
    print()

    # ---- Bar 1: every card_id retrieves >= 1 template -------------------- #

    print("[bar 1] retrieve_for_card(card_id) returns >= 1 hit for every card")
    print("-" * 100)
    print(f"{'card':>6}  {'#bucket':>7}  {'#top3-only':>10}  {'top-1 source':>14}  {'top-1 priority':>15}  card title")
    bar1_pass = 0
    bar1_fail: List[str] = []
    for cid in all_card_ids():
        hits = R.retrieve_for_card(cid, top_k=5)
        meta = card_meta(cid) or {}
        primary_count = len(R.by_card.get(cid, []))
        top3_only_count = len(set(R.by_card_top3.get(cid, [])) - set(R.by_card.get(cid, [])))
        if not hits:
            print(f"{cid:>6}  {primary_count:>7}  {top3_only_count:>10}  {'<NO HITS>':>14}  {'-':>15}  {meta.get('title','')}")
            bar1_fail.append(cid)
            continue
        h = hits[0]
        bar1_pass += 1
        print(
            f"{cid:>6}  {primary_count:>7}  {top3_only_count:>10}  "
            f"{h.source:>14}  {h.priority_weight:>15.2f}  {meta.get('title','')}"
        )

    print()
    print(f"  bar 1 : {bar1_pass}/{len(all_card_ids())} cards have >= 1 template")
    print(f"  failures: {bar1_fail or 'none'}")
    print()

    # ---- Bar 2: smoke-test free-text queries hit a VE401-local template -- #

    print("[bar 2] retrieve(query) surfaces a VE401-local (priority=1) hit in top-3 for canonical queries")
    print("-" * 100)
    print(f"{'tag':>30}  {'top-3 sources':>40}  {'ve401-local in top-3?':>22}")
    bar2_pass = 0
    for tag, q in SMOKE_QUERIES:
        hits = R.retrieve(q, top_k=3)
        sources = [h.source for h in hits]
        has_local = any(s == "ve401_local" or s == "crash_course" for s in sources)
        bar2_pass += int(has_local)
        print(f"{tag:>30}  {','.join(sources):>40}  {'+' if has_local else '-':>22}")

    print()
    print(f"  bar 2 : {bar2_pass}/{len(SMOKE_QUERIES)} canonical queries put a VE401-local hit in top-3")
    print()

    # ---- Combined verdict ------------------------------------------------ #

    bars = [
        ("every card has >= 1 template", bar1_pass == len(all_card_ids())),
        (">= 4/5 canonical queries hit ve401-local in top-3", bar2_pass >= 4),
    ]
    print("=" * 100)
    for label, ok in bars:
        print(f"  [{'ok' if ok else 'FAIL'}] {label}")

    return 0 if all(ok for _, ok in bars) else 1


if __name__ == "__main__":
    raise SystemExit(main())
