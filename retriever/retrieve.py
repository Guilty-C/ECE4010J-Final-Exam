"""Phase D retriever (plan §6 step D1).

Combines a tag inverted index with BM25-Okapi keyword scoring over
``data/corpus.jsonl`` and weights every hit by its ``source_priority`` so the
VE401-local gold templates float above OpenStax / Hendrycks fillers.

Two public modes
----------------

``retrieve(query, top_k=10)``
    Classify the query first (Phase C) to obtain candidate test cards, take
    the union of records that classify to those cards, then rerank by BM25
    overlap with the query and source-priority weight.

``retrieve_for_card(card_id, top_k=10)``
    Return records that classify to ``card_id`` directly, ranked by source
    priority and BM25 overlap with the card's own title + tags. This is the
    target of the Phase D acceptance test (plan §6 step D3): every card_id
    must surface at least one matching template.

The whole module is dependency-free — BM25Okapi is implemented inline so we
don't need ``rank_bm25`` (kept commented in ``requirements.txt``).
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = ROOT / "data" / "corpus.jsonl"

from classifier.decision_tree import (  # noqa: E402  (after path/const setup)
    all_card_ids,
    card_meta,
    classify,
    classify_record,
)


# --------------------------------------------------------------------------- #
# Tokeniser                                                                    #
# --------------------------------------------------------------------------- #

# A tiny stop-list — we keep math/Greek and statistical jargon. Words that add
# no retrieval signal (and inflate document length, lowering BM25 idf weight)
# are removed; "the" / "a" / "is" together account for ~6% of every doc.
_STOPWORDS = frozenset(
    """
    a an the of in on at by for to from with as is are was were be been being
    this that these those it its they them their there here which who whom whose
    or and but if then else than so such not no nor do does did done has have
    had having will would shall should can could may might must just into out
    up down over under between among also each per very more most less few many
    about above below upon some any all both either neither one two three
    when while where why how what we you your our us he she his her him me my i
    """.split()
)

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z\-_']*|[0-9]+(?:\.[0-9]+)?")


def _tokenise(text: str) -> List[str]:
    if not text:
        return []
    out: List[str] = []
    for m in _TOKEN_RE.finditer(text.lower()):
        tok = m.group(0)
        if len(tok) < 2:
            continue
        if tok in _STOPWORDS:
            continue
        out.append(tok)
    return out


# --------------------------------------------------------------------------- #
# BM25-Okapi                                                                   #
# --------------------------------------------------------------------------- #


class _BM25:
    """Plain BM25-Okapi (Robertson/Sparck-Jones) — no smoothing tricks.

    score(q, d) = sum_t idf(t) * (tf_t,d * (k1+1)) / (tf_t,d + k1*(1 - b + b*|d|/avgdl))
    idf(t) = ln((N - df_t + 0.5) / (df_t + 0.5) + 1)   # +1 keeps idf non-negative
    """

    __slots__ = ("docs", "doc_len", "avgdl", "df", "idf", "N", "k1", "b")

    def __init__(self, docs: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75):
        self.docs = docs
        self.doc_len = [len(d) for d in docs]
        self.N = len(docs)
        self.avgdl = (sum(self.doc_len) / self.N) if self.N else 0.0
        self.k1 = k1
        self.b = b

        df: Dict[str, int] = {}
        for d in docs:
            for t in set(d):
                df[t] = df.get(t, 0) + 1
        self.df = df
        self.idf = {
            t: math.log(((self.N - n + 0.5) / (n + 0.5)) + 1.0)
            for t, n in df.items()
        }

    def score(self, query_tokens: Sequence[str], doc_idx: int) -> float:
        if not query_tokens:
            return 0.0
        d = self.docs[doc_idx]
        if not d:
            return 0.0
        dl = self.doc_len[doc_idx]
        # tf for tokens in this doc
        tf: Dict[str, int] = {}
        for t in d:
            tf[t] = tf.get(t, 0) + 1
        score = 0.0
        denom_norm = self.k1 * (1.0 - self.b + self.b * (dl / self.avgdl if self.avgdl else 0.0))
        for q in query_tokens:
            if q not in tf:
                continue
            idf = self.idf.get(q, 0.0)
            f = tf[q]
            score += idf * (f * (self.k1 + 1.0)) / (f + denom_norm)
        return score

    def score_all(self, query_tokens: Sequence[str]) -> List[float]:
        return [self.score(query_tokens, i) for i in range(self.N)]


# --------------------------------------------------------------------------- #
# Retriever                                                                    #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RetrievalHit:
    rank: int
    score: float
    bm25: float
    priority_weight: float
    card_id: str
    record: dict
    matched_tokens: Tuple[str, ...] = field(default=())

    @property
    def record_id(self) -> str:
        return str(self.record.get("id", ""))

    @property
    def source(self) -> str:
        return str(self.record.get("source", ""))

    def as_dict(self) -> dict:
        return {
            "rank": self.rank,
            "score": round(self.score, 4),
            "bm25": round(self.bm25, 4),
            "priority_weight": self.priority_weight,
            "card_id": self.card_id,
            "record_id": self.record_id,
            "source": self.source,
            "matched_tokens": list(self.matched_tokens),
        }


# Higher is better; mirrors plan §5.3 (priority 1 = VE401 gold, oversampled 3x).
_PRIORITY_WEIGHT = {1: 2.0, 2: 1.0, 3: 0.5}


def _record_text_for_index(rec: dict) -> str:
    """The text we feed BM25. Question + solution + rubric + trail-of-thought
    so that solution-bearing templates (which we want to retrieve) score
    higher than question-only fillers when the query mentions a *recipe*."""
    parts: List[str] = []
    if rec.get("question"):
        parts.append(str(rec["question"]))
    for s in rec.get("solution_steps") or []:
        if isinstance(s, dict) and s.get("content"):
            parts.append(str(s["content"]))
    for r in rec.get("rubric") or []:
        if isinstance(r, dict) and r.get("point"):
            parts.append(str(r["point"]))
    if rec.get("trail_of_thought"):
        parts.append(str(rec["trail_of_thought"]))
    return " \n ".join(parts)


class Retriever:
    """Loads the corpus once, classifies every record into a card bucket,
    builds BM25 + tag/slide-ref inverted indexes."""

    def __init__(self, corpus_path: Path = CORPUS_PATH):
        self.corpus_path = corpus_path
        self.records: List[dict] = []
        self.doc_tokens: List[List[str]] = []
        self.bm25: Optional[_BM25] = None
        # card_id -> list of record indices (top-1 classification bucket).
        self.by_card: Dict[str, List[int]] = {c: [] for c in all_card_ids()}
        # card_id -> list of indices where the card appeared in top-3 (broader bucket).
        self.by_card_top3: Dict[str, List[int]] = {c: [] for c in all_card_ids()}
        # tag -> indices (record-level topic_tag inverted index, for plan §6 D1).
        self.by_tag: Dict[str, List[int]] = {}
        # slide_ref -> indices.
        self.by_slide_ref: Dict[int, List[int]] = {}
        # source_priority -> indices.
        self.by_priority: Dict[int, List[int]] = {1: [], 2: [], 3: []}

        self._load()

    # ---- index build ----------------------------------------------------- #

    def _load(self) -> None:
        if not self.corpus_path.exists():
            raise FileNotFoundError(
                f"corpus.jsonl not found at {self.corpus_path}; "
                f"run `python -m extractors.merge_corpus` first."
            )
        with self.corpus_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                self.records.append(json.loads(line))

        for i, rec in enumerate(self.records):
            self.doc_tokens.append(_tokenise(_record_text_for_index(rec)))

            # tag inverted index
            for t in rec.get("topic_tags") or []:
                self.by_tag.setdefault(str(t), []).append(i)

            # slide_ref inverted index
            for s in rec.get("slide_refs") or []:
                try:
                    self.by_slide_ref.setdefault(int(s), []).append(i)
                except (ValueError, TypeError):
                    continue

            # priority bucket
            p = int(rec.get("source_priority") or 3)
            self.by_priority.setdefault(p, []).append(i)

            # card classification (top-1 + top-3)
            hits = classify_record(rec, top_k=3)
            if hits:
                self.by_card[hits[0].card_id].append(i)
                for h in hits:
                    self.by_card_top3[h.card_id].append(i)

        self.bm25 = _BM25(self.doc_tokens)

    # ---- card-driven retrieval (plan §6 D3 acceptance) ------------------ #

    def retrieve_for_card(
        self,
        card_id: str,
        top_k: int = 10,
        *,
        prefer_with_solutions: bool = True,
        include_top3_fallback: bool = True,
    ) -> List[RetrievalHit]:
        """Pull templates that classify to ``card_id``.

        Ranking key (descending):
            1. has-solution flag (when ``prefer_with_solutions``);
            2. source_priority weight (VE401 gold > OpenStax > Hendrycks);
            3. BM25 against the card's own title + tags + slide cite;
            4. record id (deterministic tiebreak).
        """
        meta = card_meta(card_id)
        if meta is None:
            raise KeyError(f"unknown card_id: {card_id}")

        # primary bucket: top-1 matches
        cand_idx = list(self.by_card.get(card_id, []))
        if include_top3_fallback and len(cand_idx) < top_k:
            seen = set(cand_idx)
            for i in self.by_card_top3.get(card_id, []):
                if i not in seen:
                    cand_idx.append(i)
                    seen.add(i)

        # tag/slide overlap fallback (still empty? widen via card.tags ∩ topic_tags or slide_refs ∩ slide_refs)
        if not cand_idx:
            seen: set = set()
            for tag in meta.get("tags", []):
                for i in self.by_tag.get(tag, []):
                    if i not in seen:
                        cand_idx.append(i)
                        seen.add(i)
            for s in meta.get("slide_refs", []):
                for i in self.by_slide_ref.get(int(s), []):
                    if i not in seen:
                        cand_idx.append(i)
                        seen.add(i)

        if not cand_idx:
            return []

        # BM25 query = card title + tags + "ch{N}" so chapter-aligned text wins on ties
        query_text = " ".join(
            [meta.get("title", "")]
            + list(meta.get("tags", []))
            + [f"chapter {meta.get('chapter','')}"]
        )
        return self._rank(cand_idx, query_text, top_k, prefer_with_solutions, primary_card=card_id)

    # ---- query-driven retrieval ----------------------------------------- #

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        *,
        cards_top_k: int = 3,
        prefer_with_solutions: bool = True,
    ) -> List[RetrievalHit]:
        """Free-text retrieval.

        Pipeline: classify(query) -> union(by_card[top_k cards]) -> BM25 rerank.
        If the classifier returns nothing (rare; query has no card-y vocab) we
        fall back to BM25 over the full corpus, still weighted by priority.
        """
        if not query or not query.strip():
            return []

        card_hits = classify(query, top_k=cards_top_k)
        cand_idx: List[int] = []
        seen: set = set()
        primary_card = card_hits[0].card_id if card_hits else ""

        for ch in card_hits:
            for i in self.by_card.get(ch.card_id, []):
                if i not in seen:
                    cand_idx.append(i)
                    seen.add(i)

        # If we still have very few candidates, widen via top-3 buckets.
        if len(cand_idx) < top_k * 2:
            for ch in card_hits:
                for i in self.by_card_top3.get(ch.card_id, []):
                    if i not in seen:
                        cand_idx.append(i)
                        seen.add(i)

        # Last-ditch fallback: BM25 over the whole corpus.
        if not cand_idx:
            cand_idx = list(range(len(self.records)))

        return self._rank(cand_idx, query, top_k, prefer_with_solutions, primary_card=primary_card)

    # ---- ranking core --------------------------------------------------- #

    def _rank(
        self,
        cand_idx: Sequence[int],
        query_text: str,
        top_k: int,
        prefer_with_solutions: bool,
        *,
        primary_card: str = "",
    ) -> List[RetrievalHit]:
        assert self.bm25 is not None
        q_tokens = _tokenise(query_text)
        q_set = set(q_tokens)

        scored: List[Tuple[float, float, int, dict, List[str], int, str]] = []
        # tuple shape: (priority_weight, bm25, has_sol, rec, matched, idx, card_id)

        for i in cand_idx:
            rec = self.records[i]
            bm = self.bm25.score(q_tokens, i)
            pw = _PRIORITY_WEIGHT.get(int(rec.get("source_priority") or 3), 0.5)
            has_sol = 1 if (rec.get("solution_steps") or []) else 0
            matched = sorted(t for t in q_set if t in self.doc_tokens[i])
            # which card did this record classify to (top-1)?
            owner_card = ""
            for cid, idxs in self.by_card.items():
                if i in idxs:
                    owner_card = cid
                    break
            scored.append((pw, bm, has_sol, rec, matched, i, owner_card))

        # composite score: weighted sum exposes both BM25 ordering and
        # priority preference even on small candidate pools where one factor
        # would otherwise dominate.
        def composite(t: Tuple) -> Tuple:
            pw, bm, has_sol, rec, matched, idx, owner = t
            sol_bonus = 0.0 if not prefer_with_solutions else (0.5 if has_sol else 0.0)
            card_bonus = 0.25 if (primary_card and owner == primary_card) else 0.0
            comp = bm * pw + sol_bonus + card_bonus
            # secondary keys for deterministic tie-break
            return (-comp, -pw, -has_sol, str(rec.get("id", "")))

        scored.sort(key=composite)

        out: List[RetrievalHit] = []
        for rank, (pw, bm, has_sol, rec, matched, idx, owner) in enumerate(scored[:top_k], start=1):
            sol_bonus = 0.5 if (prefer_with_solutions and has_sol) else 0.0
            card_bonus = 0.25 if (primary_card and owner == primary_card) else 0.0
            comp = bm * pw + sol_bonus + card_bonus
            out.append(
                RetrievalHit(
                    rank=rank,
                    score=comp,
                    bm25=bm,
                    priority_weight=pw,
                    card_id=owner or primary_card or "",
                    record=rec,
                    matched_tokens=tuple(matched),
                )
            )
        return out


# --------------------------------------------------------------------------- #
# Module-level singleton helpers                                               #
# --------------------------------------------------------------------------- #

_INSTANCE: Optional[Retriever] = None


def get_retriever() -> Retriever:
    """Lazy singleton — first call costs ~1-2 s for the 3,597-doc corpus
    (classifying every record); subsequent calls are free."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = Retriever()
    return _INSTANCE


def retrieve(query: str, top_k: int = 10, **kwargs) -> List[RetrievalHit]:
    return get_retriever().retrieve(query, top_k=top_k, **kwargs)


def retrieve_for_card(card_id: str, top_k: int = 10, **kwargs) -> List[RetrievalHit]:
    return get_retriever().retrieve_for_card(card_id, top_k=top_k, **kwargs)


__all__ = [
    "Retriever",
    "RetrievalHit",
    "get_retriever",
    "retrieve",
    "retrieve_for_card",
]
