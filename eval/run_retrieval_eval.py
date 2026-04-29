from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from retriever.query_exercise_index import query_index


def iter_cases(path: Path) -> list[dict[str, Any]]:
    cases = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                cases.append(json.loads(line))
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate VE401 retrieval cases.")
    parser.add_argument("--cases", default="eval/retrieval_eval_cases.jsonl")
    parser.add_argument("--index", default="data/exercise_index")
    parser.add_argument("--suite", default="")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--pool-size", type=int, default=140)
    parser.add_argument("--backend", default="dense", choices=["auto", "dense", "tfidf"])
    args = parser.parse_args()

    cases = iter_cases(Path(args.cases))
    if args.suite:
        cases = [case for case in cases if case.get("suite") == args.suite]

    top1 = top3 = top5 = 0
    misses = []
    for case in cases:
        hits = query_index(
            str(case["query"]),
            Path(args.index),
            top_k=args.top_k,
            pool_size=args.pool_size,
            backend=args.backend,
        )
        expected = set(case["expected"])
        procs = [hit["features"].get("procedure") for hit in hits]
        rank = next((idx + 1 for idx, proc in enumerate(procs) if proc in expected), None)
        top1 += rank == 1
        top3 += bool(rank and rank <= 3)
        top5 += bool(rank and rank <= 5)
        if rank != 1:
            misses.append(
                {
                    "id": case["id"],
                    "rank": rank,
                    "expected": sorted(expected),
                    "top": procs,
                    "hit_ids": [hit["id"] for hit in hits],
                }
            )

    total = len(cases)
    suite = args.suite or "all"
    print(f"suite={suite} top1={top1}/{total} top3={top3}/{total} top5={top5}/{total}")
    if misses:
        print("misses:")
        for miss in misses:
            print(json.dumps(miss, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
