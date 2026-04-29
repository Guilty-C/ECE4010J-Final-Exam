from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
FORMULA_PATH = ROOT / "ontology" / "ve401_formula_patterns.json"
TAXONOMY_PATH = ROOT / "ontology" / "ve401_method_taxonomy.json"

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\\-]*|\\[A-Za-z]+|\d+(?:\.\d+)?")
SYMBOL_RE = re.compile(
    r"\\(?:bar|hat)?\s*[A-Za-z]+|\\(?:mu|sigma|alpha|beta|chi|lambda)|"
    r"\b(?:xbar|mu|sigma|alpha|beta|df|p-value|pvalue|n|s\^2|s|z|t|F|r\^2|R\^2)\b"
)

STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "there", "where", "when",
    "what", "which", "into", "over", "under", "then", "than", "use", "using", "has",
    "have", "had", "are", "was", "were", "been", "being", "sample", "random",
}

INTENT_RULES = (
    ("known_sigma", (r"long[-\s]run.*(?:spread|sigma|standard deviation)", r"historical.*(?:spread|sigma)", r"calibration.*(?:spread|sigma)", r"process sigma is known", r"known standard deviation")),
    ("unknown_sigma", (r"sample spread", r"sample standard deviation", r"estimated from the same sample", r"spread must be estimated")),
    ("variance_target", (r"spread itself", r"variation itself", r"variability itself", r"population spread", r"population variance", r"process variation", r"not the center")),
    ("sign_test_cue", (r"very asymmetric", r"middle observation", r"count observations on each side", r"claimed value")),
    ("variance_ratio_cue", (r"two normal .*sample variances", r"compared only through their sample variances", r"first .* more variable", r"ratio of two normal population variances")),
    ("np_power", (r"cutoff.*before data", r"chance.*rule fires", r"power curve", r"type i.*type ii", r"alpha.*beta")),
    ("nhst_multiple_testing", (r"large family of.*tests", r"only .*results.*reported", r"only .*significant", r"selective reporting", r"many tests", r"twenty hypotheses")),
    ("two_independent_binary", (r"two independent.*(?:binary|yes/no|success|proportion)", r"success chances differ", r"combined estimate under equality", r"x1\s*/\s*n1", r"x_?1.*n_?1.*x_?2.*n_?2")),
    ("paired_design", (r"same .*twice", r"within units?", r"each unit appears twice", r"same subjects?.*both", r"paired differences")),
    ("signed_rank_cue", (r"rank.*absolute", r"absolute sizes", r"signs? restored", r"w plus|w minus|w\+|w-", r"paired differences.*rank")),
    ("rank_sum_cue", (r"two unrelated.*ordinal", r"two independent small samples", r"replace measurements by ranks", r"compare locations using ranks")),
    ("welch_cue", (r"very different.*spreads", r"spread.*three times", r"unbalanced sample sizes", r"without sharing.*variance", r"without.*common variance", r"s1 squared over n1 plus s2 squared over n2")),
    ("pooled_cue", (r"common spread", r"common variance", r"one combined spread", r"sp squared", r"equal variances")),
    ("slr_cue", (r"one x", r"one predictor", r"line is fit", r"fitted tilt", r"simple regression")),
    ("slr_diagnostics", (r"residual.*bend", r"residual.*fan", r"funnel shape", r"curvature", r"straight-line error model")),
    ("mean_response_cue", (r"average response", r"expected response", r"all units at that x", r"not a new individual")),
    ("prediction_cue", (r"one future", r"future observed", r"new individual", r"include.*noise")),
    ("lack_fit_cue", (r"several y values.*each x", r"repeatability error", r"systematic curvature", r"split.*residual sum of squares")),
    ("mlr_cue", (r"several predictors", r"design matrix", r"coefficient vector", r"x times a coefficient", r"with other predictors retained")),
    ("mlr_matrix_cue", (r"hat matrix", r"projection matrix", r"diagonal.*leverage", r"creates fitted values")),
    ("mlr_inference_cue", (r"predictors help jointly", r"extra block of variables", r"nested in a larger", r"coefficient.*standard error")),
    ("model_selection_cue", (r"deleted observations", r"deleted-residual", r"validation-style", r"overfit", r"search over many predictors", r"poor deleted", r"press")),
    ("indicator_cue", (r"categorical factor", r"baseline group", r"dummy variables?", r"shift intercepts", r"product term", r"group-specific slopes")),
)


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _normalise_text(record: Dict[str, Any]) -> str:
    return "\n".join(
        str(record.get(k, ""))
        for k in ("question_text", "solution_text", "thought_text", "source")
        if record.get(k)
    )


def _tokens(text: str) -> List[str]:
    out: List[str] = []
    for match in TOKEN_RE.finditer(text.lower()):
        token = match.group(0).strip("\\")
        if len(token) < 2 or token in STOPWORDS:
            continue
        out.append(token)
    return out


def _contains_keyword(text_lower: str, keyword: str) -> bool:
    return keyword.lower().replace("\\\\", "\\") in text_lower


def _match_formula_patterns(text: str, patterns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    text_lower = text.lower()
    hits: List[Dict[str, Any]] = []
    for pattern in patterns:
        pattern_id = str(pattern.get("id", ""))
        if (
            pattern_id.startswith("chi_square_variance")
            and "chi" not in text_lower
            and not _contains_keyword(text_lower, "test sigma")
            and not _contains_keyword(text_lower, "test whether sigma")
            and not _contains_keyword(text_lower, "test variance")
            and not ("s^2" in text_lower and "sigma" in text_lower)
            and not ("s squared" in text_lower and "sigma" in text_lower)
        ):
            continue
        keyword_score = 0
        regex_score = 0
        for keyword in pattern.get("keywords", []):
            if _contains_keyword(text_lower, keyword):
                keyword_score += 2
        for regex in pattern.get("regex", []):
            try:
                if re.search(regex, text, flags=re.IGNORECASE):
                    regex_score += 3
            except re.error:
                continue
        score = keyword_score + regex_score
        # Avoid broad false positives such as generic "test" or regression
        # residual variance s^2. A formula hit needs either strong keyword
        # evidence or a formula cue plus a method-specific keyword cue.
        if not (keyword_score >= 4 or (keyword_score >= 2 and regex_score >= 3) or regex_score >= 6):
            score = 0
        if score:
            hit = dict(pattern)
            hit["match_score"] = score
            hits.append(hit)
    hits.sort(key=lambda x: (-int(x["match_score"]), str(x["id"])))
    return hits


def _chapter_from_record(record: Dict[str, Any]) -> str:
    source = str(record.get("source", ""))
    rec_id = str(record.get("id", ""))
    match = re.search(r"ch(?:apter)?[_\s-]*(\d{1,2})", source + " " + rec_id, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _taxonomy_matches(text: str, taxonomy: Dict[str, Any], key: str) -> List[str]:
    text_lower = text.lower()
    matched: List[str] = []
    for name, keywords in taxonomy.get(key, {}).items():
        if any(_contains_keyword(text_lower, str(keyword)) for keyword in keywords):
            matched.append(name)
    return sorted(matched)


def _symbols(text: str) -> List[str]:
    found = {m.group(0).replace(" ", "") for m in SYMBOL_RE.finditer(text)}
    return sorted(found)


def _intent_flags(text: str) -> List[str]:
    text_lower = text.lower()
    flags = []
    for name, patterns in INTENT_RULES:
        if any(re.search(pattern, text_lower, flags=re.IGNORECASE) for pattern in patterns):
            flags.append(name)
    return sorted(set(flags))


def extract_features(
    record: Dict[str, Any],
    *,
    formula_ontology: Dict[str, Any] | None = None,
    method_taxonomy: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    formula_ontology = formula_ontology or load_json(FORMULA_PATH)
    method_taxonomy = method_taxonomy or load_json(TAXONOMY_PATH)
    text = _normalise_text(record)
    chapter = _chapter_from_record(record)
    chapter_hints = method_taxonomy.get("chapter_hints", {}).get(chapter, [])
    task_matches = _taxonomy_matches(text, method_taxonomy, "task_type_keywords")
    parameter_matches = _taxonomy_matches(text, method_taxonomy, "parameter_keywords")
    pattern_hits = _match_formula_patterns(text, formula_ontology.get("patterns", []))
    intent_flags = _intent_flags(text)
    best = pattern_hits[0] if pattern_hits else {}
    if pattern_hits and task_matches:
        preferred_tasks = ["hypothesis_test", "confidence_interval", "regression_inference", "regression_modeling"]
        preferred_task = next((task for task in preferred_tasks if task in task_matches), task_matches[0])
        task_best = next((hit for hit in pattern_hits if hit.get("task_type") == preferred_task), None)
        if task_best and int(task_best.get("match_score", 0)) >= int(best.get("match_score", 0)) - 3:
            best = task_best

    method_family = str(best.get("method_family") or (chapter_hints[0] if chapter_hints else "unknown"))
    procedure = str(best.get("procedure") or (chapter_hints[1] if len(chapter_hints) > 1 else method_family))
    task_type = str(best.get("task_type") or (task_matches[0] if task_matches else "unknown"))
    parameter = str(best.get("parameter") or (parameter_matches[0] if parameter_matches else "unknown"))

    if "known_sigma" in intent_flags and procedure in {"unknown", "one_sample_t_mean", "mean_interval"}:
        method_family = "interval_estimation"
        procedure = "one_sample_z_mean"
        parameter = "mu"
    if "unknown_sigma" in intent_flags and procedure in {"unknown", "sign_test", "one_sample_z_mean", "mean_interval"}:
        method_family = "interval_estimation"
        procedure = "one_sample_t_mean"
        parameter = "mu"
    if "variance_target" in intent_flags and procedure in {"unknown", "mean_interval", "one_sample_z_mean", "one_sample_t_mean"}:
        method_family = "single_sample_tests"
        procedure = "chi_square_variance"
        parameter = "sigma_squared"
    if "sign_test_cue" in intent_flags and procedure in {"unknown", "one_sample_t_mean", "fisher_significance_test"}:
        method_family = "nonparametric_median"
        procedure = "sign_test"
        task_type = "hypothesis_test"
        parameter = "median"
    if "variance_ratio_cue" in intent_flags and procedure in {"unknown", "one_sample_z_mean", "fisher_significance_test", "prediction_interval"}:
        method_family = "two_variance_comparison"
        procedure = "variance_ratio_f_test"
        task_type = "hypothesis_test"
        parameter = "sigma_ratio"
    if "signed_rank_cue" in intent_flags and procedure in {"wilcoxon_rank_sum", "paired_t", "sign_test", "unknown"}:
        method_family = "nonparametric_median"
        procedure = "wilcoxon_signed_rank"
        parameter = "median"
    if "two_independent_binary" in intent_flags and procedure in {"one_proportion_z", "chi_square_gof", "chi_square_independence", "unknown"}:
        method_family = "proportion_inference"
        procedure = "two_proportion_z"
        parameter = "p_difference"
    if "welch_cue" in intent_flags and procedure in {"pooled_t_test", "variance_ratio_f_test", "chi_square_variance", "unknown"}:
        method_family = "two_mean_comparison"
        procedure = "welch_t_test"
        parameter = "mu_difference"
    if "model_selection_cue" in intent_flags and procedure in {"overall_or_partial_f_test", "unknown"}:
        method_family = "multiple_regression_iii"
        procedure = "model_selection_indicator_press"
        task_type = "model_selection"
    if "indicator_cue" in intent_flags and procedure in {"unknown", "slope_t_test", "overall_or_partial_f_test"}:
        method_family = "multiple_regression_iii"
        procedure = "model_selection_indicator_press"
        task_type = "model_selection"
    if "mlr_inference_cue" in intent_flags and procedure in {"slope_t_test", "model_selection_indicator_press", "unknown"}:
        method_family = "multiple_regression_ii"
        procedure = "overall_or_partial_f_test"
        parameter = "beta"
    if "lack_fit_cue" in intent_flags and procedure in {"unknown", "slope_t_test", "model_selection_indicator_press"}:
        method_family = "simple_regression_ii"
        procedure = "lack_of_fit"
        task_type = "regression_modeling"
        parameter = "model_adequacy"
    if "nhst_multiple_testing" in intent_flags and procedure in {"unknown", "fisher_significance_test"}:
        method_family = "nhst"
        procedure = "nhst_decision"
        task_type = "interpretation"

    assumptions: List[str] = []
    for hit in pattern_hits:
        assumptions.extend(str(x) for x in hit.get("assumptions", []))

    token_counts = Counter(_tokens(text))
    return {
        "id": str(record.get("id", "")),
        "chapter": chapter,
        "method_family": method_family,
        "procedure": procedure,
        "task_type": task_type,
        "parameter": parameter,
        "assumptions": sorted(set(assumptions)),
        "formula_patterns": [str(hit["id"]) for hit in pattern_hits],
        "intent_flags": intent_flags,
        "symbols": _symbols(text),
        "tokens": dict(token_counts),
    }


def feature_terms(features: Dict[str, Any]) -> Counter[str]:
    terms: Counter[str] = Counter()
    for token, count in features.get("tokens", {}).items():
        terms[f"tok:{token}"] += int(count)
    weighted_singletons = {
        "chapter": 5,
        "method_family": 8,
        "procedure": 10,
        "task_type": 7,
        "parameter": 7,
    }
    for key, weight in weighted_singletons.items():
        value = features.get(key)
        if value and value != "unknown":
            terms[f"{key}:{value}"] += weight
    for key, weight in (("formula_patterns", 12), ("intent_flags", 10), ("assumptions", 5), ("symbols", 3)):
        for value in features.get(key, []) or []:
            terms[f"{key}:{value}"] += weight
    return terms


def iter_jsonl_records(input_path: Path) -> Iterable[Dict[str, Any]]:
    files = [input_path] if input_path.is_file() else sorted(input_path.glob("exercises_ch*.jsonl"))
    for path in files:
        if not re.search(r"exercises_ch(?:1[5-9]|2\d|30)\.jsonl$", path.name):
            continue
        with path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                record["_jsonl_path"] = path.as_posix()
                record["_jsonl_line"] = line_no
                yield record
