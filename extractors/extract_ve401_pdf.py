"""Extract VE401 problem-set PDFs and the sample-final PDFs.

This extractor is intentionally pragmatic. The source PDFs (built by LaTeX
on a system whose font subset omits proper ToUnicode mappings) emit
literal `(cid:NN)` strings for ligatures (fi, fl, ff) and a handful of
Greek letters. We post-process those after `pdfminer.six` returns text.

For each homework PDF (`ve401_summer21_ex06..10.pdf`) we segment by
"Exercise N.M" headings and emit one record per exercise with
`solution_steps=[]` (homework PDFs do not contain solutions).

For the sample-final pair we segment the question PDF on "Exercise N." and
its sub-parts (i, ii, iii…); for each segment we look up the same
heading in the *_sol.pdf and use the diff between the two as the solution.
That is coarse — `solution_steps[0].content` is the entire matched solution
block — but it is enough to give the retriever something to anchor on.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from pdfminer.high_level import extract_text

from extractors.common import (
    EXTRACTED_DIR,
    REFERENCE_ROOT,
    collapse_ws,
    harvest_slide_refs,
    make_record,
    validate_records,
    write_jsonl,
)

OUTPUT_PATH: Path = EXTRACTED_DIR / "ve401_pdf.jsonl"

HOMEWORK_FILES: list[tuple[str, int]] = [
    ("ve401_summer21_ex06 .pdf", 6),
    ("ve401_summer21_ex07.pdf", 7),
    ("ve401_summer21_ex08.pdf", 8),
    ("ve401_summer21_ex09.pdf", 9),
    ("ve401_summer21_ex10.pdf", 10),
]

SAMPLE_Q = "ve401_sample_final_2021.pdf"
SAMPLE_S = "ve401_sample_final_2021_sol.pdf"


# --------------------------------------------------------------------------- #
# Cleanup
# --------------------------------------------------------------------------- #

# Pdfminer emits these literal markers when ToUnicode info is missing.
_CID_FIXES = {
    "(cid:11)": "α",
    "(cid:12)": "fi",   # most common -> ligature 'fi'
    "(cid:13)": "fl",
    "(cid:14)": "ff",
    "(cid:15)": "ffi",
    "(cid:16)": "ffl",
    "(cid:0)": "-",     # minus
    "(cid:1)": "·",
    "(cid:9)": "\t",
    "(cid:21)": "≤",    # observed in the source
    "(cid:20)": "≥",
    "(cid:18)": "≠",
    "(cid:22)": "μ",
    "(cid:27)": "σ",
    "(cid:23)": "ν",
    "(cid:31)": "λ",
}


def _clean(text: str) -> str:
    for k, v in _CID_FIXES.items():
        text = text.replace(k, v)
    # Drop any remaining (cid:NN) markers — they are non-recoverable here.
    text = re.sub(r"\(cid:\d+\)", "", text)
    return text


# --------------------------------------------------------------------------- #
# Homework segmentation
# --------------------------------------------------------------------------- #

# Headings look like: "Exercise 6.1 Title goes here"
_HW_HEADING_RE = re.compile(
    r"^Exercise\s+(\d+)\.(\d+)\s*(.*)$",
    re.MULTILINE,
)


def _segment_homework(raw: str) -> list[tuple[int, int, str, str]]:
    """Return list of (assignment_number, question_number, title, body)."""
    text = _clean(raw)
    matches = list(_HW_HEADING_RE.finditer(text))
    out: list[tuple[int, int, str, str]] = []
    for i, m in enumerate(matches):
        a = int(m.group(1))
        q = int(m.group(2))
        title = collapse_ws(m.group(3))
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = collapse_ws(text[body_start:body_end])
        out.append((a, q, title, body))
    return out


def extract_homework() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for fname, assignment in HOMEWORK_FILES:
        path = REFERENCE_ROOT / fname
        if not path.exists():
            print(f"[warn] missing input: {path}", file=sys.stderr)
            continue
        raw = extract_text(str(path))
        segs = _segment_homework(raw)
        if not segs:
            print(f"[warn] no exercises segmented from {fname}", file=sys.stderr)
            continue
        for a, q, title, body in segs:
            question_text = body
            if title:
                question_text = f"{title}. {body}" if body else title
            if not question_text:
                continue
            rec = make_record(
                id=f"ve401_local_hw{a:02d}_q{q}",
                source="ve401_local",
                source_priority=1,
                chapter=None,
                topic_tags=["homework"],
                slide_refs=harvest_slide_refs(question_text),
                difficulty=None,
                language="en",
                type="exercise",
                question=question_text,
                solution_steps=[],   # homework solutions not available
            )
            records.append(rec)
    return records


# --------------------------------------------------------------------------- #
# Sample-final segmentation
# --------------------------------------------------------------------------- #

# Heading: "Exercise 1." through "Exercise 9." etc. (up to ~16 typical)
_SF_HEADING_RE = re.compile(r"^Exercise\s+(\d+)\.\s*$", re.MULTILINE)
# Sub-parts inside an Exercise: lines starting with "i)", "ii)", ... "ix)".
_SF_PART_RE = re.compile(
    r"^\s*(i{1,3}|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv)\)\s",
    re.MULTILINE | re.IGNORECASE,
)


def _segment_sample_final(raw: str) -> list[tuple[int, str | None, str]]:
    """Return list of (exercise_num, part_label or None, body_text).

    Each Exercise gets one entry for its preamble (part_label=None) plus one
    entry per (i)/(ii)/... sub-part. If an Exercise has no sub-parts we
    emit a single entry with part_label=None and the full body.
    """
    text = _clean(raw)
    headings = list(_SF_HEADING_RE.finditer(text))
    if not headings:
        return []

    out: list[tuple[int, str | None, str]] = []
    for i, m in enumerate(headings):
        ex_num = int(m.group(1))
        body_start = m.end()
        body_end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        chunk = text[body_start:body_end]
        parts = list(_SF_PART_RE.finditer(chunk))
        if not parts:
            body = collapse_ws(chunk)
            if body:
                out.append((ex_num, None, body))
            continue

        # Preamble = text before the first part marker, if any.
        preamble = collapse_ws(chunk[: parts[0].start()])
        if preamble:
            out.append((ex_num, None, preamble))
        for j, p in enumerate(parts):
            label = p.group(1).lower()
            p_start = p.end()
            p_end = parts[j + 1].start() if j + 1 < len(parts) else len(chunk)
            body = collapse_ws(chunk[p_start:p_end])
            if body:
                out.append((ex_num, label, body))
    return out


def extract_sample_final() -> list[dict[str, Any]]:
    q_path = REFERENCE_ROOT / SAMPLE_Q
    s_path = REFERENCE_ROOT / SAMPLE_S
    if not q_path.exists() or not s_path.exists():
        print(f"[warn] sample-final pair missing: {q_path}, {s_path}",
              file=sys.stderr)
        return []
    q_raw = extract_text(str(q_path))
    s_raw = extract_text(str(s_path))
    q_segs = _segment_sample_final(q_raw)
    s_segs = _segment_sample_final(s_raw)

    # Build (ex, part) -> body dict for solutions.
    s_index: dict[tuple[int, str | None], str] = {}
    for ex, part, body in s_segs:
        s_index[(ex, part)] = body

    records: list[dict[str, Any]] = []
    for ex, part, q_body in q_segs:
        sol_body = s_index.get((ex, part), "")
        # Coarse "solution diff" is just the difference in length and the
        # solution body text. We keep it whole; downstream renderer can
        # truncate. If the question body equals the solution body, we treat
        # it as solution-absent.
        steps: list[dict[str, Any]] = []
        if sol_body and sol_body != q_body:
            steps.append({"step_id": 1, "label": "Solution", "content": sol_body})

        part_suffix = f"_part_{part}" if part else ""
        rec_id = f"ve401_local_samplefinal_q{ex}{part_suffix}"
        rec = make_record(
            id=rec_id,
            source="ve401_local",
            source_priority=1,
            chapter=None,
            topic_tags=["sample-final-2021"],
            slide_refs=harvest_slide_refs(q_body + " " + sol_body),
            difficulty=None,
            language="en",
            type="exercise",
            question=q_body,
            solution_steps=steps,
        )
        records.append(rec)
    return records


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

def main() -> int:
    hw = extract_homework()
    sf = extract_sample_final()
    all_records = hw + sf

    errs = validate_records(all_records)
    if errs:
        print("[error] schema validation failed:", file=sys.stderr)
        for e in errs[:20]:
            print("  -", e, file=sys.stderr)
        if len(errs) > 20:
            print(f"  ... and {len(errs) - 20} more", file=sys.stderr)
        return 1

    n = write_jsonl(all_records, OUTPUT_PATH)
    print(f"[ok] wrote {n} records to {OUTPUT_PATH}")
    print(f"     homework: {len(hw)}")
    print(f"     sample-final: {len(sf)}")
    with_sol = sum(1 for r in all_records if r["solution_steps"])
    print(f"     with-solution: {with_sol}/{n}")
    non_empty_slides = sum(1 for r in all_records if r["slide_refs"])
    print(f"     slide_refs non-empty: {non_empty_slides}/{n}"
          f" ({non_empty_slides / max(n,1):.0%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
