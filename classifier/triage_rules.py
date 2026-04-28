"""Triage rules that map raw question wording to candidate test cards.

This module is the public "triage from question wording" entry point named in
plan §6 step C2 — it is a thin facade over :mod:`decision_tree`, which holds
the concrete scoring engine and reads ``tag_taxonomy.json``. They are kept
in separate modules so callers can swap in a different scoring backend
later without rewriting upstream code.
"""
from __future__ import annotations

from typing import List

from classifier.decision_tree import (
    ClassifyHit,
    classify as _classify,
    classify_record as _classify_record,
)


def triage(text: str, top_k: int = 3, context: str = "") -> List[ClassifyHit]:
    """Triage a single question's wording into ranked test-card hits."""
    return _classify(text, top_k=top_k, context=context)


def triage_record(record: dict, top_k: int = 3) -> List[ClassifyHit]:
    """Triage a JSONL corpus record (uses question + rubric + trail)."""
    return _classify_record(record, top_k=top_k)


__all__ = ["triage", "triage_record", "ClassifyHit"]
