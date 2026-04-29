from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple


def cosine_similarity(left: Dict[str, float], right: Dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    dot = sum(value * right.get(term, 0.0) for term, value in left.items())
    if dot <= 0.0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def tfidf_vector(terms: Counter[str], idf: Dict[str, float]) -> Dict[str, float]:
    vec: Dict[str, float] = {}
    for term, count in terms.items():
        if count <= 0:
            continue
        vec[term] = (1.0 + math.log(float(count))) * idf.get(term, 0.0)
    return vec


def build_idf(term_sets: Iterable[Iterable[str]], doc_count: int) -> Dict[str, float]:
    df: Counter[str] = Counter()
    for terms in term_sets:
        df.update(set(terms))
    return {term: math.log((doc_count + 1.0) / (count + 1.0)) + 1.0 for term, count in df.items()}


def overlap_score(query_features: Dict[str, Any], doc_features: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    reasons: Dict[str, Any] = {}
    score = 0.0
    for key, weight in (
        ("chapter", 0.5),
        ("method_family", 2.0),
        ("procedure", 2.5),
        ("task_type", 1.5),
        ("parameter", 1.5),
    ):
        qv = query_features.get(key)
        dv = doc_features.get(key)
        if qv and qv != "unknown" and qv == dv:
            score += weight
            reasons[key] = qv

    for key, weight in (
        ("formula_patterns", 2.0),
        ("assumptions", 0.8),
        ("symbols", 0.2),
    ):
        qset = set(query_features.get(key, []) or [])
        dset = set(doc_features.get(key, []) or [])
        common = sorted(qset & dset)
        if common:
            score += weight * len(common)
            reasons[key] = common[:10]

    qproc = query_features.get("procedure")
    dproc = doc_features.get("procedure")
    qfamily = query_features.get("method_family")
    dfamily = doc_features.get("method_family")
    if qproc and qproc != "unknown":
        if qproc == dproc:
            score += 4.0
            reasons["procedure_exact_boost"] = qproc
        elif qfamily and qfamily != "unknown" and qfamily == dfamily:
            score += 1.2
            reasons["method_family_boost"] = qfamily

    qpatterns = set(query_features.get("formula_patterns", []) or [])
    dpatterns = set(doc_features.get("formula_patterns", []) or [])
    if qpatterns and qpatterns & dpatterns:
        score += 3.0
        reasons["formula_exact_boost"] = sorted(qpatterns & dpatterns)[:10]

    # Keep simple-regression and multiple-regression procedures from
    # dominating each other when the query carries a clear regression level.
    qreg = str(qfamily or "")
    dreg = str(dfamily or "")
    if qreg.startswith("multiple_regression") and dreg.startswith("simple_regression"):
        score -= 3.0
        reasons["regression_level_penalty"] = "simple_candidate_for_multiple_query"
    if qreg.startswith("simple_regression") and dreg.startswith("multiple_regression"):
        score -= 2.0
        reasons["regression_level_penalty"] = "multiple_candidate_for_simple_query"

    qtask = query_features.get("task_type")
    dtask = doc_features.get("task_type")
    if qtask == "confidence_interval" and dtask == "hypothesis_test":
        score -= 1.8
        reasons["task_mismatch_penalty"] = "test_candidate_for_interval_query"
    if qtask == "sample_size" and dtask != "sample_size":
        score -= 1.0
        reasons["task_mismatch_penalty"] = "non_sample_size_candidate"
    if qproc == "two_proportion_z" and dproc == "one_proportion_z":
        score -= 4.0
        reasons["proportion_level_penalty"] = "one_proportion_candidate_for_two_proportion_query"
    if qproc == "one_proportion_z" and dproc == "two_proportion_z":
        score -= 2.0
        reasons["proportion_level_penalty"] = "two_proportion_candidate_for_one_proportion_query"
    if qproc == "pooled_t_test" and dproc == "welch_t_test":
        score -= 2.0
        reasons["variance_assumption_penalty"] = "welch_candidate_for_pooled_query"
    if qproc == "model_selection_indicator_press" and dproc == "overall_or_partial_f_test":
        score -= 3.5
        reasons["model_selection_penalty"] = "inference_candidate_for_model_selection_query"
    return score, reasons


def final_score(vector_score: float, overlap: float) -> float:
    return (0.50 * vector_score) + (0.50 * min(max(overlap, 0.0) / 24.0, 1.0))


def rerank(
    query_features: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    *,
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    rescored: List[Dict[str, Any]] = []
    for candidate in candidates:
        overlap, reasons = overlap_score(query_features, candidate["features"])
        out = dict(candidate)
        out["overlap_score"] = round(overlap, 6)
        out["overlap_reasons"] = reasons
        out["score"] = round(final_score(float(candidate.get("vector_score", 0.0)), overlap), 6)
        rescored.append(out)
    rescored.sort(key=lambda item: (-float(item["score"]), -float(item["overlap_score"]), str(item["id"])))
    return rescored[:top_k]
