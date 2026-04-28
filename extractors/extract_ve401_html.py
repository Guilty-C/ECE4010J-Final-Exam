"""Extract VE401 exercise-bank HTML files into the unified JSONL schema.

Inputs (under `<repo>/reference/`):
    exercises_ch19_20_21.html
    exercises_ch22_23_24.html
    exercises_ch25.html
    exercises_ch26_27_28_29_30.html

Output:
    data/extracted/ve401_local.jsonl

Each `<article class="card">` becomes one JSONL row. The chapter is read
from the enclosing `<section id="chXX">`. Difficulty/tags come from the
`badge` spans, the question from `div.problem`, and the solution body is
flattened into ordered `solution_steps`. Inline LaTeX (`\(...\)`, `\[...\]`)
is preserved verbatim — BeautifulSoup's `get_text()` keeps the raw text.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag, NavigableString

from extractors.common import (
    DIFFICULTY_MAP,
    EXTRACTED_DIR,
    REFERENCE_ROOT,
    collapse_ws,
    harvest_slide_refs,
    make_record,
    validate_records,
    write_jsonl,
)

# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #

HTML_FILES: list[str] = [
    "exercises_ch19_20_21.html",
    "exercises_ch22_23_24.html",
    "exercises_ch25.html",
    "exercises_ch26_27_28_29_30.html",
]

OUTPUT_PATH: Path = EXTRACTED_DIR / "ve401_local.jsonl"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

# Card ID looks like: "Ch 19 — Q1" (with an mdash). Be permissive about dashes.
_CARDID_RE = re.compile(
    r"Ch\s*(?P<ch>\d+)\s*[—–\-‒―]+\s*Q\s*(?P<q>\d+)",
    re.IGNORECASE,
)

# Match marks like "— 2 pts", "(2 pts)", "2 pt", "1 pt".
_MARKS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*pt", re.IGNORECASE)


def _txt(node: Tag | NavigableString | None) -> str:
    """Return collapsed text of an element (LaTeX kept verbatim)."""
    if node is None:
        return ""
    if isinstance(node, NavigableString):
        return collapse_ws(str(node))
    return collapse_ws(node.get_text(" "))


def _parse_card_id(raw: str) -> tuple[str | None, int | None]:
    m = _CARDID_RE.search(raw)
    if not m:
        return None, None
    return m.group("ch"), int(m.group("q"))


def _parse_badges(card_head: Tag) -> tuple[str | None, list[str]]:
    difficulty: str | None = None
    tags: list[str] = []
    for span in card_head.select("span.badge"):
        classes = set(span.get("class") or [])
        text = _txt(span)
        # Difficulty badges have class easy/med/hard *and not* "tag".
        if "tag" in classes:
            tags.append(text)
            continue
        for k in ("easy", "med", "hard"):
            if k in classes:
                difficulty = DIFFICULTY_MAP[k]
                break
        else:
            # No difficulty class but no "tag" class either — treat as a tag.
            if text:
                tags.append(text)
    return difficulty, tags


def _split_labelled_paragraph(p: Tag) -> tuple[str, str]:
    """If `<p>` starts with `<b>Label.</b> rest...`, return (label, rest).

    Otherwise return ("", full text).
    """
    children = list(p.children)
    # Find the first non-whitespace child.
    first: Tag | NavigableString | None = None
    rest_idx = 0
    for i, c in enumerate(children):
        if isinstance(c, NavigableString) and not str(c).strip():
            continue
        first = c
        rest_idx = i + 1
        break
    if first is None:
        return "", _txt(p)
    if isinstance(first, Tag) and first.name == "b":
        label_raw = _txt(first).rstrip(".:")
        # Grab the remaining children's text.
        rest_parts = []
        for c in children[rest_idx:]:
            rest_parts.append(_txt(c))
        rest = collapse_ws(" ".join(part for part in rest_parts if part))
        return label_raw, rest
    return "", _txt(p)


def _table_to_text(tbl: Tag) -> str:
    """Render a `<table>` as a compact pipe-separated text block."""
    rows: list[str] = []
    for tr in tbl.find_all("tr"):
        cells = [_txt(td) for td in tr.find_all(["th", "td"])]
        rows.append(" | ".join(cells))
    return " ; ".join(r for r in rows if r)


def _extract_solution_steps(soln_body: Tag) -> list[dict[str, Any]]:
    """Walk children of `div.soln-body` and emit ordered solution steps.

    Skips the rubric / thought subtrees — those are extracted separately.
    """
    steps: list[dict[str, Any]] = []
    step_id = 1
    for child in soln_body.children:
        if isinstance(child, NavigableString):
            text = collapse_ws(str(child))
            if text:
                steps.append({"step_id": step_id, "label": "Body", "content": text})
                step_id += 1
            continue
        if not isinstance(child, Tag):
            continue
        classes = set(child.get("class") or [])
        if child.name == "div" and ({"rubric", "thought"} & classes):
            # Handled outside.
            continue
        if child.name == "p":
            label, content = _split_labelled_paragraph(child)
            label = label or "Body"
            content = content if content else _txt(child)
            if content:
                steps.append({"step_id": step_id, "label": label, "content": content})
                step_id += 1
        elif child.name == "table":
            txt = _table_to_text(child)
            if txt:
                steps.append({"step_id": step_id, "label": "Table", "content": txt})
                step_id += 1
        elif child.name in ("ol", "ul"):
            items = [_txt(li) for li in child.find_all("li", recursive=False)]
            items = [it for it in items if it]
            if items:
                steps.append({
                    "step_id": step_id,
                    "label": "List",
                    "content": " | ".join(items),
                })
                step_id += 1
        elif child.name == "div" and "soln-body" not in classes:
            # Generic nested div — fall back to flat text.
            txt = _txt(child)
            if txt:
                steps.append({"step_id": step_id, "label": "Body", "content": txt})
                step_id += 1
        else:
            txt = _txt(child)
            if txt:
                steps.append({"step_id": step_id, "label": "Body", "content": txt})
                step_id += 1
    return steps


def _extract_rubric(soln_body: Tag) -> list[dict[str, Any]]:
    rubric_div = soln_body.find("div", class_="rubric", recursive=False)
    if rubric_div is None:
        # Sometimes nested deeper; do a fuller search inside soln-body only.
        rubric_div = soln_body.find("div", class_="rubric")
    if rubric_div is None:
        return []
    items: list[dict[str, Any]] = []
    for li in rubric_div.find_all("li"):
        text = _txt(li)
        if not text:
            continue
        marks: float | None = None
        m = _MARKS_RE.search(text)
        if m:
            try:
                marks = float(m.group(1))
            except ValueError:
                marks = None
        items.append({"point": text, "marks": marks})
    return items


def _extract_thought(soln_body: Tag) -> str | None:
    div = soln_body.find("div", class_="thought")
    if div is None:
        return None
    # Drop the "label" span (e.g. "Trail of thought ...") prefix.
    for label in div.select("span.label"):
        label.extract()
    text = _txt(div)
    return text or None


# --------------------------------------------------------------------------- #
# Per-card extractor
# --------------------------------------------------------------------------- #

def extract_card(card: Tag, *, source_file: str) -> dict[str, Any] | None:
    head = card.find("div", class_="card-head")
    if head is None:
        return None
    card_id_div = head.find("div", class_="card-id")
    if card_id_div is None:
        return None
    chapter, qnum = _parse_card_id(_txt(card_id_div))
    if chapter is None or qnum is None:
        return None

    difficulty, tags = _parse_badges(head)
    src_div = card.find("div", class_="src")
    src_text = _txt(src_div) if src_div else ""
    problem_div = card.find("div", class_="problem")
    if problem_div is None:
        return None
    question = _txt(problem_div)
    if not question:
        return None

    solution_steps: list[dict[str, Any]] = []
    rubric: list[dict[str, Any]] = []
    thought: str | None = None
    soln_body = card.find("div", class_="soln-body")
    if soln_body is not None:
        # Extract rubric/thought first (they are children of soln-body), then
        # produce steps with those subtrees ignored.
        rubric = _extract_rubric(soln_body)
        thought = _extract_thought(soln_body)
        solution_steps = _extract_solution_steps(soln_body)

    # Slide-ref harvest from src + every solution paragraph + every rubric
    # item + thought. Rubric items frequently cite the slide that justifies
    # the grading point (e.g. "Cite slide 552: ..."), so they are a
    # meaningful contributor to coverage.
    slide_text = " ".join(
        [
            src_text,
            " ".join(s["content"] for s in solution_steps),
            " ".join(item["point"] for item in rubric),
            thought or "",
        ]
    )
    slide_refs = harvest_slide_refs(slide_text)

    rec = make_record(
        id=f"ve401_local_ch{chapter}_q{qnum}",
        source="ve401_local",
        source_priority=1,
        chapter=str(chapter),
        topic_tags=tags,
        slide_refs=slide_refs,
        difficulty=difficulty,
        language="en",
        type="exercise",
        question=question,
        solution_steps=solution_steps,
        rubric=rubric,
        trail_of_thought=thought,
        # Provenance is encoded in `source` + the deterministic `id`.
        # `src_text` is preserved as the trailing comment in `final_answer` only
        # when it carries useful info (rare); for now leave final_answer None
        # because the explicit "Decision/Interpretation" step already captures it.
    )
    return rec


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

def extract_file(path: Path) -> list[dict[str, Any]]:
    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, Any]] = []
    for card in soup.select("article.card"):
        rec = extract_card(card, source_file=path.name)
        if rec is not None:
            out.append(rec)
    return out


def main() -> int:
    all_records: list[dict[str, Any]] = []
    per_file_counts: list[tuple[str, int]] = []
    for fname in HTML_FILES:
        path = REFERENCE_ROOT / fname
        if not path.exists():
            print(f"[warn] missing input: {path}", file=sys.stderr)
            continue
        recs = extract_file(path)
        per_file_counts.append((fname, len(recs)))
        all_records.extend(recs)

    # Validate before writing.
    errs = validate_records(all_records)
    if errs:
        print("[error] schema validation failed for the following rows:", file=sys.stderr)
        for e in errs[:20]:
            print("  -", e, file=sys.stderr)
        if len(errs) > 20:
            print(f"  ... and {len(errs) - 20} more", file=sys.stderr)
        return 1

    n = write_jsonl(all_records, OUTPUT_PATH)
    print(f"[ok] wrote {n} records to {OUTPUT_PATH}")
    for fname, count in per_file_counts:
        print(f"     {fname}: {count}")
    non_empty_slides = sum(1 for r in all_records if r["slide_refs"])
    print(f"     slide_refs non-empty: {non_empty_slides}/{n}"
          f" ({non_empty_slides / max(n,1):.0%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
