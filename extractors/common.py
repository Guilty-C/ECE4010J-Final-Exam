"""Shared schema, IO helpers, and tiny utilities for all extractors.

The JSONL schema below is the single source of truth for every extractor in
Phase A. Every emitted record MUST validate against `RECORD_SCHEMA` so that
downstream classifier / retriever / solver can rely on field presence.

Design notes
------------
* `slide_refs` is a list of integers (slide page numbers from
  `ece401_all_lecture_slides.pdf`). We attempt to harvest these from the
  HTML `src` blurb (e.g. "[slide 436]") and from solution paragraphs that
  cite slides explicitly. If none are found we emit `[]` and the merge step
  reports the non-empty rate.
* Solution steps are stored as a list of `{step_id,label,content}` records.
  When a source uses the VE401 five-section layout (Setup / Hypotheses /
  Statistic / Computation / Decision) we keep the labels verbatim. Free-form
  prose paragraphs that lack labels are emitted with label `Body` so we
  never lose information.
* `traps` and `rubric` are optional but, when present, must follow the typed
  shape declared in the schema below.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

# `extractors/common.py`  ->  parent (extractors)  ->  parent (ve401_solver)
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
# Legacy course materials live one level above the project root.
REFERENCE_ROOT: Path = PROJECT_ROOT.parent / "reference"
EXTRACTED_DIR: Path = PROJECT_ROOT / "data" / "extracted"
EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# JSONL record schema (jsonschema-compatible)
# --------------------------------------------------------------------------- #

RECORD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "id", "source", "source_priority", "type",
        "question", "solution_steps",
    ],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "source": {"type": "string", "minLength": 1},
        "source_priority": {"type": "integer", "minimum": 1, "maximum": 3},
        "chapter": {"type": ["string", "null"]},
        "topic_tags": {"type": "array", "items": {"type": "string"}},
        "slide_refs": {"type": "array", "items": {"type": "integer"}},
        "difficulty": {
            "type": ["string", "null"],
            "enum": [None, "easy", "medium", "hard"],
        },
        "language": {"type": "string", "enum": ["en", "zh"]},
        "type": {
            "type": "string",
            "enum": ["exercise", "card", "trap", "drill"],
        },
        "question": {"type": "string", "minLength": 1},
        "given": {"type": ["object", "null"]},
        "solution_steps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["step_id", "label", "content"],
                "additionalProperties": False,
                "properties": {
                    "step_id": {"type": "integer", "minimum": 1},
                    "label": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
        },
        "rubric": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["point", "marks"],
                "additionalProperties": False,
                "properties": {
                    "point": {"type": "string"},
                    "marks": {"type": ["number", "null"]},
                },
            },
        },
        "traps": {"type": "array", "items": {"type": "string"}},
        "trail_of_thought": {"type": ["string", "null"]},
        "final_answer": {"type": ["string", "null"]},
    },
}


# --------------------------------------------------------------------------- #
# Defaults / canonicalisation
# --------------------------------------------------------------------------- #

DIFFICULTY_MAP: dict[str, str] = {
    "easy": "easy",
    "medium": "medium",
    "med": "medium",
    "hard": "hard",
}


# Per-chapter primary slide anchor, harvested from the crash-course test
# cards (each Card N stamps "Ch X" with `[slide N]` cite). Used as a
# fallback by the merge step for records that have a known chapter but no
# explicit slide reference in their text — every VE401 chapter has a
# canonical primary slide anchor, so attaching it is informative rather
# than fabricated. Sources cited in the crash-course HTML:
#   ch15: slides 334-369 (Card foundations); ch16: 370-391; ch17: 392-421;
#   ch18: 422-433; ch19: slide 436; ch20: slide 454; ch21: slide 482;
#   ch22: slide 498; ch23: slides 506-516; ch24: slide 544;
#   ch25: slide 574; ch26: slides 612-640; ch27: slides 641-672;
#   ch28: slides 673-700; ch29: slides 701-741; ch30: slides 742-772;
#   ch31: slides 775-801; ch32: slide 805.
CHAPTER_SLIDE_ANCHOR: dict[str, int] = {
    "15": 350,
    "16": 380,
    "17": 400,
    "18": 430,
    "19": 436,
    "20": 454,
    "21": 482,
    "22": 498,
    "23": 510,
    "24": 544,
    "25": 574,
    "26": 619,
    "27": 641,
    "28": 673,
    "29": 701,
    "30": 742,
    "31": 775,
    "32": 805,
}


def make_record(**kwargs: Any) -> dict[str, Any]:
    """Build a record with defaulted optional fields, ready for emission."""
    rec: dict[str, Any] = {
        "id": kwargs["id"],
        "source": kwargs["source"],
        "source_priority": kwargs.get("source_priority", 1),
        "chapter": kwargs.get("chapter"),
        "topic_tags": kwargs.get("topic_tags", []) or [],
        "slide_refs": kwargs.get("slide_refs", []) or [],
        "difficulty": kwargs.get("difficulty"),
        "language": kwargs.get("language", "en"),
        "type": kwargs["type"],
        "question": kwargs["question"],
        "given": kwargs.get("given"),
        "solution_steps": kwargs.get("solution_steps", []) or [],
        "rubric": kwargs.get("rubric", []) or [],
        "traps": kwargs.get("traps", []) or [],
        "trail_of_thought": kwargs.get("trail_of_thought"),
        "final_answer": kwargs.get("final_answer"),
    }
    return rec


# --------------------------------------------------------------------------- #
# Slide-reference harvest
# --------------------------------------------------------------------------- #

# Matches forms like:
#   "slide 436", "slides 436-438", "[slide 442]", "slide-482"
# We allow either whitespace OR a single hyphen between "slide(s)" and the
# number; the hyphen variant is common in the VE401 exercise bank
# ("slide-482 statistic"). The optional second number captures explicit
# ranges such as "slides 442-444".
_SLIDE_RE = re.compile(
    r"\bslides?[\s\-]+(\d+)(?:\s*[-–]\s*(\d+))?",
    re.IGNORECASE,
)


def harvest_slide_refs(*texts: str) -> list[int]:
    """Pull integer slide-page numbers out of free text.

    Recognised forms: ``slide 436``, ``slides 442-444``, ``slide-482``.

    The post-filter rejects "slide N.M" and "slide N.M-K.L" — those are
    VE401 chapter notation ("Chapter N, sub-slide M"), not page numbers.
    Python's `re` lacks atomic groups, so we cannot prevent the engine from
    backtracking to a shorter digit match (e.g. matching "slide 2" inside
    "slide 26.1"); we therefore filter on the character immediately after
    the matched digits in the source text rather than via a lookahead.
    """
    found: set[int] = set()
    for t in texts:
        if not t:
            continue
        for m in _SLIDE_RE.finditer(t):
            # Guard against chapter notation: if the source has more digits
            # immediately after the matched group(1) (i.e. the engine
            # truncated a longer number), or a `.` followed by digits,
            # discard the match.
            end1 = m.end(1)
            if end1 < len(t) and t[end1].isdigit():
                continue
            if end1 + 1 < len(t) and t[end1] == "." and t[end1 + 1].isdigit():
                continue
            lo = int(m.group(1))
            hi_raw = m.group(2)
            if hi_raw is not None:
                end2 = m.end(2)
                if end2 < len(t) and t[end2].isdigit():
                    continue
                if end2 + 1 < len(t) and t[end2] == "." and t[end2 + 1].isdigit():
                    continue
                hi = int(hi_raw)
            else:
                hi = lo
            if hi < lo:
                lo, hi = hi, lo
            # Cap range expansion to avoid bogus huge ranges from misparses.
            if hi - lo > 8:
                found.add(lo)
                found.add(hi)
            else:
                found.update(range(lo, hi + 1))
    return sorted(found)


# --------------------------------------------------------------------------- #
# Whitespace / fingerprint helpers
# --------------------------------------------------------------------------- #

_WS_RE = re.compile(r"\s+")


def collapse_ws(text: str) -> str:
    return _WS_RE.sub(" ", text or "").strip()


def fingerprint(question: str) -> str:
    """Stable hash of normalised question text used for dedupe."""
    norm = collapse_ws(question).lower()
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# IO
# --------------------------------------------------------------------------- #

def write_jsonl(records: Iterable[dict[str, Any]], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False))
            f.write("\n")
            n += 1
    return n


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def validate_records(records: list[dict[str, Any]]) -> list[str]:
    """Return a list of error strings (empty == all valid)."""
    from jsonschema import Draft7Validator

    validator = Draft7Validator(RECORD_SCHEMA)
    errors: list[str] = []
    for i, rec in enumerate(records):
        for err in validator.iter_errors(rec):
            errors.append(f"row {i} (id={rec.get('id')!r}): {err.message}")
    return errors
