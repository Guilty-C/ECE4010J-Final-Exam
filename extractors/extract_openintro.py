"""Extract end-of-chapter exercises from the OpenIntro Statistics 4e LaTeX
source tree into ``data/extracted/openintro.jsonl``.

Source tree
-----------
``data/raw/openintro/openintro-statistics-master/`` is the (codeload-zipped)
``OpenIntroStat/openintro-statistics`` GitHub repository at HEAD of the
``master`` branch. Each chapter has its own directory ``ch_*/TeX/*.tex``.
Inside each section file every exercise is wrapped in:

```latex
\\eoce{
  \\qt{Title\\label{slug}}  % optional title with anchor label
  Question body, possibly with \\begin{parts}…\\end{parts}.
}{
  Optional second arg — empty in 4e since the public source ships
  problems only; the solution manual is sold separately.
}
```

Solutions are NOT in this repo (the published "Solution Manual" is sold
through OpenIntro's store), so every emitted record has empty
``solution_steps``. These records still earn their keep:

* They give the classifier and tag taxonomy a much wider variety of
  question phrasings (≈ 600 problems) than the VE401 local corpus alone.
* They're tagged by chapter via the file-path mapping in
  ``_PATH_TO_TAGS`` so the retriever can score them under the right
  topic bucket.

Schema mapping
--------------
* ``id``  = ``openintro_<chapter_slug>_<file_slug>_<n>`` where ``n`` is
  the per-file 1-based exercise index.
* ``source_priority`` = 2 (between VE401 local and Hendrycks).
* ``chapter`` = OpenIntro chapter name (string slug, NOT a VE401 chapter
  number — they don't align).
* ``topic_tags`` = derived from the parent ``ch_*/TeX/<file>.tex`` path
  via ``_PATH_TO_TAGS`` (see table below).
* ``language`` = "en".
* ``type`` = "exercise".

Why a custom brace matcher
--------------------------
The body of ``\\eoce{...}`` contains arbitrary LaTeX, including
``\\begin{parts}`` blocks, math environments, and nested groups. A naive
regex cannot balance braces, so we walk the source character by character
counting depth from each ``\\eoce`` token. This is ~30 lines of Python
and keeps the dependency surface to nothing beyond the standard library.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Iterator

from extractors.common import (
    EXTRACTED_DIR,
    PROJECT_ROOT,
    collapse_ws,
    make_record,
    validate_records,
    write_jsonl,
)

REPO_ROOT: Path = (
    PROJECT_ROOT / "data" / "raw" / "openintro"
    / "openintro-statistics-master"
)
OUTPUT_PATH: Path = EXTRACTED_DIR / "openintro.jsonl"


# Map an OpenIntro chapter directory name → topic tags. We don't try to
# pin these to a VE401 chapter number because OpenIntro's chapter ordering
# differs from VE401 (e.g. OpenIntro covers SLR before MLR but uses its
# own chapter numbering); the tags are enough for the retriever to score
# relevance against a VE401 question's tag set.
_PATH_TO_TAGS: dict[str, list[str]] = {
    "ch_intro_to_data": ["intro-data", "study-design"],
    "ch_summarizing_data": ["descriptive-stats", "summary-stats"],
    "ch_probability": ["probability", "random-variables"],
    "ch_distributions": ["distributions", "normal", "binomial"],
    "ch_foundations_for_inf": ["sampling-distribution", "ci", "test"],
    "ch_inference_for_means": ["one-sample-T", "paired-T", "two-sample-T", "anova"],
    "ch_inference_for_props": ["one-sample-prop-Z", "two-sample-prop-Z", "chi2-gof"],
    "ch_regr_simple_linear": ["SLR", "SLR-CI", "SLR-PI"],
    "ch_regr_mult_and_log": ["MLR", "logistic-regression"],
}


# Try to map an OpenIntro filename slug → a finer-grained tag set. The
# default of an empty list means we fall back to the directory-level tags.
_FILE_TO_TAGS: dict[str, list[str]] = {
    # ch_inference_for_means
    "one-sample_means_with_the_t-distribution": ["one-sample-T"],
    "paired_data": ["paired-T"],
    "difference_of_two_means": ["two-sample-T", "welch-T", "pooled-T"],
    "comparing_many_means_with_anova": ["one-way-ANOVA"],
    "power_calculations_for_a_difference_of_means": ["power"],
    # ch_inference_for_props
    "inference_for_a_single_proportion": ["one-sample-prop-Z"],
    "difference_of_two_proportions": ["two-sample-prop-Z"],
    "testing_for_goodness_of_fit_using_chi-square": ["chi2-gof"],
    "testing_for_independence_in_two-way_tables": ["chi2-independence"],
    # ch_regr_simple_linear
    "fitting_a_line_residuals_and_correlation": ["SLR", "correlation-rho"],
    "least_squares_regression": ["SLR"],
    "outliers_in_linear_regression": ["SLR"],
    "inference_for_linear_regression": ["SLR-CI", "SLR-PI"],
}


# Pull a one-line title out of ``\qt{Title\label{slug}}`` if present.
# The title is purely cosmetic — we don't emit it as part of the question
# text — but seeing it in inspector output speeds up debugging.
_QT_RE = re.compile(r"\\qt\{([^{}]*?)(?:\\label\{[^}]*\})?\}", re.DOTALL)


def _strip_latex(text: str) -> str:
    """Best-effort plain-text view of a LaTeX exercise body.

    OpenIntro's exercise text is mostly prose with inline math, so we
    keep math intact (``$...$`` or ``\\(...\\)``) but unwrap structural
    macros that get in the way of question-text indexing:

    * ``\\qt{Title\\label{slug}}`` → drop the label, keep the title as a
      leading sentence so retrieval can match on it.
    * ``\\begin{parts}…\\end{parts}`` → keep the body, replace ``\\item``
      with ``(a) (b) (c) …`` so the parts read as flat prose.
    * ``\\FigureFullPath[caption]{w}{path}`` → drop entirely; figure
      captions are descriptive prose unrelated to the problem.
    * ``\\D{...}`` → drop (display-only macros like ``\\D{\\newpage}``).
    * ``\\begin{center}…\\end{center}`` → keep body.
    * Whitespace collapsed to single spaces at the end.

    Any other ``\\macro`` is left in place; downstream the renderer can
    decide whether to keep math notation literal or render it.
    """
    # \qt{Title\label{slug}}  →  "Title — "
    def _qt_sub(m: re.Match[str]) -> str:
        title = m.group(1).strip()
        return f"{title} — " if title else ""
    text = _QT_RE.sub(_qt_sub, text)

    # \FigureFullPath[caption]{w}{path}  →  ""
    text = re.sub(
        r"\\FigureFullPath(?:\[[^\]]*\])?\{[^{}]*\}\{[^{}]*\}",
        "",
        text,
    )

    # \D{...}  →  ""  (display-only newpage / pagebreak helpers)
    text = re.sub(r"\\D\{[^{}]*\}", "", text)

    # \begin{parts} ... \item A ... \item B ...  →  "(a) A (b) B ..."
    def _parts_sub(m: re.Match[str]) -> str:
        body = m.group(1)
        items = re.split(r"\\item\s*", body)
        out = []
        # First chunk before the first \item is preamble (rare; usually empty).
        if items and items[0].strip():
            out.append(items[0].strip())
        for i, chunk in enumerate(items[1:]):
            label = chr(ord("a") + i)
            out.append(f"({label}) {chunk.strip()}")
        return " ".join(out)

    text = re.sub(
        r"\\begin\{parts\}(.*?)\\end\{parts\}",
        _parts_sub,
        text,
        flags=re.DOTALL,
    )

    # \begin{center}...\end{center}, \begin{multicols}...\end{multicols}
    # → keep body
    for env in ("center", "multicols"):
        text = re.sub(
            rf"\\begin\{{{env}\}}(.*?)\\end\{{{env}\}}",
            r"\1",
            text,
            flags=re.DOTALL,
        )
    # \begin{multicols}{N} (with arg)
    text = re.sub(r"\\begin\{multicols\}\{\d+\}", "", text)

    # Drop comments — only ``%`` at line start or preceded by whitespace.
    # We avoid stripping ``\%`` (escaped percent inside math).
    text = re.sub(r"(?<!\\)%[^\n]*", "", text)

    return collapse_ws(text)


def _iter_eoce_bodies(tex: str) -> Iterator[str]:
    """Yield the first-arg body of every ``\\eoce{...}{...}`` macro.

    We walk the source manually because the body contains arbitrary LaTeX
    (including ``\\begin{...}\\end{...}`` blocks) that cannot be matched
    with a single regex. The walker:

    1. Finds the next literal token ``\\eoce{`` in the source.
    2. Tracks brace depth from that opening ``{``, counting all following
       ``{`` and ``}`` characters until depth returns to 0; that yields
       the first-arg body.
    3. Skips whitespace, expects a second ``{...}`` and consumes it
       (we don't return its content; in OpenIntro 4e it is always empty).
    4. Resumes scanning for the next ``\\eoce``.

    Backslash-escaped braces (``\\{``, ``\\}``) inside the body are
    common in math (``\\{x \\mid x>0\\}``) and must NOT shift depth, so
    we look at the previous character before counting a brace.
    """
    i = 0
    needle = r"\eoce{"
    n = len(tex)
    while True:
        j = tex.find(needle, i)
        if j == -1:
            return
        depth = 1
        k = j + len(needle)
        body_start = k
        while k < n and depth > 0:
            ch = tex[k]
            if ch == "{" and tex[k - 1] != "\\":
                depth += 1
            elif ch == "}" and tex[k - 1] != "\\":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        if depth != 0:
            # Malformed source — give up on this file rather than emit
            # half a problem. The dataset is large; one missed file is
            # acceptable.
            return
        yield tex[body_start:k]
        # Skip the second `{...}` arg (the empty solution slot in 4e).
        m = k + 1
        while m < n and tex[m].isspace():
            m += 1
        if m < n and tex[m] == "{":
            depth = 1
            m += 1
            while m < n and depth > 0:
                ch = tex[m]
                if ch == "{" and tex[m - 1] != "\\":
                    depth += 1
                elif ch == "}" and tex[m - 1] != "\\":
                    depth -= 1
                m += 1
        i = m


def _walk_chapter_files() -> Iterator[tuple[str, str, Path]]:
    """Yield ``(chapter_dir, file_slug, path)`` for every chapter section.

    File slug = stem of the .tex filename (so we can map it through
    ``_FILE_TO_TAGS`` before falling back to the directory tags).
    """
    for ch_dir in sorted(REPO_ROOT.glob("ch_*")):
        if not ch_dir.is_dir():
            continue
        tex_dir = ch_dir / "TeX"
        if not tex_dir.is_dir():
            continue
        for tex_path in sorted(tex_dir.glob("*.tex")):
            yield (ch_dir.name, tex_path.stem, tex_path)


def main() -> int:
    if not REPO_ROOT.is_dir():
        print(f"[error] missing repo: {REPO_ROOT}", file=sys.stderr)
        print(
            "        download via:\n"
            "        curl -L https://codeload.github.com/OpenIntroStat/"
            "openintro-statistics/zip/refs/heads/master "
            f"-o {REPO_ROOT.parent}/repo.zip && "
            f"unzip {REPO_ROOT.parent}/repo.zip -d {REPO_ROOT.parent}",
            file=sys.stderr,
        )
        return 1

    records: list[dict[str, Any]] = []
    files_seen = 0
    for ch_dir, file_slug, tex_path in _walk_chapter_files():
        files_seen += 1
        try:
            tex = tex_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            print(f"[warn] cannot read {tex_path}: {exc}", file=sys.stderr)
            continue

        tags: list[str] = list(
            _FILE_TO_TAGS.get(file_slug, _PATH_TO_TAGS.get(ch_dir, []))
        )

        for n, body in enumerate(_iter_eoce_bodies(tex), start=1):
            text = _strip_latex(body)
            if len(text) < 20:
                # Skip near-empty bodies (figure-only exercises sometimes
                # have nothing but a \FigureFullPath that we just stripped).
                continue
            rec = make_record(
                id=f"openintro_{ch_dir}_{file_slug}_{n:03d}",
                source="openintro",
                source_priority=2,
                chapter=ch_dir.removeprefix("ch_"),
                topic_tags=tags,
                slide_refs=[],
                difficulty=None,
                language="en",
                type="exercise",
                question=text,
                given=None,
                solution_steps=[],
                rubric=[],
                traps=[],
                trail_of_thought=None,
                final_answer=None,
            )
            records.append(rec)

    print(f"[info] scanned {files_seen} .tex files; emitted {len(records)} records")

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
