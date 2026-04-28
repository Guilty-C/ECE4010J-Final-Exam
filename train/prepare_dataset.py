"""train/prepare_dataset.py — Phase I1.

Reads ``data/corpus.jsonl`` and emits train/val/test JSONL files of
(messages, metadata) records ready for an SFT trainer that calls
``tokenizer.apply_chat_template``. Records with empty ``solution_steps``
are skipped (they cannot teach a question→answer mapping).

Output (under ``data/training/``)::

    train.jsonl  ~3,200 examples (after weighted oversampling)
    val.jsonl    ~115 examples
    test.jsonl   ~115 examples

Each line::

    {"id": "ve401_local_ch19_q1",
     "source": "ve401_local",
     "source_priority": 1,
     "messages": [
        {"role": "system",    "content": "..."},
        {"role": "user",      "content": "..."},
        {"role": "assistant", "content": "..."}
     ],
     "card_id": "card01" | null,
     "weight": 1.0}

Splits are stratified by ``source`` so every split contains every source
in proportion. Deterministic with ``--seed`` (default 4010).

Priority-weighted oversampling (plan §5.3) is applied to the *train*
split only:

==========  ============  ====================
priority    title         repeat factor
1           VE401 gold     3.0
2           OpenIntro/OS   1.5
3           Hendrycks      1.0
==========  ============  ====================

A 1.5× factor is realised stochastically: every other record gets a
second copy. The seeded RNG keeps it reproducible.

Stdlib only. Run::

    python -m train.prepare_dataset
    python -m train.prepare_dataset --in data/corpus.jsonl --out data/training
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
DEFAULT_IN = _REPO / "data" / "corpus.jsonl"
DEFAULT_OUT = _REPO / "data" / "training"

# Path to the optional triage classifier — used only to attach card_id
# metadata so train_lora can compute a cheap class-balanced eval. Import
# is best-effort: if the classifier package is not importable we just
# leave card_id=None.
try:  # pragma: no cover - tested via main run
    sys.path.insert(0, str(_REPO))
    from classifier.triage_rules import triage_record  # type: ignore
except Exception:  # pragma: no cover
    triage_record = None  # type: ignore[assignment]

# ----------------------------------------------------------------------
# System prompt (matches plan §8.4 with light adjustments for English-
# heavy corpora — OpenStax/OpenIntro/Hendrycks records are all English,
# so keep the system message bilingual-but-direct).
# ----------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a teaching assistant for VE401 / ECE4010J "
    "(Probabilistic Methods in Engineering, chapters 15–32). "
    "Answer in English. Follow the slide-notation conventions: "
    "Welch df rounded down, df = k - 1 - m for chi-square goodness-of-fit, "
    "denominator with p_0 for proportion tests, two-sided alternative "
    "uses z_{alpha/2}. When relevant, cite slide pages. Structure the "
    "answer in five labelled sections: Setup, Hypotheses, Statistic, "
    "Computation, Decision. Surface common traps and grading checkpoints "
    "where helpful."
)


# ----------------------------------------------------------------------
# Answer rendering
# ----------------------------------------------------------------------

_LABEL_PRIORITY = {
    # Map any of the corpus's solution_steps labels onto the canonical
    # five-section spine. Anything unknown falls through verbatim.
    "Assumptions": "Setup",
    "Setup": "Setup",
    "Hypotheses": "Hypotheses",
    "Statistic": "Statistic",
    "Test statistic": "Statistic",
    "Computation": "Computation",
    "Computation of statistic": "Computation",
    "Critical value": "Decision",
    "Critical value / P-value": "Decision",
    "Decision": "Decision",
    "Conclusion": "Decision",
    "Interpretation": "Decision",
    "Body": "Computation",  # short-form crash-course drills
}


def _render_answer(rec: dict) -> str:
    """Build the assistant turn from solution_steps + slide_refs + rubric +
    traps + final_answer.

    The rendered text is plain Markdown with ``## `` section headers; the
    same skeleton the rule renderer in ``solver/render.py`` emits.
    """
    out: List[str] = []

    slide_refs = rec.get("slide_refs") or []
    if slide_refs:
        out.append(
            "*Slide refs:* " + ", ".join(f"slide {p}" for p in slide_refs)
        )
        out.append("")

    # Group steps by canonical section so we get one ``## Setup`` etc.
    # even if the source uses two steps with overlapping labels.
    grouped: dict[str, List[str]] = {}
    order: List[str] = []
    for step in rec.get("solution_steps") or []:
        raw_label = (step.get("label") or "").strip()
        canon = _LABEL_PRIORITY.get(raw_label, raw_label or "Body")
        if canon not in grouped:
            grouped[canon] = []
            order.append(canon)
        content = (step.get("content") or "").strip()
        if content:
            grouped[canon].append(content)

    for label in order:
        out.append(f"## {label}")
        for chunk in grouped[label]:
            out.append(chunk)
        out.append("")

    rubric = rec.get("rubric") or []
    if rubric:
        out.append("## Rubric")
        for r in rubric:
            point = (r.get("point") or "").strip()
            marks = r.get("marks")
            if marks is None:
                out.append(f"- {point}")
            else:
                out.append(f"- ({marks} pt) {point}")
        out.append("")

    traps = rec.get("traps") or []
    if traps:
        out.append("## Traps")
        for t in traps:
            out.append(f"- {t}")
        out.append("")

    final = (rec.get("final_answer") or "").strip()
    if final:
        out.append("## Final answer")
        out.append(final)
        out.append("")

    text = "\n".join(out).rstrip() + "\n"
    return text


# ----------------------------------------------------------------------
# Filtering / record → message conversion
# ----------------------------------------------------------------------


@dataclass
class TrainExample:
    id: str
    source: str
    source_priority: int
    messages: List[dict]
    card_id: Optional[str]
    weight: float = 1.0

    def to_json(self) -> str:
        return json.dumps(
            {
                "id": self.id,
                "source": self.source,
                "source_priority": self.source_priority,
                "messages": self.messages,
                "card_id": self.card_id,
                "weight": self.weight,
            },
            ensure_ascii=False,
        )


def _record_to_example(rec: dict) -> Optional[TrainExample]:
    if not rec.get("solution_steps"):
        return None
    question = (rec.get("question") or "").strip()
    if not question:
        return None
    answer = _render_answer(rec).strip()
    if not answer:
        return None

    card_id: Optional[str] = None
    if triage_record is not None:
        try:
            hits = triage_record(rec, top_k=1)
            if hits:
                card_id = hits[0].card_id
        except Exception:
            card_id = None

    return TrainExample(
        id=rec["id"],
        source=rec["source"],
        source_priority=int(rec.get("source_priority") or 3),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ],
        card_id=card_id,
        weight=1.0,
    )


# ----------------------------------------------------------------------
# Splitting + oversampling
# ----------------------------------------------------------------------

PRIORITY_REPEATS = {1: 3.0, 2: 1.5, 3: 1.0}


def _stratified_split(
    examples: List[TrainExample], rng: random.Random, train: float, val: float
) -> tuple[List[TrainExample], List[TrainExample], List[TrainExample]]:
    """Split examples into train/val/test stratified by ``source``.

    ``train + val + test`` is implicitly ``1.0``. We do NOT round
    individual sources to fixed integer fractions — small sources (e.g.
    crash_course at 25 cards) would otherwise collapse to 0 in val/test.
    Instead we draw uniform-random thresholds per record, the same
    construction used in scikit-learn ShuffleSplit when stratify is on.
    """
    by_src: dict[str, List[TrainExample]] = {}
    for ex in examples:
        by_src.setdefault(ex.source, []).append(ex)

    tr: List[TrainExample] = []
    va: List[TrainExample] = []
    te: List[TrainExample] = []
    for src, items in by_src.items():
        rng.shuffle(items)
        n = len(items)
        n_tr = max(1, int(round(n * train)))
        n_va = max(1, int(round(n * val))) if n >= 4 else 0
        # Test gets the rest (>= 0). For very small sources the
        # remaining-records bucket can be empty; that's acceptable —
        # such sources are evaluated through train+val only.
        if n_tr + n_va > n:
            n_va = max(0, n - n_tr - 1)
        n_te = n - n_tr - n_va
        tr.extend(items[:n_tr])
        va.extend(items[n_tr : n_tr + n_va])
        te.extend(items[n_tr + n_va : n_tr + n_va + n_te])
    rng.shuffle(tr)
    rng.shuffle(va)
    rng.shuffle(te)
    return tr, va, te


def _oversample(
    examples: List[TrainExample], rng: random.Random
) -> List[TrainExample]:
    """Apply integer + fractional oversampling per priority. Returns a new
    list; original ordering is preserved up to the multiplier."""
    out: List[TrainExample] = []
    for ex in examples:
        factor = PRIORITY_REPEATS.get(ex.source_priority, 1.0)
        whole = int(math.floor(factor))
        frac = factor - whole
        for _ in range(whole):
            out.append(ex)
        if frac > 0 and rng.random() < frac:
            out.append(ex)
    rng.shuffle(out)
    return out


# ----------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------


def load_corpus(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def write_jsonl(examples: List[TrainExample], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for ex in examples:
            fh.write(ex.to_json())
            fh.write("\n")


def summarise(label: str, items: List[TrainExample]) -> str:
    if not items:
        return f"{label:>5}: 0 records"
    by_src: dict[str, int] = {}
    by_pri: dict[int, int] = {}
    by_card: dict[str, int] = {}
    for it in items:
        by_src[it.source] = by_src.get(it.source, 0) + 1
        by_pri[it.source_priority] = by_pri.get(it.source_priority, 0) + 1
        if it.card_id:
            by_card[it.card_id] = by_card.get(it.card_id, 0) + 1
    src_str = ", ".join(f"{k}={v}" for k, v in sorted(by_src.items()))
    pri_str = ", ".join(f"p{k}={v}" for k, v in sorted(by_pri.items()))
    return (
        f"{label:>5}: {len(items):4d} records | "
        f"{src_str} | {pri_str} | tagged_cards={len(by_card)}"
    )


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="inp", default=str(DEFAULT_IN))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--seed", type=int, default=4010)
    ap.add_argument("--train", type=float, default=0.90)
    ap.add_argument("--val", type=float, default=0.05)
    ap.add_argument(
        "--no-oversample",
        action="store_true",
        help="skip the priority-weighted oversampling step",
    )
    ap.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="trim to this many input records (smoke-test only)",
    )
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    inp = Path(args.inp)
    out = Path(args.out)
    if not inp.exists():
        print(f"FAIL: corpus not found at {inp}", file=sys.stderr)
        return 2

    print(f"[prep] loading {inp}")
    raw = list(load_corpus(inp))
    if args.max_records is not None:
        raw = raw[: args.max_records]
    print(f"[prep] {len(raw)} raw records")

    examples: List[TrainExample] = []
    skipped = 0
    for r in raw:
        ex = _record_to_example(r)
        if ex is None:
            skipped += 1
            continue
        examples.append(ex)
    print(f"[prep] {len(examples)} usable records ({skipped} skipped — empty solution)")

    train_raw, val, test = _stratified_split(
        examples, rng, train=args.train, val=args.val
    )
    print(f"[prep] split (pre-oversample) {len(train_raw)}/{len(val)}/{len(test)}")

    if args.no_oversample:
        train = train_raw
    else:
        train = _oversample(train_raw, rng)
    print(f"[prep] train after oversample: {len(train)} records")

    write_jsonl(train, out / "train.jsonl")
    write_jsonl(val, out / "val.jsonl")
    write_jsonl(test, out / "test.jsonl")

    print()
    print(summarise("train", train))
    print(summarise("val", val))
    print(summarise("test", test))
    print(f"[prep] wrote {out / 'train.jsonl'}")
    print(f"[prep] wrote {out / 'val.jsonl'}")
    print(f"[prep] wrote {out / 'test.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
