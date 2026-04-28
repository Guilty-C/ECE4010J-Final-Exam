"""Extract end-of-section exercises from OpenStax Introductory Statistics 2e
into ``data/extracted/openstax.jsonl``.

Source tree
-----------
``data/raw/openstax/osbooks-introductory-statistics-bundle-main/`` is the
codeload-zipped ``openstax/osbooks-introductory-statistics-bundle`` repo.
It contains both ``Introductory Statistics 2e`` and the business-stats
sibling. We only walk the former — the plan §2.2 names that book.

Two file families matter:

* ``collections/introductory-statistics-2e.collection.xml`` — a CNX
  ``<col:collection>`` that nests ``<col:module document="m4XXXX"/>``
  pointers under ``<col:subcollection><md:title>Chapter Name</md:title>``.
  We read this once to build a ``module_id → chapter_title`` map.

* ``modules/m4XXXX/index.cnxml`` — one CNXML document per section. Each
  exercise sits in:

  ```xml
  <exercise id="...">
    <problem id="..."> <para>...</para> ...</problem>
    <solution id="..."> <para>...</para></solution>   <!-- often absent -->
  </exercise>
  ```

  Most modules ship without ``<solution>`` elements (answers live in a
  separate "Practice / Homework / Solutions" companion module). We emit
  the problem text either way and surface the solution if present.

Why we use ElementTree, not regex
---------------------------------
The CNXML body has two namespaces (``cnx`` and ``mathml``), nested
``<para>``, ``<list>``, ``<emphasis>``, and inline ``<m:math>``. A regex
would either lose math content or mis-balance tags. ``xml.etree`` is in
the stdlib, so this stays dependency-light.

Schema mapping
--------------
* ``id``  = ``openstax_<module_id>_<idx>`` where ``idx`` is the 1-based
  exercise index inside the module.
* ``source_priority`` = 2.
* ``chapter`` = the OpenStax chapter slug derived from the collection
  subcollection title (lowercased, hyphenated; e.g.
  ``hypothesis-testing-with-one-sample``).
* ``topic_tags`` = derived from the chapter slug via ``_CHAPTER_TAGS``.
* ``solution_steps`` = single-step "Solution" record if a ``<solution>``
  element was present; empty list otherwise.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from extractors.common import (
    EXTRACTED_DIR,
    PROJECT_ROOT,
    collapse_ws,
    make_record,
    validate_records,
    write_jsonl,
)


REPO_ROOT: Path = (
    PROJECT_ROOT / "data" / "raw" / "openstax"
    / "osbooks-introductory-statistics-bundle-main"
)
COLLECTION_PATH: Path = (
    REPO_ROOT / "collections" / "introductory-statistics-2e.collection.xml"
)
MODULES_DIR: Path = REPO_ROOT / "modules"
OUTPUT_PATH: Path = EXTRACTED_DIR / "openstax.jsonl"


# CNXML namespace map. ``cnx`` is the document body, ``md`` is the
# metadata vocabulary, ``col`` is the collection vocabulary, ``m`` is
# MathML inside the body. We register them so XPath queries like
# ``cnx:exercise`` resolve cleanly.
_NS = {
    "cnx": "http://cnx.rice.edu/cnxml",
    "md":  "http://cnx.rice.edu/mdml",
    "col": "http://cnx.rice.edu/collxml",
    "m":   "http://www.w3.org/1998/Math/MathML",
}


# Chapter-slug → topic tags. Keys are chapter titles after slugify
# (lowercase, hyphens). Values are VE401-aligned tag tokens.
_CHAPTER_TAGS: dict[str, list[str]] = {
    "sampling-and-data": ["intro-data", "study-design"],
    "descriptive-statistics": ["descriptive-stats"],
    "probability-topics": ["probability"],
    "discrete-random-variables": ["distributions", "binomial", "poisson"],
    "continuous-random-variables": ["distributions", "continuous"],
    "the-normal-distribution": ["distributions", "normal"],
    "the-central-limit-theorem": ["sampling-distribution", "clt"],
    "confidence-intervals": ["ci", "one-sample-Z", "one-sample-T"],
    "hypothesis-testing-with-one-sample": ["test", "one-sample-Z", "one-sample-T"],
    "hypothesis-testing-with-two-samples": ["test", "two-sample-Z", "two-sample-T", "paired-T"],
    "the-chi-square-distribution": ["chi2-gof", "chi2-independence", "chi2-homogeneity"],
    "linear-regression-and-correlation": ["SLR", "correlation-rho", "SLR-CI", "SLR-PI"],
    "f-distribution-and-one-way-anova": ["F-test-variances", "one-way-ANOVA"],
}


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(title: str) -> str:
    """Lowercase, hyphenate. ``"Hypothesis Testing With One Sample"`` →
    ``"hypothesis-testing-with-one-sample"``."""
    s = _SLUG_RE.sub("-", title.lower()).strip("-")
    return s


def _build_module_chapter_map(coll_path: Path) -> dict[str, str]:
    """Walk the collection XML and map each module id → chapter slug.

    Subcollections nest two levels deep in this book: the outer
    subcollection is the chapter ("Sampling and Data"), and any inner
    subcollections (rare) are sub-sections — we still attribute their
    modules to the outermost chapter.
    """
    tree = ET.parse(coll_path)
    root = tree.getroot()
    out: dict[str, str] = {}

    def _walk(node: ET.Element, current_chapter: str | None) -> None:
        for child in node:
            tag = child.tag.split("}", 1)[-1]
            if tag == "subcollection":
                title_el = child.find("md:title", _NS)
                title = title_el.text if title_el is not None else ""
                next_chapter = _slugify(title or "") or current_chapter
                content_el = child.find("col:content", _NS)
                if content_el is not None:
                    _walk(content_el, next_chapter)
            elif tag == "module":
                mid = child.attrib.get("document")
                if mid and current_chapter:
                    out[mid] = current_chapter
            elif tag == "content":
                _walk(child, current_chapter)

    top = root.find("col:content", _NS)
    if top is not None:
        _walk(top, None)
    return out


def _element_text(el: ET.Element) -> str:
    """Flatten an element subtree to whitespace-collapsed plain text.

    We deliberately drop MathML (it's hostile to plain-text indexing and
    the surrounding prose carries enough signal for retrieval).
    Everything else is concatenated in document order.

    Empty self-closing ``<link target-id="..." />`` tags are replaced
    with ``[Table/Figure]`` — without that substitution, sentences like
    "From <link.../>, find the percentage" come out as "From , find …"
    which is grammatically ill-formed and confuses downstream tokenisers.
    """
    if el.tag.endswith("}math"):
        return ""  # drop MathML; surrounding prose is enough
    if el.tag.endswith("}link") and el.text is None and len(list(el)) == 0:
        # Empty cross-reference (target-id pointer with no display text).
        # Inserting "[Table/Figure]" keeps surrounding prose readable.
        tail = el.tail or ""
        return f"[Table/Figure]{tail}"
    parts: list[str] = []
    if el.text:
        parts.append(el.text)
    for child in el:
        parts.append(_element_text(child))
        if child.tail:
            parts.append(child.tail)
    return " ".join(p for p in parts if p)


def _walk_exercises(module_path: Path) -> list[tuple[str, str | None]]:
    """Return ``(problem_text, solution_text or None)`` per exercise."""
    try:
        tree = ET.parse(module_path)
    except ET.ParseError as exc:
        print(f"[warn] parse error in {module_path}: {exc}", file=sys.stderr)
        return []
    root = tree.getroot()

    out: list[tuple[str, str | None]] = []
    # Use iter() so we catch exercises at any nesting depth.
    for ex in root.iter("{http://cnx.rice.edu/cnxml}exercise"):
        problem_el = ex.find("cnx:problem", _NS)
        if problem_el is None:
            continue
        problem_text = collapse_ws(_element_text(problem_el))
        if len(problem_text) < 20:
            continue
        sol_el = ex.find("cnx:solution", _NS)
        sol_text: str | None = None
        if sol_el is not None:
            sol_text = collapse_ws(_element_text(sol_el)) or None
        out.append((problem_text, sol_text))
    return out


def main() -> int:
    if not COLLECTION_PATH.is_file():
        print(f"[error] missing collection: {COLLECTION_PATH}", file=sys.stderr)
        return 1
    if not MODULES_DIR.is_dir():
        print(f"[error] missing modules dir: {MODULES_DIR}", file=sys.stderr)
        return 1

    module_to_chapter = _build_module_chapter_map(COLLECTION_PATH)
    print(f"[info] collection maps {len(module_to_chapter)} modules → chapters")

    records: list[dict[str, Any]] = []
    n_modules = 0
    n_with_solutions = 0
    for mid, chapter_slug in sorted(module_to_chapter.items()):
        path = MODULES_DIR / mid / "index.cnxml"
        if not path.is_file():
            # Some collection entries point to modules that aren't
            # checked in (rare; the bundle is a snapshot). Skip silently.
            continue
        n_modules += 1
        tags = _CHAPTER_TAGS.get(chapter_slug, [])
        for n, (qtxt, stxt) in enumerate(_walk_exercises(path), start=1):
            steps: list[dict[str, Any]] = []
            if stxt:
                steps.append({
                    "step_id": 1,
                    "label": "Solution",
                    "content": stxt,
                })
                n_with_solutions += 1
            rec = make_record(
                id=f"openstax_{mid}_{n:03d}",
                source="openstax",
                source_priority=2,
                chapter=chapter_slug,
                topic_tags=list(tags),
                slide_refs=[],
                difficulty=None,
                language="en",
                type="exercise",
                question=qtxt,
                given=None,
                solution_steps=steps,
                rubric=[],
                traps=[],
                trail_of_thought=None,
                final_answer=None,
            )
            records.append(rec)

    print(f"[info] visited {n_modules} modules; emitted {len(records)} records "
          f"({n_with_solutions} with solutions)")

    errs = validate_records(records)
    if errs:
        print("[error] schema validation failed:", file=sys.stderr)
        for e in errs[:10]:
            print("  -", e, file=sys.stderr)
        return 2

    n = write_jsonl(records, OUTPUT_PATH)
    print(f"[ok] wrote {n} records to {OUTPUT_PATH}")

    by_chapter: dict[str, int] = {}
    by_tagcount: dict[int, int] = {}
    for r in records:
        ch = r["chapter"] or "—"
        by_chapter[ch] = by_chapter.get(ch, 0) + 1
        by_tagcount[len(r["topic_tags"])] = by_tagcount.get(len(r["topic_tags"]), 0) + 1
    print(f"     by chapter: {dict(sorted(by_chapter.items()))}")
    print(f"     by tagcount: {dict(sorted(by_tagcount.items()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
