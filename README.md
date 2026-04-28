# ve401-solver

Local template-retrieval solver for **ECE4010J / VE401 — Probabilistic Methods in Engineering** (chapters 15–32).

Given a natural-language exam-style question, the system identifies its test type, retrieves the matching template from a curated corpus, and renders a step-by-step solution that follows the course's slide conventions (slide-numbered formulas, df = k−1−m for GoF, Welch ν rounded *down*, denominator-with-p₀ for proportion tests, …).

## Status

**Phase A — DONE** (2026-04-28). Local material extraction.

| File | Records |
|---|---|
| `data/extracted/ve401_local.jsonl` | 208 (HTML 130 + PDF 78) |
| `data/extracted/crash_course.jsonl` | 80 (25 cards + 30 traps + 25 drills) |
| `data/extracted/ve401_pdf.jsonl` | 78 (intermediate) |

Acceptance:
- jsonschema validation: **pass**
- size: 208 (target ~145, +43%)
- `slide_refs` non-empty: **84%** (174/208)
- smoke test: `python -m tests.test_extractors` → all 6 `[ok]`

See `progress.md` for full details.

**Next**: Phase B (external open corpora — OpenIntro / OpenStax / Hendrycks MATH) and Phase C (classifier).

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

## Quick start (Phase A reproduction)

```bash
pip install beautifulsoup4 lxml jsonschema pdfminer.six

# Re-run extractors against the source files in ../  (the parent project dir
# D:\4010Cheating Code\ keeps the raw PDFs / HTMLs).
python -m extractors.extract_ve401_html
python -m extractors.extract_crash_course
python -m extractors.extract_ve401_pdf
python -m extractors.merge_local

# Smoke test
python -m tests.test_extractors
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
