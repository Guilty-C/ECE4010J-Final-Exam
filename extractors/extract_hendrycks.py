"""Extract the Hendrycks MATH `Counting & Probability` slice into JSONL.

Source: ``data/raw/hendrycks_math/competition_math.parquet`` — a single-file
parquet of the Hendrycks MATH benchmark, published on HuggingFace as
``qwedsacf/competition_math``. Schema: ``problem``, ``level``, ``type``,
``solution`` (LaTeX prose with ``\\boxed{...}`` final answer).

Filtering policy
----------------
Plan §2.2 only keeps the prob/stat-relevant subset. The published dataset's
``type`` column has 7 high-level categories; we keep:

* ``Counting & Probability`` — directly on-topic (1,245 problems)

We deliberately skip ``Prealgebra`` because that bucket is dominated by
arithmetic and pre-arithmetic word problems; on inspection there are very
few statistics items there and they are noisy. The crash-course / VE401
local corpus already covers descriptive statistics. ``Number Theory`` and
``Geometry`` are entirely off-topic.

Schema mapping
--------------
* ``id`` = ``hendrycks_<row_index>`` so it is stable across re-runs.
* ``source_priority`` = 3 (lowest weight; consumed by ``prepare_dataset.py``).
* ``chapter`` left as ``None`` — Hendrycks problems do not align to VE401's
  chapter structure.
* ``solution_steps`` = single-step record with label ``"Solution"`` carrying
  the full LaTeX solution body. We do not attempt to parse it into the
  five-section VE401 layout because the solutions are competition-style
  and would not survive that mapping.
* ``final_answer`` = contents of the last ``\\boxed{...}`` in the solution
  (this is the Hendrycks convention for the final numeric answer).
* ``difficulty`` = ``"easy" | "medium" | "hard"`` mapped from levels
  1-2 / 3 / 4-5; "Level ?" rows fall back to None.
* ``topic_tags`` = ``["counting", "probability"]`` for the Counting &
  Probability subset.

Output: ``data/extracted/hendrycks_math.jsonl``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from extractors.common import (
    EXTRACTED_DIR,
    PROJECT_ROOT,
    make_record,
    validate_records,
    write_jsonl,
)

INPUT_PATH: Path = PROJECT_ROOT / "data" / "raw" / "hendrycks_math" / "competition_math.parquet"
OUTPUT_PATH: Path = EXTRACTED_DIR / "hendrycks_math.jsonl"

# Categories we keep from the ``type`` column. Only Counting & Probability
# is consistently on-topic for VE401's combinatorics / discrete probability
# warm-ups (Ch 15-18 of the lecture slides).
KEEP_TYPES: set[str] = {"Counting & Probability"}

# Hendrycks ``level`` strings (``"Level 1"`` … ``"Level 5"``, plus the
# stray ``"Level ?"``) → VE401 difficulty buckets. Levels 1-2 are warm-up
# items, 3 is mid-difficulty, 4-5 are competition-grade.
_LEVEL_TO_DIFF: dict[str, str] = {
    "Level 1": "easy",
    "Level 2": "easy",
    "Level 3": "medium",
    "Level 4": "hard",
    "Level 5": "hard",
}

# Pull the contents of the last ``\boxed{...}`` group. The dataset wraps
# the final answer in ``\\boxed{...}`` by convention; if the body has more
# than one ``\\boxed`` the last one is always the final answer (earlier
# ones are intermediate boxed expressions inside the proof). The regex
# uses a simple non-greedy match because nested braces are extremely rare
# in this slice (Counting & Probability solutions are short prose with
# numeric answers).
_BOXED_RE = re.compile(r"\\boxed\{([^{}]*)\}")


def _final_answer(solution: str) -> str | None:
    """Return the contents of the last ``\\boxed{...}`` or None."""
    matches = _BOXED_RE.findall(solution or "")
    if not matches:
        return None
    return matches[-1].strip() or None


def _build_record(row_index: int, row: dict[str, Any]) -> dict[str, Any]:
    problem: str = row["problem"]
    solution: str = row.get("solution") or ""
    level: str = row.get("level") or ""
    cat: str = row.get("type") or ""

    diff = _LEVEL_TO_DIFF.get(level)

    # ``topic_tags`` mirror the Hendrycks category. We use lower-case,
    # hyphenless tokens to stay consistent with `tag_taxonomy.json`'s
    # convention (e.g. "one-sample-Z").
    tags: list[str]
    if cat == "Counting & Probability":
        tags = ["counting", "probability"]
    else:
        # Defensive: KEEP_TYPES already filters this, but keep the branch
        # to avoid surprising emissions if KEEP_TYPES is widened later.
        tags = [cat.lower().replace(" & ", "-").replace(" ", "-")]

    final = _final_answer(solution)

    steps = []
    if solution.strip():
        steps.append({
            "step_id": 1,
            "label": "Solution",
            "content": solution.strip(),
        })

    return make_record(
        id=f"hendrycks_{row_index:05d}",
        source="hendrycks_math",
        source_priority=3,
        chapter=None,
        topic_tags=tags,
        slide_refs=[],
        difficulty=diff,
        language="en",
        type="exercise",
        question=problem.strip(),
        given=None,
        solution_steps=steps,
        rubric=[],
        traps=[],
        trail_of_thought=None,
        final_answer=final,
    )


def main() -> int:
    if not INPUT_PATH.exists():
        print(f"[error] missing parquet: {INPUT_PATH}", file=sys.stderr)
        print(
            "        download it via:\n"
            "        curl -sL "
            "https://hf-mirror.com/datasets/qwedsacf/competition_math/"
            "resolve/main/data/train-00000-of-00001-7320a6f3aba8ebd2.parquet "
            f"-o {INPUT_PATH}",
            file=sys.stderr,
        )
        return 1

    # Lazy import: pandas+pyarrow are heavy and only this extractor uses
    # them. The rest of the pipeline reads JSONL directly.
    import pandas as pd

    df = pd.read_parquet(INPUT_PATH)
    print(f"[info] loaded {len(df)} rows from {INPUT_PATH.name}")

    kept_df = df[df["type"].isin(KEEP_TYPES)].reset_index(drop=False)
    print(f"[info] kept {len(kept_df)} rows after type filter "
          f"({sorted(KEEP_TYPES)})")

    records: list[dict[str, Any]] = []
    for _, row in kept_df.iterrows():
        # ``index`` is the original row index in the parquet, used for a
        # stable id. ``iterrows`` yields a Series, but `make_record`
        # only touches a fixed set of keys so coerce via .to_dict().
        rec = _build_record(int(row["index"]), row.to_dict())
        records.append(rec)

    errs = validate_records(records)
    if errs:
        print("[error] schema validation failed:", file=sys.stderr)
        for e in errs[:10]:
            print("  -", e, file=sys.stderr)
        return 2

    n = write_jsonl(records, OUTPUT_PATH)
    print(f"[ok] wrote {n} records to {OUTPUT_PATH}")

    # Stats
    by_diff: dict[str, int] = {}
    with_final = 0
    with_sol = 0
    for r in records:
        d = r.get("difficulty") or "—"
        by_diff[d] = by_diff.get(d, 0) + 1
        if r.get("final_answer"):
            with_final += 1
        if r["solution_steps"]:
            with_sol += 1
    print(f"     by difficulty: {dict(sorted(by_diff.items()))}")
    print(f"     with final_answer: {with_final}/{n}")
    print(f"     with solution_steps: {with_sol}/{n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
