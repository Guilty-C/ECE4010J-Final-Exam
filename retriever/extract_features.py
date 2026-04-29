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
    ("known_sigma", (r"long[-\s]run.*(?:spread|sigma|standard deviation)", r"long[-\s]established population standard deviation", r"historical.*(?:spread|sigma|standard deviation)", r"stable.*(?:spread|sigma|standard deviation)", r"certified population standard deviation", r"calibration.*(?:spread|sigma|standard deviation)", r"process (?:sigma|variation) is known", r"known (?:common )?standard deviation", r"known population standard deviation", r"population standard deviation .*certified")),
    ("unknown_sigma", (r"population spread is not known", r"sample spread", r"sample standard deviation", r"estimated from the same sample", r"spread must be estimated", r"xbar and s\b", r"sample mean.*sample standard deviation")),
    ("variance_target", (r"standard deviations? differ", r"true standard deviation", r"population standard deviation", r"standard deviation .*itself", r"spread itself", r"variation itself", r"variability itself", r"population variance", r"process variation", r"true variance", r"sample variance", r"s squared", r"s\^2", r"sigma squared", r"sigma\^2", r"not the center", r"mean .*irrelevant")),
    ("mean_target", (r"process center", r"true center", r"underlying center", r"sample mean", r"true mean", r"population mean", r"population means", r"confidence interval for the mean", r"interval .* for .*mean", r"for the mean\b", r"difference in means", r"difference between means", r"question is still about .*means", r"mean exceeds", r"mean is larger", r"mean response", r"average response", r"average difference", r"average paired response", r"mu1 minus mu2", r"mu_?1\s*-\s*mu_?2", r"not for the variability")),
    ("median_target", (r"median", r"typical .*larger", r"distribution-free", r"rank-based", r"signed procedure")),
    ("sign_test_cue", (r"very asymmetric", r"highly skewed", r"middle observation", r"count .*above and below", r"above and below .*median", r"magnitudes .*discarded", r"sign-only", r"only .*signs?", r"claimed median")),
    ("variance_ratio_cue", (r"two .*standard deviations? differ", r"two .*variances? differ", r"two independent sample variances", r"two normal .*sample variances", r"compare .*variability .*two", r"compare .*spreads .*two", r"relative variability", r"compared only through their sample variances", r"first .* more variable", r"ratio of two normal population variances", r"ratio of .*variances", r"ratio .*standard deviations")),
    ("nhst_decision_cue", (r"\b(?:reject|fail to reject)\b", r"rejection region", r"statistical conclusion", r"conclusion .*hypothesis", r"test conclusion", r"significant at", r"statistically significant at", r"compare .*p[-\s]?value.*alpha", r"p[-\s]?value .* (?:less|greater) than .*alpha", r"p[-\s]?value .*<.*alpha", r"p[-\s]?value .*>.*alpha")),
    ("np_power", (r"cutoff.*before data", r"fixed.*alpha", r"significance level is fixed", r"probability of rejection", r"chance.*rule fires", r"detect .*with probability", r"sample size.*power", r"power curve", r"type[-\s]?i.*type[-\s]?ii", r"alpha.*beta", r"bad batches.*accepted", r"good batches.*rejected", r"good batch .*rejected", r"bad batch .*pass", r"two risks", r"rule boundary")),
    ("nhst_multiple_testing", (r"large family of.*tests", r"only .*results.*reported", r"only .*significant", r"selective reporting", r"many tests", r"twenty hypotheses")),
    ("one_proportion_cue", (r"one proportion", r"success probability", r"successes out of n", r"x successes out of n", r"defective fraction", r"defect(?:ive)? rate", r"failure fraction", r"population failure fraction", r"underlying success probability")),
    ("two_independent_binary", (r"two independent.*(?:binary|yes/no|success|proportion|treatment|survey|group)", r"two .*defect rates", r"two .*complaint rates", r"before and after.*two independent samples", r"success chances differ", r"success probability is higher", r"change in proportions", r"difference in proportions", r"combined estimate under equality", r"x1\s*/\s*n1", r"x_?1.*n_?1.*x_?2.*n_?2")),
    ("gof_cue", (r"goodness[-\s]?of[-\s]?fit", r"fit .*distribution", r"fit .*specified probabilities", r"expected proportions", r"model is plausible", r"adequate model", r"counts .*categories", r"frequencies for", r"grouped into bins", r"binned", r"poisson model", r"normal distribution", r"die-like", r"full vector of category probabilities")),
    ("independence_cue", (r"contingency table", r"cross[-\s]?classifies", r"row and column totals", r"rows? .* columns?", r"two categorical variables", r"associated", r"depends on", r"treatment group by outcome", r"survival .*treatment", r"machine type and defect category")),
    ("paired_design", (r"same .*twice", r"same subject", r"same specimen", r"before[-\s]?after", r"pre[-\s]?post", r"matched pairs?", r"paired design", r"within units?", r"each (?:unit|participant|patient|specimen).*both", r"each measured with both", r"each (?:unit|participant|patient|specimen).*once under.*once under", r"each unit appears twice", r"same subjects?.*both", r"paired differences", r"paired response", r"blocking information")),
    ("independent_groups", (r"two independent", r"independent groups", r"unrelated groups", r"different groups", r"not paired", r"pairing is not present", r"unrelated samples")),
    ("signed_rank_cue", (r"signed[-\s]?rank", r"rank.*absolute", r"absolute sizes", r"signs? restored", r"w plus|w minus|w\+|w-", r"paired differences.*rank", r"zero differences.*discarded")),
    ("rank_sum_cue", (r"rank[-\s]?sum", r"two unrelated.*ordinal", r"two independent small samples", r"replace measurements by ranks", r"compare locations using ranks", r"rank-based two-sample", r"rank-based alternative to the two-sample", r"one population tends to produce larger")),
    ("welch_cue", (r"unequal[-\s]?variance", r"not be assumed equal", r"no equality of variances", r"no common variance", r"do not pool", r"very different.*spreads", r"different sample spreads", r"differ substantially", r"unequal spreads", r"spread.*three times", r"unbalanced sample sizes", r"without sharing.*variance", r"without.*common variance", r"satterthwaite", r"approximate degree of freedom", r"s1 squared over n1 plus s2 squared over n2")),
    ("pooled_cue", (r"pooled", r"common spread", r"common variance", r"one combined spread", r"sp squared", r"equal variances", r"equal variance.*assumed", r"comparable spreads", r"variability .*common")),
    ("slr_cue", (r"one x", r"one predictor", r"single predictor", r"line is fit", r"straight[-\s]?line regression", r"fitted tilt", r"simple regression", r"slope", r"intercept")),
    ("slr_diagnostics", (r"residual.*bend", r"residual.*fan", r"funnel shape", r"curvature", r"straight-line error model")),
    ("mean_response_cue", (r"mean[-\s]?response interval", r"expected response at", r"all units at that x", r"not a new individual")),
    ("prediction_cue", (r"prediction interval", r"single future measurement", r"one future", r"future observed", r"future error", r"new individual", r"new response", r"future value at", r"new predictor vector", r"include.*noise")),
    ("lack_fit_cue", (r"several y values.*each x", r"repeatability error", r"systematic curvature", r"split.*residual sum of squares")),
    ("mlr_cue", (r"multiple regression", r"several predictors", r"all predictors", r"four predictors", r"design matrix", r"coefficient vector", r"x times a coefficient", r"with other predictors retained")),
    ("mlr_matrix_cue", (r"design matrix", r"model matrix", r"least[-\s]?squares estimator", r"used in least squares", r"hat matrix", r"projection matrix", r"diagonal.*leverage", r"creates fitted values", r"fitted values", r"residual mean zero", r"x beta", r"\(x'?x\)\^-?1", r"normal equations")),
    ("mlr_inference_cue", (r"predictors help jointly", r"at least one non[-\s]?intercept", r"all slopes.*zero", r"all regression slopes", r"linear combination", r"coefficient.*test", r"overall test", r"overall f", r"partial f", r"extra sum of squares", r"extra block of variables", r"nested in a larger", r"reduced .*full", r"full model", r"compared to a model", r"improves the fit", r"coefficient.*standard error", r"ssr.*sse")),
    ("model_selection_cue", (r"deleted observations", r"leave[-\s]?one[-\s]?out", r"predictive performance", r"deleted-residual", r"validation-style", r"overfit", r"search over many predictors", r"poor deleted", r"press", r"adjusted r", r"ordinary r squared", r"number of predictors", r"candidate regression models", r"model selection")),
    ("indicator_cue", (r"group indicator", r"categorical factor", r"baseline group", r"dummy variables?", r"shift intercepts", r"product term", r"group-specific slopes")),
    ("correlation_cue", (r"correlation", r"pearson", r"population correlation", r"sample correlation", r"\br\s*=", r"fisher transformation", r"fisher z", r"bivariate normal")),
    ("regression_assumptions_cue", (r"regression assumptions?", r"linear(?:ity)? assumption", r"normal errors?", r"constant variance", r"independent errors?", r"extrapolation", r"inside the design region", r"multicollinearity", r"causal claim", r"not causal", r"random error")),
    ("residual_diagnostics_cue", (r"residual diagnostics?", r"residual plot", r"residuals?", r"outlier", r"influence", r"leverage", r"constant variance", r"curvature", r"funnel")),
)

PROCEDURE_STRUCTURES = {
    "one_sample_z_mean": ("mean", "one_sample", "z"),
    "one_sample_t_mean": ("mean", "one_sample", "t"),
    "one_sample_t_test": ("mean", "one_sample", "t"),
    "chi_square_variance": ("variance", "one_sample", "chi_square"),
    "variance_ratio_f_test": ("variance", "two_independent", "f"),
    "pooled_t_test": ("mean", "two_independent", "t"),
    "welch_t_test": ("mean", "two_independent", "t"),
    "paired_t": ("mean", "paired", "t"),
    "sign_test": ("median", "one_sample_or_paired", "binomial"),
    "wilcoxon_signed_rank": ("median", "paired", "rank_based"),
    "wilcoxon_rank_sum": ("median", "two_independent", "rank_based"),
    "one_proportion_z": ("proportion", "one_sample", "z"),
    "two_proportion_z": ("proportion", "two_independent", "z"),
    "two_sample_z_mean": ("mean", "two_independent", "z"),
    "chi_square_gof": ("categorical_distribution", "one_sample", "chi_square"),
    "chi_square_independence": ("categorical_association", "categorical_table", "chi_square"),
    "fisher_correlation_z": ("correlation", "paired_quantitative", "z"),
    "slope_t_test": ("regression_slope", "simple_regression", "t"),
    "regression_prediction_interval": ("regression_prediction", "simple_regression", "t"),
    "lack_of_fit": ("regression_diagnostic", "simple_regression", "f"),
    "model_matrix_least_squares": ("regression_model", "multiple_regression", "matrix"),
    "model_matrix": ("regression_model", "multiple_regression", "matrix"),
    "overall_or_partial_f_test": ("regression_model", "multiple_regression", "f"),
    "model_selection_indicator_press": ("regression_model", "multiple_regression", "model_selection"),
    "regression_assumptions": ("regression_assumptions", "regression", "diagnostic"),
    "residual_diagnostics": ("regression_diagnostic", "regression", "diagnostic"),
    "fisher_significance_test": ("p_value", "generic_test", "p_value"),
    "nhst_decision": ("hypothesis_decision", "generic_test", "decision"),
    "critical_region_power": ("power", "generic_test", "power"),
}

PROCEDURE_ALIASES = {
    "critical_region": "critical_region_power",
    "power": "critical_region_power",
    "p_value_evidence": "fisher_significance_test",
    "p_value_interpretation": "fisher_significance_test",
    "significance_test": "fisher_significance_test",
    "significance_decision": "nhst_decision",
    "one_sample_t_test": "one_sample_t_mean",
    "chi_square_variance_test": "chi_square_variance",
    "rank_sum": "wilcoxon_rank_sum",
    "fisher_correlation": "fisher_correlation_z",
    "prediction_interval": "regression_prediction_interval",
    "least_squares": "slope_t_test",
    "slope_inference": "slope_t_test",
    "overall_f_test": "overall_or_partial_f_test",
    "partial_f_test": "overall_or_partial_f_test",
    "model_matrix": "model_matrix_least_squares",
    "hat_matrix": "model_matrix_least_squares",
    "indicator_variables": "model_selection_indicator_press",
    "model_selection": "model_selection_indicator_press",
}

ANCHOR_METHOD_FAMILIES = {
    "one_sample_z_mean": "interval_estimation",
    "one_sample_t_mean": "interval_estimation",
    "chi_square_variance": "single_sample_tests",
    "two_sample_z_mean": "two_mean_comparison",
    "pooled_t_test": "two_mean_comparison",
    "welch_t_test": "two_mean_comparison",
    "paired_t": "two_mean_comparison",
    "variance_ratio_f_test": "two_variance_comparison",
    "chi_square_gof": "categorical_inference",
    "chi_square_independence": "categorical_inference",
    "fisher_significance_test": "fisher_significance_test",
    "nhst_decision": "nhst",
    "critical_region_power": "neyman_pearson",
    "model_matrix_least_squares": "multiple_regression_i",
    "overall_or_partial_f_test": "multiple_regression_ii",
    "regression_prediction_interval": "simple_regression_ii",
    "regression_assumptions": "regression_diagnostics",
    "residual_diagnostics": "regression_diagnostics",
    "model_selection_indicator_press": "multiple_regression_iii",
}

CONCEPT_RULES = (
    ("p_value_interpretation", (r"p[-\s]?value", r"surprising .*under the null", r"if the null (?:model )?were true", r"not .*probability.*null", r"observed statistic.*under the null")),
    ("confidence_interval_interpretation", (r"confidence interval", r"repeated[-\s]?sampling", r"fixed parameter", r"coverage", r"not .*probability.*parameter", r"confidence level")),
    ("r_squared_interpretation", (r"r squared|r\^2", r"explained variation", r"proportion of variation", r"ordinary r squared")),
    ("model_fit_not_truth", (r"not .*truth", r"does not prove", r"model fit", r"high r squared.*not", r"prediction guarantee")),
    ("correlation_not_causation", (r"correlation.*causation", r"not causal", r"causal claim", r"observational")),
    ("type_i_type_ii_error", (r"type[-\s]?i", r"type[-\s]?ii", r"\balpha\b", r"\bbeta\b", r"power", r"miss rate", r"mistake rate")),
    ("regression_assumptions", (r"regression assumptions?", r"normal errors?", r"constant variance", r"independent errors?", r"extrapolation", r"design region", r"multicollinearity", r"random error")),
    ("residual_diagnostics", (r"residual diagnostics?", r"residual plot", r"residuals?", r"outlier", r"influence", r"leverage", r"curvature", r"funnel")),
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
        found = False
        for keyword in keywords:
            keyword_text = str(keyword)
            if len(keyword_text) <= 2:
                found = bool(re.search(rf"\b{re.escape(keyword_text.lower())}\b", text_lower))
            else:
                found = _contains_keyword(text_lower, keyword_text)
            if found:
                break
        if found:
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
    if "paired_design" in flags and re.search(r"rather than before[-\s]?after|two different groups|rather than .*same subject|rather than .*paired", text_lower):
        flags.remove("paired_design")
    if "known_sigma" in flags and re.search(r"no known population standard deviation|no historical sigma|historical sigma .*not available|population standard deviation.*not known|sigma .*not known|spread is not known", text_lower):
        flags.remove("known_sigma")
    if "known_sigma" in flags and "unknown_sigma" in flags and not re.search(r"population (?:spread|standard deviation|sigma) .*not known|sigma .*not known|spread is not known", text_lower):
        flags.remove("unknown_sigma")
    if "mean_target" in flags and "variance_target" in flags and re.search(r"population (?:spread|standard deviation|sigma) .*not known", text_lower):
        flags.remove("variance_target")
    if "known_sigma" in flags and "mean_target" in flags and "variance_target" in flags:
        flags.remove("variance_target")
    return sorted(set(flags))


def _normalise_procedure(procedure: str) -> str:
    return PROCEDURE_ALIASES.get(procedure, procedure)


def _anchor_solution_procedure(record: Dict[str, Any]) -> str:
    if not str(record.get("id", "")).startswith("anchor_"):
        return ""
    solution = str(record.get("solution_text", "")).lower()
    for procedure in sorted(PROCEDURE_STRUCTURES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(procedure.lower())}\b", solution):
            return _normalise_procedure(procedure)
    return ""


def _concept_tags(text: str) -> List[str]:
    text_lower = text.lower()
    tags = []
    for name, patterns in CONCEPT_RULES:
        if any(re.search(pattern, text_lower, flags=re.IGNORECASE) for pattern in patterns):
            tags.append(name)
    return sorted(set(tags))


def _inference_action(text_lower: str, task_type: str, intent_flags: List[str]) -> str:
    if "model_selection_cue" in intent_flags:
        return "model_selection"
    if "np_power" in intent_flags or re.search(r"\bpower\b|sample size|detect .*probability|alpha.*beta|type[-\s]?ii", text_lower):
        return "power"
    if re.search(r"confidence interval|uncertainty interval|\binterval\b|two-sided uncertainty|confidence statement|\bbound\b|margin of error", text_lower):
        return "confidence_interval"
    if re.search(r"test|reject|p[-\s]?value|hypothesis|claim|evidence|significance|asks whether|question asks whether|question is whether", text_lower):
        return "hypothesis_test"
    if "interpret" in text_lower or "interpretation" in text_lower:
        return "interpretation"
    if task_type and task_type != "unknown":
        return task_type
    return "unknown"


def _structure_features(
    text: str,
    procedure: str,
    task_type: str,
    parameter: str,
    intent_flags: List[str],
) -> Dict[str, str]:
    text_lower = text.lower()
    target, sample_structure, distribution_family = PROCEDURE_STRUCTURES.get(procedure, ("unknown", "unknown", "unknown"))

    if "variance_target" in intent_flags:
        target = "variance"
    if "mean_target" in intent_flags and target in {"unknown", "p_value", "hypothesis_decision"}:
        target = "mean"
    if "median_target" in intent_flags:
        target = "median"
    if "one_proportion_cue" in intent_flags:
        target = "proportion"
    if "two_independent_binary" in intent_flags:
        target = "proportion"
        sample_structure = "two_independent"
    if "gof_cue" in intent_flags:
        target = "categorical_distribution"
        sample_structure = "one_sample"
    if "independence_cue" in intent_flags:
        target = "categorical_association"
        sample_structure = "categorical_table"
    if "correlation_cue" in intent_flags:
        target = "correlation"
        sample_structure = "paired_quantitative"
    if "paired_design" in intent_flags:
        sample_structure = "paired"
    elif "independent_groups" in intent_flags and sample_structure in {"unknown", "paired", "one_sample_or_paired"}:
        sample_structure = "two_independent"
    if "mlr_cue" in intent_flags or "mlr_matrix_cue" in intent_flags or "mlr_inference_cue" in intent_flags or "model_selection_cue" in intent_flags or "indicator_cue" in intent_flags:
        sample_structure = "multiple_regression"
        if target in {"unknown", "regression_slope"}:
            target = "regression_model"
    elif "slr_cue" in intent_flags or "slr_diagnostics" in intent_flags or "prediction_cue" in intent_flags or "mean_response_cue" in intent_flags or "lack_fit_cue" in intent_flags:
        sample_structure = "simple_regression"
        if target == "unknown":
            target = "regression_slope"

    if parameter in {"sigma_squared", "sigma_ratio"}:
        target = "variance"
    elif parameter in {"mu", "mu_difference"} and "variance_ratio_cue" not in intent_flags:
        target = "mean"
    elif parameter in {"p", "p_difference"}:
        target = "proportion"
    elif parameter == "rho":
        target = "correlation"

    inference_action = _inference_action(text_lower, task_type, intent_flags)
    if distribution_family == "unknown":
        if "known_sigma" in intent_flags:
            distribution_family = "z"
        elif "variance_target" in intent_flags:
            distribution_family = "chi_square"
        elif "welch_cue" in intent_flags or "pooled_cue" in intent_flags or "unknown_sigma" in intent_flags:
            distribution_family = "t"
        elif "rank_sum_cue" in intent_flags or "signed_rank_cue" in intent_flags:
            distribution_family = "rank_based"

    assumption_profile = "unknown"
    if "known_sigma" in intent_flags:
        assumption_profile = "known_sigma"
    elif "welch_cue" in intent_flags:
        assumption_profile = "unequal_variance"
    elif "pooled_cue" in intent_flags:
        assumption_profile = "equal_variance"
    elif "unknown_sigma" in intent_flags:
        assumption_profile = "unknown_sigma"
    elif "variance_ratio_cue" in intent_flags:
        assumption_profile = "normal_variances"

    model_structure = "none"
    if "model_selection_cue" in intent_flags:
        model_structure = "model_selection"
    elif "indicator_cue" in intent_flags:
        model_structure = "indicator_interaction"
    elif "mlr_matrix_cue" in intent_flags:
        model_structure = "matrix_least_squares"
    elif "mlr_inference_cue" in intent_flags:
        model_structure = "overall_partial_f"
    elif sample_structure == "multiple_regression":
        model_structure = "multiple_regression"
    elif "lack_fit_cue" in intent_flags:
        model_structure = "lack_of_fit"
    elif "prediction_cue" in intent_flags or "mean_response_cue" in intent_flags:
        model_structure = "prediction_interval"
    elif sample_structure == "simple_regression":
        model_structure = "simple_regression"

    return {
        "target_parameter": target,
        "sample_structure": sample_structure,
        "inference_action": inference_action,
        "distribution_family": distribution_family,
        "assumption_profile": assumption_profile,
        "model_structure": model_structure,
    }


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
    procedure = _normalise_procedure(str(best.get("procedure") or (chapter_hints[1] if len(chapter_hints) > 1 else method_family)))
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
    if "variance_ratio_cue" in intent_flags and procedure in {"unknown", "one_sample_z_mean", "fisher_significance_test", "regression_prediction_interval", "chi_square_variance"}:
        method_family = "two_variance_comparison"
        procedure = "variance_ratio_f_test"
        task_type = "hypothesis_test"
        parameter = "sigma_ratio"
    if "variance_target" in intent_flags and procedure in {"unknown", "mean_interval", "one_sample_z_mean", "one_sample_t_mean"} and "mean_target" not in intent_flags and "variance_ratio_cue" not in intent_flags:
        method_family = "single_sample_tests"
        procedure = "chi_square_variance"
        parameter = "sigma_squared"
    if "mean_target" in intent_flags and procedure == "chi_square_variance":
        method_family = "interval_estimation"
        procedure = "one_sample_t_mean" if "unknown_sigma" in intent_flags else "one_sample_z_mean"
        parameter = "mu"
    if "sign_test_cue" in intent_flags and procedure in {"unknown", "one_sample_t_mean", "fisher_significance_test"}:
        method_family = "nonparametric_median"
        procedure = "sign_test"
        task_type = "hypothesis_test"
        parameter = "median"
    if "signed_rank_cue" in intent_flags and procedure in {"wilcoxon_rank_sum", "paired_t", "sign_test", "unknown"}:
        method_family = "nonparametric_median"
        procedure = "wilcoxon_signed_rank"
        parameter = "median"
    if "two_independent_binary" in intent_flags and procedure in {"one_proportion_z", "chi_square_gof", "chi_square_independence", "unknown"}:
        method_family = "proportion_inference"
        procedure = "two_proportion_z"
        parameter = "p_difference"
    if "one_proportion_cue" in intent_flags and procedure in {"unknown", "one_sample_z_mean", "fisher_significance_test"}:
        method_family = "proportion_inference"
        procedure = "one_proportion_z"
        parameter = "p"
    if "gof_cue" in intent_flags and procedure in {"unknown", "one_proportion_z", "two_proportion_z", "chi_square_independence", "slope_t_test"}:
        method_family = "categorical_inference"
        procedure = "chi_square_gof"
        task_type = "hypothesis_test"
        parameter = "category_probabilities"
    if "independence_cue" in intent_flags and procedure in {"unknown", "one_proportion_z", "two_proportion_z", "chi_square_gof", "fisher_significance_test"}:
        method_family = "categorical_inference"
        procedure = "chi_square_independence"
        task_type = "hypothesis_test"
        parameter = "association"
    if "independent_groups" in intent_flags and "mean_target" in intent_flags and "known_sigma" in intent_flags and procedure in {"unknown", "regression_prediction_interval", "one_sample_t_mean", "one_sample_z_mean"}:
        method_family = "two_mean_comparison"
        procedure = "two_sample_z_mean"
        parameter = "mu_difference"
    if "independent_groups" in intent_flags and "pooled_cue" in intent_flags and "mean_target" in intent_flags and procedure in {"unknown", "regression_prediction_interval", "one_sample_z_mean", "one_sample_t_mean", "chi_square_variance"}:
        method_family = "two_mean_comparison"
        procedure = "pooled_t_test"
        parameter = "mu_difference"
    if "independent_groups" in intent_flags and "welch_cue" in intent_flags and "mean_target" in intent_flags and procedure in {"unknown", "regression_prediction_interval", "one_sample_z_mean", "one_sample_t_mean", "chi_square_variance"}:
        method_family = "two_mean_comparison"
        procedure = "welch_t_test"
        parameter = "mu_difference"
    if "paired_design" in intent_flags and "signed_rank_cue" not in intent_flags and "sign_test_cue" not in intent_flags and procedure in {"unknown", "pooled_t_test", "welch_t_test", "one_sample_t_mean", "mean_interval", "wilcoxon_rank_sum"}:
        method_family = "two_mean_comparison"
        procedure = "paired_t"
        parameter = "mu_difference"
    if "rank_sum_cue" in intent_flags and procedure in {"unknown", "paired_t", "wilcoxon_signed_rank", "pooled_t_test", "welch_t_test"}:
        method_family = "nonparametric_median"
        procedure = "wilcoxon_rank_sum"
        parameter = "median"
    if "pooled_cue" in intent_flags and procedure in {"unknown", "welch_t_test", "chi_square_variance", "one_sample_t_mean"} and "variance_ratio_cue" not in intent_flags:
        method_family = "two_mean_comparison"
        procedure = "pooled_t_test"
        parameter = "mu_difference"
    if "welch_cue" in intent_flags and procedure in {"pooled_t_test", "variance_ratio_f_test", "chi_square_variance", "unknown"}:
        method_family = "two_mean_comparison"
        procedure = "welch_t_test"
        parameter = "mu_difference"
    if "correlation_cue" in intent_flags and procedure in {"unknown", "slope_t_test", "regression_prediction_interval", "one_sample_t_mean"}:
        method_family = "correlation"
        procedure = "fisher_correlation_z"
        parameter = "rho"
    if "mlr_matrix_cue" in intent_flags and procedure in {"unknown", "slope_t_test", "overall_or_partial_f_test", "model_selection_indicator_press"}:
        method_family = "multiple_regression_i"
        procedure = "model_matrix_least_squares"
        task_type = "regression_modeling"
        parameter = "beta"
    if "prediction_cue" in intent_flags and procedure in {"unknown", "slope_t_test", "one_sample_t_mean", "fisher_correlation_z"}:
        method_family = "simple_regression_ii"
        procedure = "regression_prediction_interval"
        task_type = "regression_modeling"
        parameter = "prediction"
    if "model_selection_cue" in intent_flags and procedure in {"overall_or_partial_f_test", "slope_t_test", "unknown"}:
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
    if "residual_diagnostics_cue" in intent_flags and procedure == "unknown":
        method_family = "regression_diagnostics"
        procedure = "residual_diagnostics"
        task_type = "diagnose_error"
        parameter = "model_adequacy"
    if "regression_assumptions_cue" in intent_flags and procedure == "unknown":
        method_family = "regression_diagnostics"
        procedure = "regression_assumptions"
        task_type = "interpretation"
        parameter = "model_adequacy"
    if "nhst_multiple_testing" in intent_flags and procedure in {"unknown", "fisher_significance_test"}:
        method_family = "nhst"
        procedure = "nhst_decision"
        task_type = "interpretation"
    if "np_power" in intent_flags and procedure in {"unknown", "fisher_significance_test", "nhst_decision"}:
        method_family = "neyman_pearson"
        procedure = "critical_region_power"
        task_type = "critical_region"
    if "nhst_decision_cue" in intent_flags and "np_power" not in intent_flags and procedure in {"unknown", "fisher_significance_test", "critical_region_power"}:
        method_family = "nhst"
        procedure = "nhst_decision"
        task_type = "interpretation"
    anchor_procedure = _anchor_solution_procedure(record)
    if anchor_procedure:
        procedure = anchor_procedure
        method_family = ANCHOR_METHOD_FAMILIES.get(anchor_procedure, method_family)
    procedure = _normalise_procedure(procedure)

    assumptions: List[str] = []
    for hit in pattern_hits:
        assumptions.extend(str(x) for x in hit.get("assumptions", []))

    token_counts = Counter(_tokens(text))
    structure = _structure_features(text, procedure, task_type, parameter, intent_flags)
    concept_tags = _concept_tags(text)
    return {
        "id": str(record.get("id", "")),
        "chapter": chapter,
        "method_family": method_family,
        "procedure": procedure,
        "task_type": task_type,
        "parameter": parameter,
        **structure,
        "assumptions": sorted(set(assumptions)),
        "formula_patterns": [str(hit["id"]) for hit in pattern_hits],
        "intent_flags": intent_flags,
        "concept_tags": concept_tags,
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
        "target_parameter": 10,
        "sample_structure": 10,
        "inference_action": 8,
        "distribution_family": 7,
        "assumption_profile": 8,
        "model_structure": 9,
    }
    for key, weight in weighted_singletons.items():
        value = features.get(key)
        if value and value != "unknown":
            terms[f"{key}:{value}"] += weight
    for key, weight in (("formula_patterns", 12), ("intent_flags", 10), ("concept_tags", 1), ("assumptions", 5), ("symbols", 3)):
        for value in features.get(key, []) or []:
            terms[f"{key}:{value}"] += weight
    return terms


def iter_jsonl_records(input_path: Path) -> Iterable[Dict[str, Any]]:
    files = [input_path] if input_path.is_file() else sorted(
        {
            *input_path.glob("exercises_ch*.jsonl"),
            *input_path.glob("*_anchor_retrieval.jsonl"),
        }
    )
    for path in files:
        if not (
            re.search(r"exercises_ch(?:1[5-9]|2\d|30)\.jsonl$", path.name)
            or re.search(r"ch(?:1[5-9]|2\d|30).*_anchor_retrieval\.jsonl$", path.name)
        ):
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
