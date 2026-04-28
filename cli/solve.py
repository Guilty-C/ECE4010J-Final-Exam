"""Phase F (plan §6 step F1/F2) — command-line wrapper for the solver.

Usage::

    python -m cli.solve "A bottling line ... test H0: mu = 25 ..."
    python -m cli.solve --file question.txt
    python -m cli.solve --mode rule --json --file question.txt

Modes (plan §6 step F2):

* ``rule`` (default): pure template fill, fully offline, < 2 s response.
* ``rag``: same retrieval + render, plus LoRA-Qwen rewrite — requires
  Phase J (``infer/rag_pipeline.py``) which is not yet implemented; the
  CLI degrades gracefully back to ``rule`` and prints a notice.
* ``llm-only``: skip retrieval, ask the local Qwen base model directly.
  Same caveat as ``rag``.

The CLI is intentionally dependency-free (only ``argparse`` from stdlib);
the solver itself is the only import required.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Make ``python -m cli.solve`` work whether invoked from the project root
# or from elsewhere. When invoked as a script we want absolute imports of
# the sibling packages (classifier, retriever, solver) to resolve, so we
# put the project root on ``sys.path``.
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from solver import solve  # noqa: E402  — see sys.path tweak above


def _read_question(args: argparse.Namespace) -> str:
    """Pick the question text from positional argument, --file, or stdin."""
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    elif args.question:
        text = " ".join(args.question)
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        raise SystemExit(
            "error: no question supplied. Pass it as a positional argument, "
            "via --file, or pipe it on stdin."
        )
    return text.strip()


def _parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="ve401-solve",
        description=(
            "VE401 / ECE4010J exam-question solver. Classifies a question "
            "against the 25 crash-course test cards, fills the matching "
            "template with extracted numerical givens, and emits a five-"
            "segment Markdown answer with slide refs."
        ),
    )
    p.add_argument(
        "question",
        nargs="*",
        help="Question text (concatenated). If omitted, use --file or stdin.",
    )
    p.add_argument(
        "--file",
        "-f",
        help="Read the question from a UTF-8 text file instead of argv.",
    )
    p.add_argument(
        "--mode",
        choices=("rule", "rag", "llm-only"),
        default="rule",
        help=(
            "rule: pure template fill (default, offline). "
            "rag: template + Qwen rewrite (Phase J, not yet wired — "
            "falls back to rule). "
            "llm-only: ask Qwen directly (Phase J, not yet wired — "
            "falls back to rule)."
        ),
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON dump of the SolveResult instead of Markdown.",
    )
    p.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="How many candidate cards to keep (default: 3).",
    )
    p.add_argument(
        "--related",
        type=int,
        default=0,
        help=(
            "If > 0, also list the top-N record_ids retrieved from the "
            "corpus. Triggers the Phase D retriever (~2.7 s cold start). "
            "Default: 0 (skip retrieval — pure offline classifier+template)."
        ),
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress diagnostic notices (mode fallback messages).",
    )
    return p.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = _parse_args(argv)
    question = _read_question(args)

    # Mode handling. rag / llm-only require Phase J (infer/rag_pipeline.py),
    # which the plan slots after MVP completion. Until then, advertise the
    # selected mode but degrade to the rule path so the CLI is always
    # responsive and offline-friendly.
    if args.mode != "rule" and not args.quiet:
        sys.stderr.write(
            f"[ve401-solve] mode={args.mode!r} requires Phase J "
            f"(LoRA-Qwen RAG pipeline) which is not yet wired up; "
            f"falling back to mode=rule.\n"
        )

    result = solve(
        question,
        top_k_cards=max(1, args.top_k),
        related_records=max(0, args.related),
    )

    if args.json:
        sys.stdout.write(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(result.markdown)
        if not result.markdown.endswith("\n"):
            sys.stdout.write("\n")
        if result.related_record_ids:
            sys.stdout.write("\n*Related corpus records:* ")
            sys.stdout.write(", ".join(result.related_record_ids))
            sys.stdout.write("\n")

    return 0 if result.card_id else 1


if __name__ == "__main__":
    raise SystemExit(main())
