# progress.md — VE401 Solver project log

Each entry timestamps a substantive change. Phase A (local material
extraction) is complete; later phases will be appended below.

---

## 2026-04-28 — Phase A: local material extraction (DONE)

### What shipped

Two JSONL corpora under `data/extracted/`:

| File | Records | Notes |
|---|---|---|
| `ve401_local.jsonl` | **208** | merged HTML exercise-bank + PDF homework + sample-final |
| `crash_course.jsonl` | **80** | 25 test cards + 30 traps + 25 drills (Q1–Q12 + B1–B4 + F/S/T1–3) |

### Pipeline

```
extractors/extract_ve401_html.py     # 4 exercise HTMLs        → 130 records
extractors/extract_crash_course.py   # crash_course HTML       →  80 records
extractors/extract_ve401_pdf.py      # 5 hw PDFs + sample      →  78 records
extractors/merge_local.py            # merge + dedup + enrich  → 208 records
```

Run order:

```bash
python -m extractors.extract_ve401_html
python -m extractors.extract_crash_course
python -m extractors.extract_ve401_pdf
python -m extractors.merge_local
python tests/test_extractors.py     # smoke test, all asserts pass
```

### Acceptance criteria (plan §6)

| Criterion | Target | Actual | Pass |
|---|---|---|---|
| JSONL passes `jsonschema` validation | yes | yes | ✓ |
| `ve401_local.jsonl` size | ~145 | **208** | ✓ |
| 10-record manual spot-check | pass | passed | ✓ |
| `slide_refs` non-empty rate | ≥ 70% | **84%** | ✓ |

### Coverage breakdown of `ve401_local.jsonl` (208 records)

* By chapter: 11/5/5 — — 12/14/13 — 11/15/16 — 13/15/13/10/11/10 (chapters 15–30) plus 34 entries with `chapter=None` (PDF segments that did not match the keyword inferer; mostly sample-final problem-1 part-shells and a few homework rubric prefixes).
* `solution_steps` non-empty: 169/208 (81%) — every HTML exercise has a labelled solution; all 20 homework entries are question-only (homework PDFs ship without solutions); 39/58 sample-final segments matched a solution block in the `_sol.pdf`.
* `slide_refs` non-empty: 174/208 (84%) — 85 from explicit citations in HTML text/rubric, 89 from chapter-anchor fallback applied during merge. The chapter-anchor map (`extractors/common.py:CHAPTER_SLIDE_ANCHOR`) attaches each chapter's primary slide page (e.g. ch19 → 436, ch26 → 619) when no explicit cite was harvested.
* `rubric` non-empty: 130/208 (62%) — every HTML card has a rubric; PDF entries do not.

### Notable extractor decisions

* Slide-ref harvest rejects chapter-notation forms (`slide 26.1`) post-hoc since Python's `re` cannot prevent the engine from backtracking to a shorter digit match. See `harvest_slide_refs` in `extractors/common.py`.
* Chapter inference for PDF segments uses an ordered keyword table (`merge_local.py:_CHAPTER_KEYWORDS`); compound names like "Neyman–Pearson" are matched before bare surnames like "Pearson" to keep ch17 problems from leaking into ch24.
* `pdfminer.six` emits literal `(cid:NN)` tokens for ligatures and Greek letters (no ToUnicode info in the source PDFs); a small replacement table in `extract_ve401_pdf.py:_CID_FIXES` handles the common cases (`fi`, `fl`, `α`, `μ`, `σ`, `≤`, `≥`, …) and the rest are stripped.
* Crash-course "drill" extraction includes 12 cross-cutting Q-drills wrapped in `<div class="card drill">` (combined classes), so the actual drill count is 25 rather than the plan's estimated 16. The smoke test asserts ≥ 13 (the strict minimum) to keep the gate honest if the source HTML changes.

### Known limitations

* PDF homework solutions are not in the source PDFs and are therefore absent from records `ve401_local_hw*_q*` (20 entries, all with `solution_steps=[]`). Phase B (external corpora) and Phase E (template renderer) will provide alternative solution paths for these.
* `samplefinal_q1` (the Multiple-Choice problem) splits into 5 sub-parts (i–v); the `_part_None` shell entry carries only the rubric preamble. Downstream code should prefer the per-part records.
* `sample_final` extraction stores the matched solution block as the entire concatenated body of the sub-part's region in `_sol.pdf`. A finer-grained "diff" against the question PDF would isolate just the answer text; this is deferred to Phase E where the renderer can do that prep more cheaply.

### Files added

```
ve401_solver/
├── extractors/
│   ├── __init__.py
│   ├── common.py
│   ├── extract_ve401_html.py
│   ├── extract_crash_course.py
│   ├── extract_ve401_pdf.py
│   └── merge_local.py
├── data/extracted/
│   ├── ve401_local.jsonl
│   ├── ve401_pdf.jsonl
│   └── crash_course.jsonl
└── tests/
    ├── __init__.py
    └── test_extractors.py
```

Dependencies installed (subset of `requirements.txt`): `beautifulsoup4`, `lxml`, `jsonschema`, `pdfminer.six`.

### Next up

Plan §6 says the next stage is **Phase B** (external open corpora — OpenIntro / OpenStax / Hendrycks MATH). Phase B is independent of Phase A and can be parallelised with **Phase C** (classifier) if desired.
