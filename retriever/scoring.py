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
        ("target_parameter", 3.0),
        ("sample_structure", 3.0),
        ("inference_action", 2.0),
        ("distribution_family", 1.5),
        ("assumption_profile", 2.0),
        ("model_structure", 2.5),
    ):
        qv = query_features.get(key)
        dv = doc_features.get(key)
        if qv and qv != "unknown" and qv == dv:
            score += weight
            reasons[key] = qv

    for key, weight in (
        ("formula_patterns", 2.0),
        ("intent_flags", 2.5),
        ("concept_tags", 0.25),
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

    qtarget = str(query_features.get("target_parameter") or "")
    dtarget = str(doc_features.get("target_parameter") or "")
    qsample = str(query_features.get("sample_structure") or "")
    dsample = str(doc_features.get("sample_structure") or "")
    qaction = str(query_features.get("inference_action") or "")
    daction = str(doc_features.get("inference_action") or "")
    qassumption = str(query_features.get("assumption_profile") or "")
    dassumption = str(doc_features.get("assumption_profile") or "")
    qmodel = str(query_features.get("model_structure") or "")
    dmodel = str(doc_features.get("model_structure") or "")

    if qtarget and qtarget != "unknown" and dtarget and dtarget != "unknown" and qtarget != dtarget:
        severe_pairs = {
            ("mean", "variance"),
            ("variance", "mean"),
            ("proportion", "mean"),
            ("mean", "proportion"),
            ("categorical_distribution", "categorical_association"),
            ("categorical_association", "categorical_distribution"),
            ("correlation", "regression_slope"),
            ("regression_slope", "correlation"),
            ("regression_model", "regression_slope"),
        }
        penalty = 5.0 if (qtarget, dtarget) in severe_pairs else 2.0
        score -= penalty
        reasons["target_conflict_penalty"] = f"{qtarget}_query_vs_{dtarget}_candidate"

    if qsample and qsample != "unknown" and dsample and dsample != "unknown" and qsample != dsample:
        severe_pairs = {
            ("paired", "two_independent"),
            ("two_independent", "paired"),
            ("one_sample", "two_independent"),
            ("two_independent", "one_sample"),
            ("categorical_table", "one_sample"),
            ("one_sample", "categorical_table"),
            ("simple_regression", "multiple_regression"),
            ("multiple_regression", "simple_regression"),
            ("paired_quantitative", "simple_regression"),
        }
        penalty = 4.5 if (qsample, dsample) in severe_pairs else 2.0
        score -= penalty
        reasons["sample_structure_penalty"] = f"{qsample}_query_vs_{dsample}_candidate"

    if qaction == "confidence_interval" and daction == "hypothesis_test":
        score -= 1.8
        reasons["action_penalty"] = "test_candidate_for_interval_query"
    if qaction == "power" and daction not in {"power", "sample_size"}:
        score -= 2.0
        reasons["action_penalty"] = "non_power_candidate_for_power_query"

    if qassumption == "known_sigma" and dproc in {"one_sample_t_mean", "pooled_t_test", "welch_t_test"}:
        score -= 3.5
        reasons["assumption_penalty"] = "estimated_sigma_candidate_for_known_sigma_query"
    if qassumption == "unknown_sigma" and dproc == "one_sample_z_mean":
        score -= 3.0
        reasons["assumption_penalty"] = "known_sigma_candidate_for_unknown_sigma_query"
    if qassumption == "equal_variance" and dproc == "welch_t_test":
        score -= 3.5
        reasons["assumption_penalty"] = "welch_candidate_for_equal_variance_query"
    if qassumption == "unequal_variance" and dproc == "pooled_t_test":
        score -= 4.0
        reasons["assumption_penalty"] = "pooled_candidate_for_unequal_variance_query"

    if qmodel and qmodel not in {"none", "unknown"} and dmodel and dmodel not in {"none", "unknown"} and qmodel != dmodel:
        if qmodel in {"model_selection", "matrix_least_squares", "overall_partial_f"}:
            score -= 3.0
            reasons["model_structure_penalty"] = f"{qmodel}_query_vs_{dmodel}_candidate"

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
    if qproc == "nhst_decision" and dproc in {"fisher_significance_test", "critical_region_power"}:
        score -= 3.0
        reasons["decision_penalty"] = f"{dproc}_candidate_for_nhst_decision_query"
    if qproc == "fisher_significance_test" and dproc == "nhst_decision":
        score -= 1.5
        reasons["decision_penalty"] = "decision_candidate_for_fisher_evidence_query"

    qflags = set(query_features.get("intent_flags", []) or [])
    dflags = set(doc_features.get("intent_flags", []) or [])
    if qflags and qflags & dflags:
        score += 2.5 * len(qflags & dflags)
        reasons["intent_exact_boost"] = sorted(qflags & dflags)[:10]

    qconcepts = set(query_features.get("concept_tags", []) or [])
    dconcepts = set(doc_features.get("concept_tags", []) or [])
    if qconcepts and qconcepts & dconcepts:
        score += 0.25 * len(qconcepts & dconcepts)
        reasons["concept_exact_boost"] = sorted(qconcepts & dconcepts)[:10]

    flag_penalties = {
        "known_sigma": {"one_sample_t_mean", "pooled_t_test", "critical_region"},
        "unknown_sigma": {"sign_test", "one_sample_z_mean"},
        "variance_target": {"one_sample_z_mean", "one_sample_t_mean", "mean_interval", "pooled_t_test", "welch_t_test", "paired_t"},
        "mean_target": {"chi_square_variance", "variance_ratio_f_test"},
        "sign_test_cue": {"one_sample_t_mean", "chi_square_gof", "fisher_significance_test"},
        "variance_ratio_cue": {"fisher_significance_test", "one_sample_z_mean", "prediction_interval", "pooled_t_test"},
        "nhst_decision_cue": {"fisher_significance_test", "critical_region_power"},
        "one_proportion_cue": {"one_sample_z_mean", "chi_square_gof", "chi_square_independence"},
        "two_independent_binary": {"one_proportion_z", "chi_square_gof", "chi_square_independence"},
        "gof_cue": {"one_proportion_z", "two_proportion_z", "chi_square_independence", "slope_t_test"},
        "independence_cue": {"one_proportion_z", "two_proportion_z", "chi_square_gof"},
        "paired_design": {"pooled_t_test", "welch_t_test", "wilcoxon_rank_sum"},
        "independent_groups": {"paired_t", "wilcoxon_signed_rank"},
        "signed_rank_cue": {"wilcoxon_rank_sum", "paired_t", "sign_test"},
        "rank_sum_cue": {"paired_t", "wilcoxon_signed_rank"},
        "welch_cue": {"pooled_t_test", "variance_ratio_f_test", "chi_square_variance"},
        "pooled_cue": {"welch_t_test"},
        "slr_diagnostics": {"critical_region_power", "model_selection_indicator_press"},
        "mlr_cue": {"slope_t_test", "regression_prediction_interval"},
        "mlr_matrix_cue": {"slope_t_test", "regression_prediction_interval", "overall_or_partial_f_test"},
        "mlr_inference_cue": {"slope_t_test", "model_selection_indicator_press"},
        "model_selection_cue": {"overall_or_partial_f_test", "slope_t_test"},
        "indicator_cue": {"slope_t_test", "overall_or_partial_f_test"},
        "correlation_cue": {"slope_t_test", "regression_prediction_interval"},
    }
    for flag, conflicting_procs in flag_penalties.items():
        if flag in qflags and dproc in conflicting_procs and flag not in dflags:
            score -= 3.0
            reasons.setdefault("intent_conflict_penalty", []).append(flag)
    return score, reasons


def final_score(vector_score: float, overlap: float) -> float:
    return (0.35 * vector_score) + (0.65 * min(max(overlap, 0.0) / 28.0, 1.0))


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
