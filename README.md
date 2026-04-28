# ve401-solver

Local template-retrieval solver for **ECE4010J / VE401 — Probabilistic Methods in Engineering** (chapters 15–32).

Given a natural-language exam-style question, the system identifies its test type, retrieves the matching template from a curated corpus, and renders a step-by-step solution that follows the course's slide conventions (slide-numbered formulas, df = k−1−m for GoF, Welch ν rounded *down*, denominator-with-p₀ for proportion tests, …).

## Status

| Phase | Status | Date | Headline result |
|---|---|---|---|
| A — local material extraction | DONE | 2026-04-28 | 208 ve401 + 80 crash-course records, slide-ref coverage 84% |
| B — external open corpora | DONE | 2026-04-28 | 3,597 deduped corpus records (OpenIntro 385, OpenStax 1,679, Hendrycks 1,245) |
| C — triage classifier | DONE | 2026-04-28 | 14/14 sample-final questions accepted top-1, 13/14 top-3 |
| D — retriever | not started | — | — |
| E — template fill + render | not started | — | — |
| F — CLI + end-to-end test | not started | — | MVP gate |
| H — infra (git/ssh/Qwen probe) | not started | — | — |
| I — LoRA training (remote) | not started | — | — |
| J — RAG inference (local) | not started | — | — |

Acceptance test cheatsheet:

```bash
python -m tests.test_extractors   # Phase A — JSONL schema, volume, sentinels
python -m tests.test_corpus       # Phase B — corpus volume, dedup, source mix
python -m tests.test_triage       # Phase C — 14 sample-final main questions
```

See `progress.md` for full per-phase write-ups.

**Next**: Phase D (retriever) and Phase E (template renderer). Phase H
(git push + remote model probe) is independent and can be parallelised.

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
├── retriever/                    # (Phase D) tag + keyword search
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

## Remote training infrastructure

- Host: `lrrelevant@10.35.13.38`
- Model: `Qwen/Qwen2.5-3B-Instruct`
- Sync channel: this repo on GitHub (`Guilty-C/ECE4010J-Final-Exam`)
- LoRA adapters pushed back via Git LFS

See `plan.md` §6 phases H/I/J for details.

## License

Code in this repository: MIT.
Data extracted from VE401 / ECE4010J course materials remains under the original course copyright; redistribution is for authorized course-internal use only.
