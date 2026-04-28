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
| F — CLI + end-to-end test | **DONE — MVP** | 2026-04-28 | `python -m cli.solve` with `--mode rule\|rag\|llm-only`, `--file`, `--json`, stdin; 14/14 sample-final card-id, 14/14 5-section skeleton, max 5.8 ms/question (offline) |
| H — infra (git/ssh/Qwen probe) | DONE | 2026-04-28 | repo on `ivlab` at `/data2/lrrelevant/ve401-solver`; conda env `agentiad` (torch 2.6+cu118, transformers 4.51, peft 0.18, accelerate 1.12, 4× RTX 3090); Phase A-F regression green on remote; Qwen2.5-3B-Instruct not yet cached — `ops/download_qwen.sh` ready |
| I — LoRA training (remote) | not started | — | — |
| J — RAG inference (local) | not started | — | — |

Acceptance test cheatsheet:

```bash
python -m tests.test_extractors   # Phase A — JSONL schema, volume, sentinels
python -m tests.test_corpus       # Phase B — corpus volume, dedup, source mix
python -m tests.test_triage       # Phase C — 14 sample-final main questions
python -m tests.test_retriever    # Phase D — 25/25 cards retrievable + 5 smoke queries
python -m tests.test_render       # Phase E — Z / T / chi-square GoF end-to-end
python -m tests.test_end_to_end   # Phase F MVP gate — sample-final card+skeleton+latency
```

See `progress.md` for full per-phase write-ups.

**Next**: Phase H (git push + remote Qwen2.5-3B probe), then Phase I
(LoRA training on the remote GPU) and Phase J (local RAG inference,
which fills in `--mode rag` / `--mode llm-only`). The MVP rule-based
solver is complete and offline-runnable today.

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

### Use the CLI (Phase F)

```bash
# Pure offline rule-based solver (default mode)
python -m cli.solve "A bottling line ... sigma = 2.0 mL ... n = 25 ... x_bar = 24.3 ..."

# Read the question from a file
python -m cli.solve --file my_question.txt

# Pipe the question on stdin
cat question.txt | python -m cli.solve

# Get a JSON dump of the SolveResult instead of Markdown
python -m cli.solve --json --file question.txt

# Also list top-N retrieved corpus records (lazy-loads Phase D index, ~2.7 s cold)
python -m cli.solve --related 5 --file question.txt

# Future modes (Phase J — LoRA-Qwen RAG / direct LLM): currently fall back to rule
python -m cli.solve --mode rag --file question.txt
python -m cli.solve --mode llm-only --file question.txt
```

Exit code is `0` when a card was identified, `1` when the classifier
could not match the question to any of the 25 test cards.

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

- Host: `lrrelevant@10.35.13.38` (SSH alias `ivlab` in `~/.ssh/config`)
- Hardware: 4× RTX 3090 (24 GiB), 251 GiB RAM, 9.4 TiB free on `/data2`
- Repo path on remote: `/data2/lrrelevant/ve401-solver` (chosen because `/home` is at 98% full)
- Conda env: `agentiad` — torch 2.6.0+cu118, transformers 4.51.3, peft 0.18.1, accelerate 1.12.0
- Model: `Qwen/Qwen2.5-3B-Instruct` (NOT yet cached; `ops/download_qwen.sh` will fetch it into the symlinked HF cache on `/data2`)
- Sync channel: this repo on GitHub (`Guilty-C/ECE4010J-Final-Exam`)
- LoRA adapters pushed back via Git LFS (configured but not yet exercised)

```bash
# Phase H probes / sync
bash ops/ssh_setup.sh                 # smoke-test SSH (BatchMode)
bash ops/check_remote_model.sh        # full inventory: GPU / disk / conda envs / Qwen path probe
bash ops/sync_to_remote.sh            # clone or git pull on remote (defaults to /data2/lrrelevant/ve401-solver)

# Phase I prep (run when training starts)
bash ops/download_qwen.sh             # snapshot_download Qwen/Qwen2.5-3B-Instruct (~6 GB, into /data2 cache)

# Phase I → J handoff
bash ops/pull_checkpoint.sh qwen25_3b_lora_v1   # rsync adapter back, skip optimizer/scheduler blobs
```

See `plan.md` §6 phases H/I/J for details and `progress.md`'s
2026-04-28 Phase H entry for the live probe transcript.

## License

Code in this repository: MIT.
Data extracted from VE401 / ECE4010J course materials remains under the original course copyright; redistribution is for authorized course-internal use only.
