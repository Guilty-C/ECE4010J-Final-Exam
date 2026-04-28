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

---

## 2026-04-28 — Phase B: external open corpora (DONE)

### What shipped

Three new per-source JSONL files plus the merged corpus:

| File | Records | Source | Priority |
|---|---|---|---|
| `data/extracted/openintro.jsonl`     | **385**   | OpenIntro Statistics 4e (LaTeX source) | 2 |
| `data/extracted/openstax.jsonl`      | **1,811** | OpenStax Introductory Statistics 2e (CNXML) | 2 |
| `data/extracted/hendrycks_math.jsonl`| **1,245** | Hendrycks MATH, Counting & Probability slice | 3 |
| **`data/corpus.jsonl`** (merged)     | **3,597** | union of all five JSONLs, fingerprint-deduped | 1/2/3 |

### Pipeline

```
data/raw/                                                # gitignored
├── hendrycks_math/competition_math.parquet              # HF mirror
├── openintro/openintro-statistics-master/               # codeload zip
└── openstax/osbooks-introductory-statistics-bundle-main/  # codeload zip

extractors/extract_hendrycks.py     # parquet → jsonl   →  1,245 records
extractors/extract_openintro.py     # \eoce{...}{} TeX  →    385 records
extractors/extract_openstax.py      # CNXML XML walk    →  1,811 records
extractors/merge_corpus.py          # union+dedupe      →  3,597 records
```

Run order:

```bash
# (one-time downloads — see "Source acquisition" below)
python -m extractors.extract_hendrycks
python -m extractors.extract_openintro
python -m extractors.extract_openstax
python -m extractors.merge_corpus
python -m tests.test_corpus    # smoke test, all asserts pass
python -m tests.test_extractors # Phase A regression, still green
```

### Acceptance criteria (plan §6)

| Criterion | Target | Actual | Pass |
|---|---|---|---|
| `corpus.jsonl` size | ≥ 1,200 | **3,597** | ✓ |
| schema consistency 100% | yes | yes (every record validates) | ✓ |
| no duplicate questions | 0 | 0 (132 collisions deduped during merge) | ✓ |

Cross-cuts that exceeded plan estimates: OpenStax 2e turned out to ship
solutions inline for 889 problems (49% of its records) — the plan
assumed pure problem-only — so the corpus has a 65% `solution_steps`
non-empty rate overall.

### Source acquisition

GitHub `github.com` was intermittently unreachable from this machine
(connect timeouts on port 443) but `codeload.github.com` and
`api.github.com` were reachable, so we fetched both repos via the
codeload zip endpoint instead of `git clone`. The HuggingFace primary
was unreachable; we used the `hf-mirror.com` mirror for the Hendrycks
parquet.

| Asset | URL used |
|---|---|
| Hendrycks MATH | `https://hf-mirror.com/datasets/qwedsacf/competition_math/resolve/main/data/train-00000-of-00001-7320a6f3aba8ebd2.parquet` |
| OpenIntro Statistics 4e | `https://codeload.github.com/OpenIntroStat/openintro-statistics/zip/refs/heads/master` |
| OpenStax Intro Stats 2e | `https://codeload.github.com/openstax/osbooks-introductory-statistics-bundle/zip/refs/heads/main` |

The `data/raw/` tree stays out of git per `.gitignore`; each end re-runs
the curls.

### Notable extractor decisions

* **Hendrycks** is filtered to `type == "Counting & Probability"` only
  (1,245 / 12,500). The plan §2.2 also lists "Prealgebra/Statistics" but
  on inspection the Prealgebra bucket is dominated by arithmetic word
  problems, not statistics; the crash-course corpus already covers
  descriptive statistics. Final-answer is recovered from the last
  `\boxed{...}` group in the solution prose (Hendrycks convention).
* **OpenIntro 4e** ships problems but not solutions in the public LaTeX
  source — the solution manual is sold separately. Every OpenIntro
  record therefore has `solution_steps=[]`. The `\eoce{problem}{}` macro
  is parsed with a hand-rolled brace walker rather than a regex because
  the body contains arbitrary nested LaTeX environments. The `\qt{Title
  \label{slug}}` title is promoted to the front of the question text so
  retrieval can match on it.
* **OpenStax 2e** is parsed via `xml.etree`. The collection XML
  (`introductory-statistics-2e.collection.xml`) is read once to map
  module IDs → chapter slug. Each `<exercise><problem>` body is
  flattened to plain text; MathML is dropped (surrounding prose
  preserves enough signal for the retriever); empty self-closing
  `<link target-id="..." />` cross-references are substituted with
  the literal `[Table/Figure]` so sentences like "From `<link/>`, find
  the percentage" don't degenerate into ungrammatical "From , find …".
* **Merge** dedupes by SHA-1 fingerprint of normalised question text;
  on collision the lower `source_priority` (= higher quality) wins.
  132 collisions were resolved this way (mostly OpenIntro/OpenStax
  cross-borrowed problems).

### Coverage breakdown of `corpus.jsonl` (3,597 records)

* By source: ve401_local 208, crash_course 80, openintro 385,
  openstax 1,679 (down from 1,811 raw because of inter-source dupes),
  hendrycks_math 1,245.
* By priority: 1 → 288 (VE401 gold), 2 → 2,064 (OpenIntro+OpenStax),
  3 → 1,245 (Hendrycks).
* By type: exercise 3,517, card 25, trap 30, drill 25.
* `solution_steps` non-empty: 2,323 / 3,597 (65%).
* `slide_refs` non-empty: 222 / 3,597 (6%) — only VE401 sources cite
  slide pages; this is expected.
* `rubric` non-empty: 155 / 3,597 (4%) — VE401 HTML exercises only.

### Known limitations

* `openintro` records are problem-only. Phase E (template renderer) and
  Phase I (LoRA fine-tune) will mostly draw their solution-style signal
  from the VE401 local + OpenStax + Hendrycks records that DO have
  solutions; OpenIntro contributes question-phrasing variety only.
* OpenStax MathML fragments are dropped; question text is therefore
  slightly impoverished where a problem hinges on a typeset formula.
  Spot-checks suggest the prose carries enough context for retrieval —
  this can be revisited if the classifier struggles on math-heavy
  questions.
* Inter-source duplicate handling is fingerprint-only; near-duplicates
  (same problem with reworded surface) are not merged. Acceptable for
  this dataset size; revisit if the trainer reports memorisation
  artifacts.

### Files added

```
ve401_solver/
├── extractors/
│   ├── extract_hendrycks.py
│   ├── extract_openintro.py
│   ├── extract_openstax.py
│   └── merge_corpus.py
├── data/
│   ├── extracted/
│   │   ├── hendrycks_math.jsonl     # 1,245
│   │   ├── openintro.jsonl          #   385
│   │   └── openstax.jsonl           # 1,811
│   └── corpus.jsonl                 # 3,597 (deduped union)
└── tests/test_corpus.py
```

Dependencies added: `pandas`, `pyarrow` (for the Hendrycks parquet);
everything else (xml.etree, hashlib, re) was already in the standard
library or `requirements.txt`.

### Next up

Plan §6 says **Phase C** (classifier) and **Phase D** (retriever) are
the next pieces — both run against `data/corpus.jsonl`. Phase H
(infrastructure: git push, ssh, remote model probe) is independent and
can be parallelised.
