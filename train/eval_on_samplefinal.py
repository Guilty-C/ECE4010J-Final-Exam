"""train/eval_on_samplefinal.py — Phase I4.

Run the LoRA-Qwen on the 14 sample-final main questions and score:

* **card-id consistency** — does the classifier applied to the *generated*
  answer recover the same card the rule classifier extracts from the
  question? (rule baseline is 14/14 acceptable; this measures whether
  the model hallucinates a different test type.)
* **decision consistency** — does the generated answer reach the same
  reject / fail-to-reject decision as the gold solution? Compared as a
  string match on a small canonical vocabulary.
* **average generated length / time** — sanity numbers.

Writes ``eval_report.md`` next to the adapter checkpoint.

Run on the remote with the trained adapter::

    cd /data2/lrrelevant/ve401-solver
    conda activate agentiad
    CUDA_VISIBLE_DEVICES=1 HF_ENDPOINT=https://hf-mirror.com \
        python -m train.eval_on_samplefinal \
            --base Qwen/Qwen2.5-3B-Instruct \
            --adapter checkpoints/qwen25_3b_lora_v1
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

os.environ.setdefault("TRANSFORMERS_VERBOSITY", "warning")

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
sys.path.insert(0, str(_REPO))

# Reuse Phase C / Phase F gold mapping: same 14 acceptable sets used in
# tests/test_triage.py and tests/test_end_to_end.py. Kept inline here so
# this script is self-contained for the eval run.
GOLD_ACCEPTABLE: Dict[str, List[str]] = {
    "ve401_local_samplefinal_q2":  ["card03"],
    "ve401_local_samplefinal_q3":  ["card01"],
    "ve401_local_samplefinal_q4":  ["card12", "card05", "card04"],
    "ve401_local_samplefinal_q5":  ["card10", "card05", "card12", "card13"],
    "ve401_local_samplefinal_q6":  ["card09"],
    "ve401_local_samplefinal_q7":  ["card09"],
    "ve401_local_samplefinal_q8":  ["card15"],
    "ve401_local_samplefinal_q9":  ["card16"],
    "ve401_local_samplefinal_q10": ["card18", "card19"],
    "ve401_local_samplefinal_q11": ["card18", "card19"],
    "ve401_local_samplefinal_q12": ["card20", "card21"],
    "ve401_local_samplefinal_q13": ["card21"],
    "ve401_local_samplefinal_q14": ["card20"],
    "ve401_local_samplefinal_q16": ["card19"],
}


def _strip_leak(text: str) -> str:
    """Identical helper to tests/test_triage.py: drop a final orphan
    chapter-header glued to the end of a PDF-extracted question."""
    leaks = [
        r"Chi-Squared Goodness-of-Fit Tests.*$",
        r"Tests of Independence.*$",
        r"Simple Linear Regression.*$",
        r"Multiple Linear Regression.*$",
        r"Model Selection.*$",
        r"One-way ANOVA.*$",
        r"Post-hoc.*$",
    ]
    for pat in leaks:
        text = re.sub(pat, "", text, flags=re.IGNORECASE | re.DOTALL).rstrip()
    return text


def _stitch_question(corpus_path: Path, qid: str) -> str:
    """Collect the umbrella + sub-part records for a single sample-final
    question and stitch them into one prompt."""
    chunks: List[str] = []
    with corpus_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            rid = r.get("id", "")
            if rid == qid or rid.startswith(qid + "_part_"):
                q = (r.get("question") or "").strip()
                if q:
                    chunks.append(q)
    return _strip_leak("\n\n".join(chunks))


# ----------------------------------------------------------------------
# Decision word extraction
# ----------------------------------------------------------------------

_DECISION_PATTERNS = [
    (re.compile(r"\bdo\s*not\s+reject\b", re.IGNORECASE), "fail-to-reject"),
    (re.compile(r"\bfail(?:\s+to|ed)\s+reject\b", re.IGNORECASE), "fail-to-reject"),
    (re.compile(r"\bcannot\s+reject\b", re.IGNORECASE), "fail-to-reject"),
    (re.compile(r"\binsufficient\s+evidence\b", re.IGNORECASE), "fail-to-reject"),
    (re.compile(r"\breject\b", re.IGNORECASE), "reject"),
]


def _classify_decision(text: str) -> Optional[str]:
    for pat, label in _DECISION_PATTERNS:
        if pat.search(text):
            return label
    return None


# ----------------------------------------------------------------------
# Gold answer lookup (sample-final solutions live in sub-part records)
# ----------------------------------------------------------------------


def _gold_answer(corpus_path: Path, qid: str) -> str:
    parts: List[str] = []
    with corpus_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            rid = r.get("id", "")
            if rid == qid or rid.startswith(qid + "_part_"):
                for step in r.get("solution_steps") or []:
                    c = step.get("content")
                    if c:
                        parts.append(c)
    return "\n".join(parts)


# ----------------------------------------------------------------------
# Generation
# ----------------------------------------------------------------------


def _load_model(base: str, adapter: Optional[str]):
    import torch  # type: ignore
    from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore

    print(f"[eval] loading base {base}")
    tok = AutoTokenizer.from_pretrained(base, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        base,
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
        device_map="auto",
    )
    if adapter:
        from peft import PeftModel  # type: ignore
        print(f"[eval] applying adapter {adapter}")
        model = PeftModel.from_pretrained(model, adapter)
    model.eval()
    return tok, model


SYSTEM_PROMPT = (
    "You are a teaching assistant for VE401 / ECE4010J "
    "(Probabilistic Methods in Engineering, chapters 15–32). "
    "Answer in English. Follow the slide-notation conventions: "
    "Welch df rounded down, df = k - 1 - m for chi-square goodness-of-fit, "
    "denominator with p_0 for proportion tests, two-sided alternative "
    "uses z_{alpha/2}. When relevant, cite slide pages. Structure the "
    "answer in five labelled sections: Setup, Hypotheses, Statistic, "
    "Computation, Decision. Surface common traps and grading checkpoints "
    "where helpful."
)


def _generate(tok, model, question: str, max_new_tokens: int = 768) -> str:
    import torch  # type: ignore

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    inputs = tok.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
    )
    inputs = inputs.to(model.device)
    with torch.no_grad():
        out = model.generate(
            inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=1.0,
            top_p=1.0,
            pad_token_id=tok.pad_token_id,
            eos_token_id=tok.eos_token_id,
        )
    gen = out[0, inputs.shape[-1]:]
    return tok.decode(gen, skip_special_tokens=True).strip()


# ----------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="Qwen/Qwen2.5-3B-Instruct")
    ap.add_argument("--adapter", default="checkpoints/qwen25_3b_lora_v1")
    ap.add_argument("--corpus", default="data/extracted/ve401_local.jsonl")
    ap.add_argument("--out", default=None,
                    help="report path; defaults to <adapter>/eval_report.md")
    ap.add_argument("--max-new-tokens", type=int, default=768)
    ap.add_argument("--no-adapter", action="store_true",
                    help="run base model only — to compute the LoRA delta")
    args = ap.parse_args(argv)

    repo = _REPO
    corpus = repo / args.corpus
    adapter_dir = (repo / args.adapter) if not Path(args.adapter).is_absolute() else Path(args.adapter)
    adapter = None if args.no_adapter else str(adapter_dir)
    out_path = Path(args.out) if args.out else adapter_dir / "eval_report.md"

    from classifier.triage_rules import triage  # type: ignore

    tok, model = _load_model(args.base, adapter)

    rows: List[Dict[str, Any]] = []
    for qid, accept in GOLD_ACCEPTABLE.items():
        question = _stitch_question(corpus, qid)
        if not question:
            continue
        rule_hits = triage(question, top_k=3)
        rule_top1 = rule_hits[0].card_id if rule_hits else None

        gold = _gold_answer(corpus, qid)
        gold_decision = _classify_decision(gold)

        t0 = time.perf_counter()
        gen = _generate(tok, model, question, max_new_tokens=args.max_new_tokens)
        dt = time.perf_counter() - t0

        # classify the generated answer to see what card the model is
        # implicitly using
        gen_hits = triage(gen, top_k=3)
        gen_top1 = gen_hits[0].card_id if gen_hits else None
        gen_decision = _classify_decision(gen)

        rows.append({
            "qid": qid,
            "rule_top1": rule_top1,
            "gen_top1": gen_top1,
            "card_acceptable": gen_top1 in accept,
            "rule_acceptable": rule_top1 in accept,
            "gold_decision": gold_decision,
            "gen_decision": gen_decision,
            "decision_match": (
                gen_decision is not None
                and gold_decision is not None
                and gen_decision == gold_decision
            ),
            "gen_chars": len(gen),
            "time_s": round(dt, 2),
            "gen_excerpt": (gen[:240] + "…") if len(gen) > 240 else gen,
        })
        print(
            f"[eval] {qid}  rule={rule_top1} gen={gen_top1} "
            f"acc={'+' if rows[-1]['card_acceptable'] else '-'} "
            f"dec={gen_decision}/{gold_decision} time={dt:.1f}s"
        )

    n = len(rows)
    n_card = sum(1 for r in rows if r["card_acceptable"])
    n_rule = sum(1 for r in rows if r["rule_acceptable"])
    n_dec_eligible = sum(1 for r in rows if r["gold_decision"] is not None)
    n_dec_match = sum(1 for r in rows if r["decision_match"])
    n_dec_emitted = sum(1 for r in rows if r["gen_decision"] is not None)

    lines: List[str] = []
    lines.append(f"# eval_report — Phase I LoRA Qwen2.5-3B-Instruct")
    lines.append("")
    lines.append(f"* base    = `{args.base}`")
    lines.append(f"* adapter = `{adapter or '(no adapter — base-only baseline)'}`")
    lines.append(f"* questions evaluated: **{n}**")
    lines.append("")
    lines.append("## Headline metrics")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append(f"| card-id acceptable (LoRA) | **{n_card}/{n}** |")
    lines.append(f"| card-id acceptable (rule baseline) | {n_rule}/{n} |")
    lines.append(
        f"| decision word emitted | {n_dec_emitted}/{n} "
        f"(eligible gold: {n_dec_eligible})"
    )
    if n_dec_eligible:
        lines.append(
            f"| decision-match rate | **{n_dec_match}/{n_dec_eligible}** "
            f"({100*n_dec_match/n_dec_eligible:.0f}%)"
        )
    avg_time = sum(r["time_s"] for r in rows) / max(n, 1)
    avg_chars = sum(r["gen_chars"] for r in rows) / max(n, 1)
    lines.append(f"| avg generation time | {avg_time:.1f} s |")
    lines.append(f"| avg generated length | {avg_chars:.0f} chars |")
    lines.append("")

    lines.append("## Per-question table")
    lines.append("")
    lines.append("| qid | rule top-1 | gen top-1 | card-acc | gold dec | gen dec | dec-match | t (s) |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append(
            "| {qid} | {rule} | {gen} | {acc} | {gd} | {nd} | {match} | {t} |".format(
                qid=r["qid"].replace("ve401_local_samplefinal_", ""),
                rule=r["rule_top1"] or "-",
                gen=r["gen_top1"] or "-",
                acc=("✓" if r["card_acceptable"] else "✗"),
                gd=r["gold_decision"] or "-",
                nd=r["gen_decision"] or "-",
                match=("✓" if r["decision_match"] else "—"),
                t=r["time_s"],
            )
        )
    lines.append("")

    lines.append("## Generation excerpts")
    lines.append("")
    for r in rows:
        lines.append(f"### {r['qid']}")
        lines.append("")
        lines.append("```")
        lines.append(r["gen_excerpt"])
        lines.append("```")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[eval] wrote {out_path}")
    print(
        f"[eval] card-id acceptable: {n_card}/{n} "
        f"(rule baseline: {n_rule}/{n}); "
        f"decision-match: {n_dec_match}/{n_dec_eligible}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
