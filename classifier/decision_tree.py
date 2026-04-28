"""Rule-based VE401 question classifier (Phase C — plan §6 step C2/C3).

The taxonomy in ``tag_taxonomy.json`` is the single source of truth: each of
the 25 crash-course test cards owns a list of weighted regex triggers. We sum
the weights of triggers that fire against the input text (negative weights
are anti-triggers) and rank cards by total score.

Public API
----------
classify(text, top_k=3, context="") -> list[ClassifyHit]
    Returns up to ``top_k`` hits (positive scores only) ordered by descending
    score. Cards with score <= 0 are dropped. ``context`` is concatenated
    with the question text before matching — useful for sub-parts whose
    parent question carries the actual setup wording.

The classifier is deliberately small and dependency-free: ``re`` and
``json`` only, so it loads in <1 ms. SymPy / scipy / Qwen are reserved
for downstream stages.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

_TAXONOMY_PATH = Path(__file__).resolve().parent / "tag_taxonomy.json"


@dataclass(frozen=True)
class ClassifyHit:
    card_id: str
    title: str
    chapter: str
    score: int
    confidence: float
    matched: Tuple[Tuple[str, int], ...]

    def as_dict(self) -> dict:
        return {
            "card_id": self.card_id,
            "title": self.title,
            "chapter": self.chapter,
            "score": self.score,
            "confidence": round(self.confidence, 3),
            "matched": [{"label": lbl, "weight": w} for lbl, w in self.matched],
        }


def _load_taxonomy() -> dict:
    with _TAXONOMY_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


_TAXONOMY = _load_taxonomy()


def _compile_patterns(taxonomy: dict) -> List[Tuple[dict, List[Tuple[re.Pattern, int, str]]]]:
    compiled: List[Tuple[dict, List[Tuple[re.Pattern, int, str]]]] = []
    for card in taxonomy["cards"]:
        plist = []
        for p in card["patterns"]:
            rx = re.compile(p["rx"], flags=re.IGNORECASE | re.DOTALL)
            plist.append((rx, int(p["w"]), p.get("label", p["rx"])))
        compiled.append((card, plist))
    return compiled


_COMPILED = _compile_patterns(_TAXONOMY)


def _normalise(text: str) -> str:
    if not text:
        return ""
    # Collapse whitespace; keep punctuation so "σ_1" / "X^TX" still match.
    return re.sub(r"\s+", " ", text)


def classify(
    text: str,
    top_k: int = 3,
    context: str = "",
    *,
    min_score: int = 1,
) -> List[ClassifyHit]:
    """Classify a question into VE401 test cards.

    Parameters
    ----------
    text : str
        The question body. May contain LaTeX or unicode math.
    top_k : int
        Max number of hits to return (positive-scoring only).
    context : str
        Optional prefix (parent question for sub-parts).
    min_score : int
        Drop cards whose total score is below this. Default 1.
    """
    blob = _normalise((context + " \n " + text).strip()) if context else _normalise(text)
    if not blob:
        return []

    raw: List[Tuple[dict, int, List[Tuple[str, int]]]] = []
    for card, patterns in _COMPILED:
        score = 0
        matched: List[Tuple[str, int]] = []
        for rx, w, label in patterns:
            if rx.search(blob):
                score += w
                matched.append((label, w))
        raw.append((card, score, matched))

    # Drop non-positive scores and sort by score desc, ties broken by chapter.
    raw_pos = [r for r in raw if r[1] >= min_score]
    raw_pos.sort(key=lambda r: (-r[1], r[0]["chapter"], r[0]["id"]))

    if not raw_pos:
        return []

    top = raw_pos[0][1]
    out: List[ClassifyHit] = []
    for card, score, matched in raw_pos[:top_k]:
        out.append(
            ClassifyHit(
                card_id=card["id"],
                title=card["title"],
                chapter=card["chapter"],
                score=score,
                confidence=score / top if top > 0 else 0.0,
                matched=tuple(matched),
            )
        )
    return out


def classify_record(record: dict, top_k: int = 3) -> List[ClassifyHit]:
    """Classify a JSONL record from corpus.jsonl. Concatenates `question`
    with rubric / trail-of-thought text where present so we can label
    sub-parts whose body is short."""
    parts: List[str] = []
    if record.get("question"):
        parts.append(str(record["question"]))
    if record.get("trail_of_thought"):
        parts.append(str(record["trail_of_thought"]))
    rubric = record.get("rubric") or []
    for r in rubric:
        if isinstance(r, dict) and r.get("point"):
            parts.append(str(r["point"]))
    return classify(" \n ".join(parts), top_k=top_k)


def all_card_ids() -> List[str]:
    return [c["id"] for c in _TAXONOMY["cards"]]


def card_meta(card_id: str) -> dict | None:
    for c in _TAXONOMY["cards"]:
        if c["id"] == card_id:
            return c
    return None


__all__ = ["ClassifyHit", "classify", "classify_record", "all_card_ids", "card_meta"]
