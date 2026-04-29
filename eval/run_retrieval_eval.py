from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from retriever.query_exercise_index import ExerciseIndex

ALIASES_PATH = ROOT / "ontology" / "ve401_label_aliases.json"


def iter_cases(path: Path) -> list[dict[str, Any]]:
    cases = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                cases.append(json.loads(line))
    return cases


def load_label_aliases(path: Path = ALIASES_PATH) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {str(key): [str(item) for item in value] for key, value in data.get("aliases", {}).items()}


def expand_expected(labels: list[str], aliases: dict[str, list[str]]) -> set[str]:
    expanded = set(str(label) for label in labels)
    for label in list(expanded):
        expanded.update(aliases.get(label, []))
    return expanded


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
    aliases = load_label_aliases()
    exercise_index = ExerciseIndex(Path(args.index), backend=args.backend)
    for case in cases:
        hits = exercise_index.query(
            str(case["query"]),
            top_k=args.top_k,
            pool_size=args.pool_size,
        )
        expected_raw = [str(label) for label in case["expected"]]
        expected = expand_expected(expected_raw, aliases)
        procs = [hit["features"].get("procedure") for hit in hits]
        hit_label_sets = [
            {str(hit["features"].get("procedure", "")), *[str(tag) for tag in hit["features"].get("concept_tags", []) or []]}
            for hit in hits
        ]
        rank = next((idx + 1 for idx, labels in enumerate(hit_label_sets) if labels & expected), None)
        top1 += rank == 1
        top3 += bool(rank and rank <= 3)
        top5 += bool(rank and rank <= 5)
        if rank != 1:
            misses.append(
                {
                    "id": case["id"],
                    "rank": rank,
                    "expected": sorted(expected),
                    "expected_raw": sorted(expected_raw),
                    "top": procs,
                    "top_labels": [sorted(labels) for labels in hit_label_sets],
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
