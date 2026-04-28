"""Extract crash_course_ch15_32.html → crash_course.jsonl.

Three entity families are pulled out:

* **Test cards** (`<div class="card" id="...">` whose `<h4 class="cardtitle">`
  matches `Card N — Title`). 25 cards, each anchored to a chapter via the
  `<span class="badge tag">Ch X</span>` and to slides via `<span class="cite">`.
  Stored with `type="card"`.

* **Traps** (`<details class="trap">`). 30 of them; the summary is the trap
  title, the body is the diagnostic + remedy. Stored with `type="trap"`.

* **Drills** (`<div class="drill">`). 13 short worked exercises. Each has a
  stem and a `<details>`-wrapped solution body. Stored with `type="drill"`.

Output: data/extracted/crash_course.jsonl
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag

from extractors.common import (
    EXTRACTED_DIR,
    REFERENCE_ROOT,
    collapse_ws,
    harvest_slide_refs,
    make_record,
    validate_records,
    write_jsonl,
)

INPUT_PATH: Path = REFERENCE_ROOT / "crash_course_ch15_32.html"
OUTPUT_PATH: Path = EXTRACTED_DIR / "crash_course.jsonl"

_CARD_NUM_RE = re.compile(r"Card\s+(\d+)\s*[—–\-]", re.IGNORECASE)
_CH_RE = re.compile(r"Ch\s*(\d+)", re.IGNORECASE)
_TRAP_NUM_RE = re.compile(r"^T\s*(\d+)\.?\s*(.*)$", re.IGNORECASE)


def _txt(node: Tag | None) -> str:
    if node is None:
        return ""
    return collapse_ws(node.get_text(" "))


# --------------------------------------------------------------------------- #
# Test cards
# --------------------------------------------------------------------------- #

def _extract_card(card_div: Tag) -> dict[str, Any] | None:
    title = card_div.find("h4", class_="cardtitle")
    if title is None:
        return None
    title_text = _txt(title)
    m = _CARD_NUM_RE.search(title_text)
    if m is None:
        # Some `<div class="card">` blocks (e.g. ch15 prerequisite cards)
        # don't follow the "Card N — ..." convention; skip them so we keep
        # exactly the 25-card crash-course set.
        return None
    card_num = int(m.group(1))

    # Chapter badge (free-form: may say "Ch 24/27", just take the first int).
    chapter: str | None = None
    chap_badge = title.find("span", class_="badge")
    if chap_badge is not None:
        cm = _CH_RE.search(_txt(chap_badge))
        if cm:
            chapter = cm.group(1)

    cite = title.find("span", class_="cite")
    cite_text = _txt(cite) if cite else ""
    slide_refs = harvest_slide_refs(cite_text)

    # Question = the title proper (strip badges + cite for cleanliness).
    bare_title = title_text
    if chap_badge:
        bare_title = bare_title.replace(_txt(chap_badge), "")
    if cite:
        bare_title = bare_title.replace(cite_text, "")
    bare_title = collapse_ws(bare_title)

    # Body = every other element inside the card div, with the title removed.
    title.extract()  # mutate the parsed tree only locally
    body_text = collapse_ws(card_div.get_text(" "))

    solution_steps = [
        {"step_id": 1, "label": "Recipe", "content": body_text or bare_title},
    ]

    rec = make_record(
        id=f"crash_course_card{card_num:02d}",
        source="crash_course",
        source_priority=1,
        chapter=chapter,
        topic_tags=[bare_title],
        slide_refs=slide_refs,
        difficulty=None,
        language="en",
        type="card",
        question=bare_title,
        solution_steps=solution_steps,
    )
    return rec


# --------------------------------------------------------------------------- #
# Traps
# --------------------------------------------------------------------------- #

def _extract_trap(trap_details: Tag) -> dict[str, Any] | None:
    summary = trap_details.find("summary")
    if summary is None:
        return None
    title = _txt(summary)
    m = _TRAP_NUM_RE.match(title)
    if m is None:
        return None
    trap_num = int(m.group(1))
    headline = collapse_ws(m.group(2))

    body = trap_details.find("div", class_="body")
    body_text = _txt(body) if body else ""
    slide_refs = harvest_slide_refs(headline + " " + body_text)

    rec = make_record(
        id=f"crash_course_trap{trap_num:02d}",
        source="crash_course",
        source_priority=1,
        chapter=None,
        topic_tags=["trap"],
        slide_refs=slide_refs,
        difficulty=None,
        language="en",
        type="trap",
        question=f"T{trap_num}. {headline}",
        solution_steps=[
            {"step_id": 1, "label": "Diagnostic+Remedy", "content": body_text},
        ],
    )
    return rec


# --------------------------------------------------------------------------- #
# Drills
# --------------------------------------------------------------------------- #

_PTAG_RE = re.compile(r"^([A-Z]\d+)\b")


def _extract_drill(drill_div: Tag) -> dict[str, Any] | None:
    stem = drill_div.find("div", class_="stem")
    if stem is None:
        return None
    ptag_b = stem.find("b", class_="ptag")
    ptag = _txt(ptag_b) if ptag_b else ""
    if not _PTAG_RE.match(ptag):
        return None
    # Question = stem text minus the ptag prefix.
    full_stem = _txt(stem)
    question = full_stem
    if ptag and full_stem.startswith(ptag):
        question = collapse_ws(full_stem[len(ptag):])

    # Solution lives inside the inner `<details>` -> `<div class="body">`.
    details = drill_div.find("details")
    body = details.find("div", class_="body") if details else None

    solution_steps: list[dict[str, Any]] = []
    rubric: list[dict[str, Any]] = []
    thought: str | None = None
    if body is not None:
        # Pull rubric and thought sub-blocks first.
        rubric_div = body.find("div", class_="rubric")
        if rubric_div is not None:
            for li in rubric_div.find_all("li"):
                t = _txt(li)
                if t:
                    rubric.append({"point": t, "marks": None})
            rubric_div.extract()
        thought_div = body.find("div", class_="thought")
        if thought_div is not None:
            # remove the label span
            for label in thought_div.select("span.label"):
                label.extract()
            thought = _txt(thought_div) or None
            thought_div.extract()
        body_text = _txt(body)
        if body_text:
            solution_steps.append(
                {"step_id": 1, "label": "Solution", "content": body_text}
            )

    slide_refs = harvest_slide_refs(
        " ".join(
            [
                question,
                " ".join(s["content"] for s in solution_steps),
                " ".join(r["point"] for r in rubric),
                thought or "",
            ]
        )
    )

    rec = make_record(
        id=f"crash_course_drill_{ptag}",
        source="crash_course",
        source_priority=1,
        chapter=None,
        topic_tags=["drill"],
        slide_refs=slide_refs,
        difficulty=None,
        language="en",
        type="drill",
        question=question,
        solution_steps=solution_steps,
        rubric=rubric,
        trail_of_thought=thought,
    )
    return rec


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

def main() -> int:
    if not INPUT_PATH.exists():
        print(f"[error] missing input: {INPUT_PATH}", file=sys.stderr)
        return 1

    soup = BeautifulSoup(INPUT_PATH.read_text(encoding="utf-8"), "lxml")

    cards = [r for c in soup.select("div.card") if (r := _extract_card(c))]
    traps = [r for t in soup.select("details.trap") if (r := _extract_trap(t))]
    drills = [r for d in soup.select("div.drill") if (r := _extract_drill(d))]

    all_records = cards + traps + drills

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
    print(f"     cards: {len(cards)}, traps: {len(traps)}, drills: {len(drills)}")
    non_empty_slides = sum(1 for r in all_records if r["slide_refs"])
    print(f"     slide_refs non-empty: {non_empty_slides}/{n}"
          f" ({non_empty_slides / max(n,1):.0%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
