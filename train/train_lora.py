"""train/train_lora.py — Phase I3.

LoRA fine-tune of Qwen2.5-3B-Instruct on the prepared VE401 corpus.

Reads chat-formatted JSONL from ``data/training/{train,val}.jsonl``,
applies the Qwen2.5 chat template, masks user/system tokens out of the
loss (assistant-only SFT), wraps the model with PEFT-LoRA per the YAML
config, and runs ``transformers.Trainer`` for the configured epochs.
The final adapter is saved at ``checkpoints/qwen25_3b_lora_v1/``.

Run on the remote (idle GPU 1, 2, or 3 — GPU 0 has 14.5 GB free)::

    cd /data2/lrrelevant/ve401-solver
    conda activate agentiad
    CUDA_VISIBLE_DEVICES=1 HF_ENDPOINT=https://hf-mirror.com \
        python -m train.train_lora --config train/configs/qwen25_3b_lora.yaml

Notes
-----
* Assistant-only loss masking is implemented via the ``assistant`` token
  range emitted by ``tokenizer.apply_chat_template`` with
  ``return_assistant_tokens_mask=True`` (added in transformers 4.40).
  Tokens outside the assistant range get ``label=-100`` and so do not
  contribute to the cross-entropy loss.
* ``packing`` is intentionally off — the corpus is small enough (~3k
  examples × ~1k tokens = ~3M tokens) that the gain is marginal and
  packing complicates the assistant-mask logic.
* The script is dependency-tolerant: ``yaml`` is imported lazily so a
  smoke run on a stripped env can still parse JSON config files via
  ``--config-json``.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Optional: silence the noisy chat-template warning
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "warning")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _load_config(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".json"}:
        return json.loads(text)
    try:
        import yaml  # type: ignore
    except ImportError as e:
        raise SystemExit(
            f"FAIL: PyYAML not installed and config is YAML ({path}). "
            "Install pyyaml or pass a JSON config."
        ) from e
    return yaml.safe_load(text)


def _set_seed(seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np  # type: ignore

        np.random.seed(seed)
    except Exception:
        pass
    try:
        import torch  # type: ignore

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except Exception:
        pass


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _build_dataset(records: List[Dict[str, Any]], tokenizer, max_seq_length: int):
    """Render each record's messages with the chat template, tokenise, and
    build labels masked to assistant tokens only.

    Returns a ``datasets.Dataset`` (lazy) with input_ids / attention_mask /
    labels columns.
    """
    from datasets import Dataset  # type: ignore

    pad_id = tokenizer.pad_token_id
    if pad_id is None:
        # Qwen2.5's tokenizer ships pad_token=None by default; reuse EOS.
        tokenizer.pad_token = tokenizer.eos_token
        pad_id = tokenizer.pad_token_id

    def _tokenize_one(rec: Dict[str, Any]) -> Dict[str, List[int]]:
        messages = rec["messages"]
        # Try return_assistant_tokens_mask (transformers >= 4.40). It
        # gives a 0/1 list aligned with input_ids: 1 inside any assistant
        # turn (excluding the surrounding <|im_start|>...<|im_end|>).
        try:
            enc = tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=False,
                return_assistant_tokens_mask=True,
                return_dict=True,
                truncation=True,
                max_length=max_seq_length,
            )
            input_ids = list(enc["input_ids"])
            assistant_mask = list(enc["assistant_masks"])
        except (TypeError, KeyError):
            # Fallback: tokenise full text + the prefix-without-final-
            # assistant separately and mask everything before the prefix
            # boundary.
            full = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
            )
            prefix_msgs = messages[:-1]
            prefix = tokenizer.apply_chat_template(
                prefix_msgs,
                tokenize=False,
                add_generation_prompt=True,
            )
            input_ids = tokenizer(
                full, truncation=True, max_length=max_seq_length, add_special_tokens=False
            )["input_ids"]
            prefix_ids = tokenizer(
                prefix, truncation=True, max_length=max_seq_length, add_special_tokens=False
            )["input_ids"]
            cut = min(len(prefix_ids), len(input_ids))
            assistant_mask = [0] * cut + [1] * (len(input_ids) - cut)

        labels = [
            tok if mask == 1 else -100
            for tok, mask in zip(input_ids, assistant_mask)
        ]
        attention_mask = [1] * len(input_ids)
        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "labels": labels,
        }

    rows = [_tokenize_one(r) for r in records]
    # Drop rows where the assistant range was clipped out by truncation
    # (e.g. an enormous OpenStax solution). Without any unmasked label
    # the loss is undefined for that example.
    rows = [r for r in rows if any(l != -100 for l in r["labels"])]
    return Dataset.from_list(rows)


def _data_collator(pad_id: int):
    """Right-pad to the longest sequence in a batch and pad labels with
    ``-100`` so masked positions stay masked."""
    import torch  # type: ignore

    def collate(features: List[Dict[str, List[int]]]):
        max_len = max(len(f["input_ids"]) for f in features)
        input_ids = []
        attn = []
        labels = []
        for f in features:
            pad = max_len - len(f["input_ids"])
            input_ids.append(f["input_ids"] + [pad_id] * pad)
            attn.append(f["attention_mask"] + [0] * pad)
            labels.append(f["labels"] + [-100] * pad)
        return {
            "input_ids": torch.tensor(input_ids, dtype=torch.long),
            "attention_mask": torch.tensor(attn, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
        }

    return collate


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="train/configs/qwen25_3b_lora.yaml")
    ap.add_argument(
        "--max-train",
        type=int,
        default=None,
        help="trim train set to N examples (smoke run)",
    )
    ap.add_argument(
        "--max-val",
        type=int,
        default=None,
        help="trim val set to N examples (smoke run)",
    )
    ap.add_argument(
        "--smoke",
        action="store_true",
        help="run 1 epoch on tiny subset for plumbing verification",
    )
    args = ap.parse_args(argv)

    repo = Path(__file__).resolve().parent.parent
    cfg_path = (repo / args.config) if not Path(args.config).is_absolute() else Path(args.config)
    cfg = _load_config(cfg_path)

    seed = int(cfg.get("seed", 4010))
    _set_seed(seed)

    # --- imports ---
    import torch  # type: ignore
    from transformers import (  # type: ignore
        AutoModelForCausalLM,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
    )
    from peft import LoraConfig, get_peft_model, TaskType  # type: ignore

    base_model = cfg["base_model"]
    output_dir = repo / cfg["output_dir"]
    data_dir = repo / cfg["data_dir"]
    max_seq_length = int(cfg["max_seq_length"])

    print(f"[train] base_model      = {base_model}")
    print(f"[train] output_dir      = {output_dir}")
    print(f"[train] data_dir        = {data_dir}")
    print(f"[train] max_seq_length  = {max_seq_length}")
    print(f"[train] cuda_available  = {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"[train] cuda_device     = {torch.cuda.current_device()} "
              f"({torch.cuda.get_device_name(0)})")

    # --- tokenizer ---
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # --- data ---
    train_records = _read_jsonl(data_dir / "train.jsonl")
    val_records = _read_jsonl(data_dir / "val.jsonl")
    if args.smoke:
        train_records = train_records[:32]
        val_records = val_records[:8]
    if args.max_train is not None:
        train_records = train_records[: args.max_train]
    if args.max_val is not None:
        val_records = val_records[: args.max_val]
    print(f"[train] train records   = {len(train_records)}")
    print(f"[train] val records     = {len(val_records)}")

    train_ds = _build_dataset(train_records, tokenizer, max_seq_length)
    val_ds = _build_dataset(val_records, tokenizer, max_seq_length)
    print(f"[train] tokenised train = {len(train_ds)}")
    print(f"[train] tokenised val   = {len(val_ds)}")

    # --- model + LoRA ---
    dtype = torch.bfloat16 if cfg.get("bf16", True) else (
        torch.float16 if cfg.get("fp16", False) else torch.float32
    )
    print(f"[train] compute dtype   = {dtype}")
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=dtype,
        trust_remote_code=True,
    )
    if cfg.get("gradient_checkpointing", True):
        model.gradient_checkpointing_enable()
        # When grad-ckpt is on, we must not cache key/values during the
        # forward pass (Trainer warns and silently caches anyway in some
        # transformers versions, hurting throughput). Disable explicitly.
        model.config.use_cache = False

    lora_cfg = LoraConfig(
        r=int(cfg["lora_r"]),
        lora_alpha=int(cfg["lora_alpha"]),
        lora_dropout=float(cfg["lora_dropout"]),
        bias="none",
        task_type=TaskType.CAUSAL_LM,
        target_modules=list(cfg["target_modules"]),
    )
    model = get_peft_model(model, lora_cfg)
    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    n_total = sum(p.numel() for p in model.parameters())
    print(f"[train] LoRA trainable  = {n_trainable:,} / {n_total:,} "
          f"({100*n_trainable/n_total:.3f}%)")

    # --- training arguments ---
    epochs = 1 if args.smoke else float(cfg["num_train_epochs"])
    targs_kwargs: Dict[str, Any] = dict(
        output_dir=str(output_dir),
        num_train_epochs=epochs,
        per_device_train_batch_size=int(cfg["per_device_train_batch_size"]),
        per_device_eval_batch_size=int(cfg["per_device_eval_batch_size"]),
        gradient_accumulation_steps=int(cfg["gradient_accumulation_steps"]),
        learning_rate=float(cfg["learning_rate"]),
        weight_decay=float(cfg.get("weight_decay", 0.0)),
        warmup_ratio=float(cfg.get("warmup_ratio", 0.0)),
        lr_scheduler_type=str(cfg.get("lr_scheduler_type", "cosine")),
        logging_steps=int(cfg.get("logging_steps", 20)),
        save_strategy=str(cfg.get("save_strategy", "epoch")),
        save_total_limit=int(cfg.get("save_total_limit", 2)),
        bf16=bool(cfg.get("bf16", True)),
        fp16=bool(cfg.get("fp16", False)),
        gradient_checkpointing=bool(cfg.get("gradient_checkpointing", True)),
        report_to=cfg.get("report_to", []) or [],
        seed=seed,
        dataloader_num_workers=2,
        remove_unused_columns=False,
    )
    # eval_strategy was renamed from `evaluation_strategy` in
    # transformers 4.41; `eval_strategy` works on 4.41+ only. Fall back
    # to the old name on older releases.
    eval_strategy = str(cfg.get("eval_strategy", "epoch"))
    try:
        targs = TrainingArguments(eval_strategy=eval_strategy, **targs_kwargs)
    except TypeError:
        targs = TrainingArguments(evaluation_strategy=eval_strategy, **targs_kwargs)

    trainer = Trainer(
        model=model,
        args=targs,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=_data_collator(tokenizer.pad_token_id),
    )
    print("[train] starting fit ...")
    train_result = trainer.train()
    print(f"[train] train_runtime   = {train_result.metrics.get('train_runtime'):.1f} s")
    print(f"[train] train_loss      = {train_result.metrics.get('train_loss'):.4f}")

    eval_metrics = trainer.evaluate()
    print(f"[train] eval_loss       = {eval_metrics.get('eval_loss'):.4f}")

    output_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    # Also dump the metrics for the report later.
    (output_dir / "train_metrics.json").write_text(
        json.dumps(
            {
                "train_runtime": train_result.metrics.get("train_runtime"),
                "train_loss": train_result.metrics.get("train_loss"),
                "eval_loss": eval_metrics.get("eval_loss"),
                "n_train": len(train_ds),
                "n_val": len(val_ds),
                "config": cfg,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[train] saved adapter to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
