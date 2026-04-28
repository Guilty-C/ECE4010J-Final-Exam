# ve401-solver

Local template-retrieval solver for **ECE4010J / VE401 — Probabilistic Methods in Engineering** (chapters 15–32).

Given a natural-language exam-style question, the system identifies its test type, retrieves the matching template from a curated corpus, and renders a step-by-step solution that follows the course's slide conventions (slide-numbered formulas, df = k−1−m for GoF, Welch ν rounded *down*, denominator-with-p₀ for proportion tests, …).

## Status

| Phase | Status | Date | Headline result |
|---|---|---|---|
| A — local material extraction | DONE | 2026-04-28 | 208 ve401 + 80 crash-course records, slide-ref coverage 84% |
| B — external open corpora | DONE | 2026-04-28 | 3,597 deduped corpus records (OpenIntro 385, OpenStax 1,679, Hendrycks 1,245) |
| C — triage classifier | DONE | 2026-04-28 | 14/14 sample-final questions accepted top-1, 13/14 top-3 |
| D — retriever | DONE | 2026-04-28 | every card (25/25) recalls ≥ 1 template; 5/5 canonical queries surface VE401-local in top-3; 1.3 ms/query warm |
| E — template fill + render | DONE | 2026-04-28 | 5-section Markdown for all 25 cards; numeric eval for Z / T / χ²-variance / paired-T / χ²-GoF; 3/3 smoke tests green; Phase C regression unchanged |
| F — CLI + end-to-end test | not started | — | MVP gate |
| H — infra (git/ssh/Qwen probe) | not started | — | — |
| I — LoRA training (remote) | not started | — | — |
| J — RAG inference (local) | not started | — | — |

Acceptance test cheatsheet:

```bash
python -m tests.test_extractors   # Phase A — JSONL schema, volume, sentinels
python -m tests.test_corpus       # Phase B — corpus volume, dedup, source mix
python -m tests.test_triage       # Phase C — 14 sample-final main questions
python -m tests.test_retriever    # Phase D — 25/25 cards retrievable + 5 smoke queries
python -m tests.test_render       # Phase E — Z / T / chi-square GoF end-to-end
```

See `progress.md` for full per-phase write-ups.

**Next**: Phase F (CLI + 16-question end-to-end MVP gate). Phase H (git
push + remote model probe) is independent and can be parallelised.

### Try the solver end-to-end

```python
from solver import solve
res = solve(
    "A bottling line is calibrated so that the fill volume is normally "
    "distributed with known standard deviation sigma = 2.0 mL. The "
    "target mean is mu_0 = 25 mL. A random sample of n = 25 bottles "
    "gives x_bar = 24.3 mL. At alpha = 0.05, test H_0: mu = 25 versus "
    "the two-sided alternative."
)
print(res.card_id)            # 'card01'
print(res.statistic_value)    # -1.75
print(res.markdown)           # five-segment Markdown answer
```

## Project layout

```
ve401_solver/
├── plan.md                       # full project plan
├── progress.md                   # timestamped log
├── data/
│   ├── raw/                      # gitignored — local PDFs/HTML, fetched per-host
│   └── extracted/                # JSONL corpora (in repo)
├── extractors/                   # PDF / HTML / TeX → JSONL
├── classifier/                   # (Phase C) tag taxonomy + decision tree
├── retriever/                    # (Phase D) BM25 + classifier-driven candidate gather
├── solver/                       # (Phase E) template fill + render
├── infer/                        # (Phase J) Qwen2.5-3B local inference
├── train/                        # (Phase I) LoRA fine-tune (runs on remote GPU)
├── ops/                          # ssh / sync / model-probe scripts
├── cli/                          # `python -m ve401_solver.cli.solve`
└── tests/
```

## Quick start (Phase A–C reproduction)

```bash
pip install beautifulsoup4 lxml jsonschema pdfminer.six pandas pyarrow

# Phase A — re-run local extractors against the source files in ../
# (the parent project dir D:\4010Cheating Code\ keeps the raw PDFs/HTMLs).
python -m extractors.extract_ve401_html
python -m extractors.extract_crash_course
python -m extractors.extract_ve401_pdf
python -m extractors.merge_local
python -m tests.test_extractors

# Phase B — external corpora (one-time downloads to data/raw/, see progress.md
# §"Source acquisition" for the exact URLs).
python -m extractors.extract_hendrycks
python -m extractors.extract_openintro
python -m extractors.extract_openstax
python -m extractors.merge_corpus
python -m tests.test_corpus

# Phase C — classifier (no extra setup; reads classifier/tag_taxonomy.json)
python -m tests.test_triage

# Phase D — retriever (BM25 + classifier-driven candidate gather; no extra deps)
python -m tests.test_retriever
```

### Try the classifier on a single question

```python
from classifier.triage_rules import triage
hits = triage(
    "A bottling line: sigma is known to be 4 mL. n=25, x_bar=498.6 mL. "
    "Test the hypothesis that the true mean equals 500 mL."
)
for h in hits:
    print(h.card_id, h.score, h.title)
# card01 8 One-sample Z-test for mu (sigma known)
```

### Try the retriever

```python
from retriever import retrieve, retrieve_for_card

# free-text query → top-3 templates
for h in retrieve(
    "A geneticist counts 90 yellow, 35 green, 25 white seeds and asks "
    "whether the data fit the predicted 9:3:4 ratio.",
    top_k=3,
):
    print(h.rank, h.card_id, h.source, round(h.score, 2), h.record_id)
# 1 card15 ve401_local 32.85 ve401_local_ch25_q1
# 2 card15 ve401_local 28.30 ...

# every card has at least one template
hits = retrieve_for_card("card12", top_k=5)   # paired-T
print(hits[0].record_id, hits[0].source)
```

## Remote training infrastructure

- Host: `lrrelevant@10.35.13.38`
- Model: `Qwen/Qwen2.5-3B-Instruct`
- Sync channel: this repo on GitHub (`Guilty-C/ECE4010J-Final-Exam`)
- LoRA adapters pushed back via Git LFS

See `plan.md` §6 phases H/I/J for details.

## License

Code in this repository: MIT.
Data extracted from VE401 / ECE4010J course materials remains under the original course copyright; redistribution is for authorized course-internal use only.
