"""Per-card render templates (plan §6 step E1/E3).

Each entry maps a ``card_id`` (from the Phase C taxonomy) to a small dict of
five Markdown segments. Segments may reference fields from the
:class:`solver.extract_givens.Givens` object via ``{key}`` placeholders;
missing values are surfaced as a literal ``?`` so the user sees what they
forgot to supply. The optional ``compute`` callable computes the test
statistic numerically using ``math`` only (no scipy) — it returns either
a float or ``None`` (insufficient givens).

We hand-author the five "core" cards in detail (card01 Z-test, card02
T-test, card03 χ²-variance, card12 paired-T, card15 χ²-GoF) — these are
the ones the Phase E E4 acceptance test exercises and the ones with the
broadest VE401 sample-final coverage. The other 20 cards get a
shape-correct skeleton with the test name, slide ref, and statistic
formula filled in symbolically; numerical evaluation for them is deferred
to a follow-up iteration (per the "ship smallest usable thing first"
rule).
"""
from __future__ import annotations

import math
from typing import Callable, Dict, Optional

# A thin alias so call sites don't import ``Givens`` here.
GivensDict = dict


# --------------------------------------------------------------------------- #
# Compute helpers (return None when a required given is missing)               #
# --------------------------------------------------------------------------- #


def _need(g: GivensDict, *keys: str) -> bool:
    raw = g.get("raw", g) if isinstance(g, dict) else {}
    for k in keys:
        if raw.get(k) is None:
            return False
    return True


def _r(g: GivensDict) -> dict:
    return g.get("raw", g) if isinstance(g, dict) else {}


def _z_one_sample(g: GivensDict) -> Optional[float]:
    r = _r(g)
    if not _need(g, "x_bar", "mu_0", "sigma", "n"):
        return None
    n = r["n"]
    if n <= 0:
        return None
    return (r["x_bar"] - r["mu_0"]) / (r["sigma"] / math.sqrt(n))


def _t_one_sample(g: GivensDict) -> Optional[float]:
    r = _r(g)
    if not _need(g, "x_bar", "mu_0", "s", "n"):
        return None
    n = r["n"]
    if n <= 0 or r["s"] == 0:
        return None
    return (r["x_bar"] - r["mu_0"]) / (r["s"] / math.sqrt(n))


def _chi2_variance(g: GivensDict) -> Optional[float]:
    r = _r(g)
    if not _need(g, "n"):
        return None
    n = r["n"]
    s2 = r.get("s_squared")
    if s2 is None and r.get("s") is not None:
        s2 = r["s"] ** 2
    sigma2_0 = r.get("sigma_0_squared")
    if sigma2_0 is None and r.get("sigma_0") is not None:
        sigma2_0 = r["sigma_0"] ** 2
    if sigma2_0 is None and r.get("sigma_squared") is not None:
        # Fallback: σ² used as σ_0² when no explicit subscript was given.
        sigma2_0 = r["sigma_squared"]
    if sigma2_0 is None and r.get("sigma") is not None:
        sigma2_0 = r["sigma"] ** 2
    if s2 is None or sigma2_0 in (None, 0):
        return None
    return (n - 1) * s2 / sigma2_0


def _paired_t(g: GivensDict) -> Optional[float]:
    r = _r(g)
    if not _need(g, "d_bar", "s", "n"):
        return None
    n = r["n"]
    if n <= 0 or r["s"] == 0:
        return None
    # H_0: mu_d = 0 (the VE401 default for "is there a paired difference")
    return r["d_bar"] / (r["s"] / math.sqrt(n))


def _chi2_gof(g: GivensDict) -> Optional[float]:
    """χ² = Σ (O_i - E_i)² / E_i.

    Only fires when ``observed_counts`` is non-empty AND a model probability
    vector can be inferred from the question text. Inferring the model
    automatically is unreliable, so for the smallest cut we just compute
    ``∑ O_i`` (= n) and emit the formula symbolically. The numerical χ²
    value is returned only if ``g["expected_counts"]`` is supplied.
    """
    r = _r(g)
    counts = g.get("observed_counts") if isinstance(g, dict) else None
    expected = g.get("expected_counts") if isinstance(g, dict) else None
    if not counts or not expected or len(counts) != len(expected):
        return None
    chi2 = 0.0
    for o, e in zip(counts, expected):
        if e <= 0:
            return None
        chi2 += (o - e) ** 2 / e
    return chi2


# --------------------------------------------------------------------------- #
# Template DB                                                                  #
# --------------------------------------------------------------------------- #


def _v(d: GivensDict, key: str, fmt: str = "{:g}") -> str:
    """Format a given for inline display, or return '?' if missing."""
    v = _r(d).get(key)
    if v is None:
        return "?"
    try:
        return fmt.format(v)
    except (TypeError, ValueError):
        return str(v)


def _tail_to_reject(tail: str, statistic: str = "z", alpha_label: str = "alpha") -> str:
    """Return a VE401-style rejection-region phrasing string.

    Uses the course-standard naming: ``z_{alpha/2}``, ``t_{alpha,nu}``,
    ``chi^2_{alpha/2,nu}``. The exact critical value table is left for the
    user / a follow-up scipy hookup.
    """
    sub = {"z": f"z_{{{alpha_label}/2}}", "z1": f"z_{{{alpha_label}}}"}
    if statistic == "z":
        if tail == "two-sided":
            return f"|z| > z_{{{alpha_label}/2}}"
        if tail == "right-tailed":
            return f"z > z_{{{alpha_label}}}"
        if tail == "left-tailed":
            return f"z < -z_{{{alpha_label}}}"
        return f"|z| > z_{{{alpha_label}/2}}"
    if statistic == "t":
        if tail == "two-sided":
            return f"|t| > t_{{{alpha_label}/2,\\,n-1}}"
        if tail == "right-tailed":
            return f"t > t_{{{alpha_label},\\,n-1}}"
        if tail == "left-tailed":
            return f"t < -t_{{{alpha_label},\\,n-1}}"
        return f"|t| > t_{{{alpha_label}/2,\\,n-1}}"
    if statistic == "chi2":
        if tail == "two-sided":
            return (
                f"chi^2 > chi^2_{{{alpha_label}/2,\\,n-1}}  or  "
                f"chi^2 < chi^2_{{1-{alpha_label}/2,\\,n-1}}"
            )
        if tail == "right-tailed":
            return f"chi^2 > chi^2_{{{alpha_label},\\,n-1}}"
        if tail == "left-tailed":
            return f"chi^2 < chi^2_{{1-{alpha_label},\\,n-1}}"
        return f"chi^2 > chi^2_{{{alpha_label}/2,\\,n-1}}"
    return f"|{statistic}| > critical value at level {alpha_label}"


# Each card defines the five Markdown segments; the renderer composes them
# into the final Markdown blob. The ``compute`` callable is optional.
TEMPLATES: Dict[str, dict] = {
    # --- card01: One-sample Z-test (sigma known) -------------------------- #
    "card01": {
        "name": "One-sample Z-test (sigma known)",
        "slide_refs": [436],
        "chapter": "19",
        "setup": (
            "Random sample from a normal population, **sigma is known** "
            "→ a one-sample Z-test is appropriate [slide 436]."
        ),
        "hypotheses_fmt": (
            "H_0: mu = {mu_0}  vs.  H_1: mu {alt_op} {mu_0}    ({tail})."
        ),
        "statistic": (
            "Under H_0,   Z = (X_bar - mu_0) / (sigma / sqrt(n))  ~  N(0, 1)."
        ),
        "computation_fmt": (
            "z = ({x_bar} - {mu_0}) / ({sigma} / sqrt({n})) = {z_val}"
        ),
        "decision_fmt": (
            "Reject H_0 if {reject_rule} (using a critical value at "
            "alpha = {alpha}). The p-value is computed from the standard "
            "normal CDF in the appropriate tail."
        ),
        "compute": _z_one_sample,
        "stat_symbol": "z",
        "stat_kind": "z",
    },
    # --- card02: One-sample T-test (sigma unknown) ------------------------ #
    "card02": {
        "name": "One-sample T-test (sigma unknown)",
        "slide_refs": [445],
        "chapter": "19",
        "setup": (
            "Random sample from a (near-)normal population, **sigma is "
            "unknown** so use a one-sample T-test [slide 445]. The test "
            "statistic has T_{n-1} under H_0."
        ),
        "hypotheses_fmt": (
            "H_0: mu = {mu_0}  vs.  H_1: mu {alt_op} {mu_0}    ({tail})."
        ),
        "statistic": (
            "Under H_0,   T = (X_bar - mu_0) / (S / sqrt(n))  ~  T_{n-1}."
        ),
        "computation_fmt": (
            "t = ({x_bar} - {mu_0}) / ({s} / sqrt({n})) = {t_val}"
        ),
        "decision_fmt": (
            "Reject H_0 if {reject_rule} (with df = n - 1 = {df}, "
            "alpha = {alpha}). Quote the two- or one-tail p-value from a "
            "T-table or scipy.stats.t."
        ),
        "compute": _t_one_sample,
        "stat_symbol": "t",
        "stat_kind": "t",
    },
    # --- card03: Chi-square test for one variance ------------------------- #
    "card03": {
        "name": "Chi-square test for one variance",
        "slide_refs": [451],
        "chapter": "19",
        "setup": (
            "Random sample from a **normal** population (course note: "
            "normality is essential for the chi-square test on the "
            "variance — there is no CLT-style relaxation, slide 444). "
            "[slide 451]"
        ),
        "hypotheses_fmt": (
            "H_0: sigma^2 = {sigma_0_squared_disp}  vs.  H_1: "
            "sigma^2 {alt_op} {sigma_0_squared_disp}    ({tail})."
        ),
        "statistic": (
            "Under H_0,   chi^2 = (n - 1) S^2 / sigma_0^2  ~  chi^2_{n-1}."
        ),
        "computation_fmt": (
            "chi^2 = ({n} - 1) * {s_squared_disp} / {sigma_0_squared_disp} "
            "= {chi2_val}"
        ),
        "decision_fmt": (
            "Reject H_0 if {reject_rule}. (VE401 convention is the "
            "two-tail rejection region, slide 443; for a one-sided H_1 "
            "use the appropriate single tail.)"
        ),
        "compute": _chi2_variance,
        "stat_symbol": "chi^2",
        "stat_kind": "chi2",
    },
    # --- card04: Sign test ------------------------------------------------ #
    "card04": {
        "name": "Sign test for the median",
        "slide_refs": [468],
        "chapter": "20",
        "setup": (
            "Non-parametric one-sample test on the median; only the **signs** "
            "of (X_i - m_0) are used. Appropriate when normality is in "
            "doubt [slide 468]."
        ),
        "hypotheses_fmt": (
            "H_0: median = {mu_0}  vs.  H_1: median {alt_op} {mu_0}."
        ),
        "statistic": (
            "Let S^+ = number of observations with X_i > m_0. Under H_0, "
            "S^+ ~ Binomial(n, 0.5)."
        ),
        "computation_fmt": (
            "n = {n}, S^+ = (count from data — fill in once observations "
            "are listed). Drop ties with m_0 from n."
        ),
        "decision_fmt": (
            "Reject H_0 when S^+ falls in the appropriate Binomial(n, 0.5) "
            "tail at level {alpha}; for n large use the normal approximation "
            "Z = (S^+ - n/2) / sqrt(n/4)."
        ),
        "compute": None,
        "stat_symbol": "S+",
        "stat_kind": "binomial",
    },
    # --- card05: Wilcoxon signed-rank ------------------------------------- #
    "card05": {
        "name": "Wilcoxon signed-rank test",
        "slide_refs": [476],
        "chapter": "20",
        "setup": (
            "Non-parametric one-sample test on the location parameter, "
            "assuming a continuous symmetric distribution [slide 476]."
        ),
        "hypotheses_fmt": (
            "H_0: median = {mu_0}  vs.  H_1: median {alt_op} {mu_0}."
        ),
        "statistic": (
            "Form W^+ = sum of ranks of |X_i - m_0| over positive "
            "(X_i - m_0). Under H_0, E[W^+] = n(n+1)/4 and Var[W^+] = "
            "n(n+1)(2n+1)/24."
        ),
        "computation_fmt": (
            "Compute W^+ from the ranked absolute deviations. n = {n}."
        ),
        "decision_fmt": (
            "Use the Wilcoxon signed-rank table for small n; for n ≥ 20 use "
            "Z = (W^+ - n(n+1)/4) / sqrt(n(n+1)(2n+1)/24)."
        ),
        "compute": None,
        "stat_symbol": "W+",
        "stat_kind": "wilcoxon",
    },
    # --- card06: One-sample proportion Z-test ----------------------------- #
    "card06": {
        "name": "One-sample proportion Z-test",
        "slide_refs": [490],
        "chapter": "21",
        "setup": (
            "Large-sample test on a binomial proportion. Course convention: "
            "the **denominator uses p_0**, not p_hat (slide 490)."
        ),
        "hypotheses_fmt": (
            "H_0: p = {p_0}  vs.  H_1: p {alt_op} {p_0}."
        ),
        "statistic": (
            "Under H_0,  Z = (p_hat - p_0) / sqrt(p_0 (1 - p_0) / n)  ~  N(0, 1)."
        ),
        "computation_fmt": (
            "p_hat = {p_hat}, p_0 = {p_0}, n = {n};  z = (p_hat - p_0) / "
            "sqrt(p_0 (1 - p_0) / n)."
        ),
        "decision_fmt": (
            "Reject H_0 if {reject_rule} at level {alpha}."
        ),
        "compute": None,  # p_hat sometimes given, sometimes implicit; leave symbolic
        "stat_symbol": "z",
        "stat_kind": "z",
    },
    # --- card07: Two-sample proportion Z-test ----------------------------- #
    "card07": {
        "name": "Two-sample proportion Z-test",
        "slide_refs": [498],
        "chapter": "21",
        "setup": (
            "Two independent binomial samples; pool under H_0 to estimate "
            "the common proportion (slide 498)."
        ),
        "hypotheses_fmt": (
            "H_0: p_1 = p_2  vs.  H_1: p_1 {alt_op} p_2."
        ),
        "statistic": (
            "Under H_0,  Z = (p_hat_1 - p_hat_2) / sqrt(p_hat (1 - p_hat) "
            "(1/n_1 + 1/n_2))  ~  N(0, 1),  where p_hat = (X_1 + X_2)/(n_1 + n_2)."
        ),
        "computation_fmt": "Plug n_1 = {n1}, n_2 = {n2} and the observed counts.",
        "decision_fmt": "Reject H_0 if {reject_rule} at level {alpha}.",
        "compute": None,
        "stat_symbol": "z",
        "stat_kind": "z",
    },
    # --- card08: F-test for two variances --------------------------------- #
    "card08": {
        "name": "F-test for two variances",
        "slide_refs": [521],
        "chapter": "22",
        "setup": (
            "Two independent samples from normal populations; H_0 says "
            "the variances are equal (slide 521)."
        ),
        "hypotheses_fmt": (
            "H_0: sigma_1^2 = sigma_2^2  vs.  H_1: sigma_1^2 {alt_op} sigma_2^2."
        ),
        "statistic": (
            "Under H_0,  F = S_1^2 / S_2^2  ~  F_{n_1 - 1, n_2 - 1}. "
            "VE401 convention: put the larger sample variance on top."
        ),
        "computation_fmt": "F = (s_1^2)/(s_2^2) = ({s1})^2 / ({s2})^2.",
        "decision_fmt": (
            "Two-sided: reject H_0 if F > F_{alpha/2, n1-1, n2-1} or F < "
            "1/F_{alpha/2, n2-1, n1-1}. One-sided: reject if F > "
            "F_{alpha, n1-1, n2-1}."
        ),
        "compute": None,
        "stat_symbol": "F",
        "stat_kind": "F",
    },
    # --- card09: Two-sample Z-test (sigma1, sigma2 known) ----------------- #
    "card09": {
        "name": "Two-sample Z-test (sigma1, sigma2 known)",
        "slide_refs": [532],
        "chapter": "23",
        "setup": (
            "Two independent samples; both sigmas are known (long "
            "experience / process records cited). Z-test [slide 532]."
        ),
        "hypotheses_fmt": (
            "H_0: mu_1 - mu_2 = 0  vs.  H_1: mu_1 - mu_2 {alt_op} 0."
        ),
        "statistic": (
            "Under H_0,  Z = (X_bar_1 - X_bar_2) / sqrt(sigma_1^2/n_1 + "
            "sigma_2^2/n_2)  ~  N(0, 1)."
        ),
        "computation_fmt": (
            "z = ({x_bar1} - {x_bar2}) / sqrt(({sigma1})^2/{n1} + "
            "({sigma2})^2/{n2})."
        ),
        "decision_fmt": "Reject H_0 if {reject_rule} at level {alpha}.",
        "compute": None,
        "stat_symbol": "z",
        "stat_kind": "z",
    },
    # --- card10: Pooled (Student) T-test ---------------------------------- #
    "card10": {
        "name": "Pooled (Student) T-test",
        "slide_refs": [540],
        "chapter": "23",
        "setup": (
            "Two independent samples from normal populations with **common** "
            "(but unknown) variance (slide 540)."
        ),
        "hypotheses_fmt": (
            "H_0: mu_1 = mu_2  vs.  H_1: mu_1 {alt_op} mu_2."
        ),
        "statistic": (
            "S_p^2 = ((n_1 - 1) S_1^2 + (n_2 - 1) S_2^2) / (n_1 + n_2 - 2). "
            "Under H_0,  T = (X_bar_1 - X_bar_2) / (S_p sqrt(1/n_1 + 1/n_2)) "
            " ~  T_{n_1 + n_2 - 2}."
        ),
        "computation_fmt": "Plug s_1, s_2, n_1, n_2 into S_p, then compute t.",
        "decision_fmt": (
            "Reject H_0 if {reject_rule} with df = n_1 + n_2 - 2 at level {alpha}."
        ),
        "compute": None,
        "stat_symbol": "t",
        "stat_kind": "t",
    },
    # --- card11: Welch / Satterthwaite T-test ----------------------------- #
    "card11": {
        "name": "Welch / Satterthwaite T-test",
        "slide_refs": [546],
        "chapter": "23",
        "setup": (
            "Two independent samples; **variances NOT assumed equal**. Use "
            "Welch's T with Satterthwaite df (rounded **down** per VE401 "
            "convention, slide 546)."
        ),
        "hypotheses_fmt": (
            "H_0: mu_1 = mu_2  vs.  H_1: mu_1 {alt_op} mu_2."
        ),
        "statistic": (
            "T' = (X_bar_1 - X_bar_2) / sqrt(S_1^2/n_1 + S_2^2/n_2). "
            "df = floor((S_1^2/n_1 + S_2^2/n_2)^2 / "
            "((S_1^2/n_1)^2/(n_1 - 1) + (S_2^2/n_2)^2/(n_2 - 1)))."
        ),
        "computation_fmt": "Compute T' and Satterthwaite df.",
        "decision_fmt": "Reject H_0 if {reject_rule} at level {alpha}.",
        "compute": None,
        "stat_symbol": "t",
        "stat_kind": "t",
    },
    # --- card12: Paired T-test ------------------------------------------- #
    "card12": {
        "name": "Paired T-test",
        "slide_refs": [554],
        "chapter": "24",
        "setup": (
            "Each subject (or matched pair) provides one **difference** D_i "
            "= X_i - Y_i. Reduce to a one-sample T-test on the differences "
            "[slide 554]."
        ),
        "hypotheses_fmt": (
            "H_0: mu_D = 0  vs.  H_1: mu_D {alt_op} 0."
        ),
        "statistic": (
            "Under H_0,  T = D_bar / (S_D / sqrt(n))  ~  T_{n - 1}."
        ),
        "computation_fmt": (
            "t = {d_bar} / ({s} / sqrt({n})) = {t_val}"
        ),
        "decision_fmt": (
            "Reject H_0 if {reject_rule} with df = n - 1 = {df} at level {alpha}."
        ),
        "compute": _paired_t,
        "stat_symbol": "t",
        "stat_kind": "t",
    },
    # --- card13: Wilcoxon rank-sum / Mann-Whitney U ----------------------- #
    "card13": {
        "name": "Wilcoxon rank-sum / Mann-Whitney U",
        "slide_refs": [562],
        "chapter": "24",
        "setup": (
            "Two independent samples; non-parametric test on equal "
            "distributions / location shift (slide 562)."
        ),
        "hypotheses_fmt": (
            "H_0: distributions are equal  vs.  H_1: location shift "
            "({alt_op})."
        ),
        "statistic": (
            "Pool the n_1 + n_2 observations, rank them, let W_1 = sum of "
            "ranks for sample 1. U = W_1 - n_1 (n_1 + 1)/2."
        ),
        "computation_fmt": "Compute W_1 from the pooled ranks; n_1 = {n1}, n_2 = {n2}.",
        "decision_fmt": (
            "Use the rank-sum table for small samples; for n_1, n_2 ≥ 8 use "
            "Z = (W_1 - mu_W)/sigma_W with the standard mean and variance."
        ),
        "compute": None,
        "stat_symbol": "W",
        "stat_kind": "wilcoxon",
    },
    # --- card14: Inferences on correlation rho --------------------------- #
    "card14": {
        "name": "Inferences on correlation rho",
        "slide_refs": [578],
        "chapter": "24",
        "setup": (
            "Sample correlation r from a bivariate normal sample. For "
            "H_0: rho = 0 use the T-form; for general rho_0 use Fisher's "
            "z-transformation (slide 578)."
        ),
        "hypotheses_fmt": (
            "H_0: rho = {rho_0_disp}  vs.  H_1: rho {alt_op} {rho_0_disp}."
        ),
        "statistic": (
            "If rho_0 = 0:  T = r sqrt(n - 2) / sqrt(1 - r^2)  ~  T_{n - 2}. "
            "Otherwise use Z = (atanh(r) - atanh(rho_0)) sqrt(n - 3)  ~  N(0,1)."
        ),
        "computation_fmt": "Compute T (or Fisher z) using r and n = {n}.",
        "decision_fmt": "Reject H_0 if {reject_rule} at level {alpha}.",
        "compute": None,
        "stat_symbol": "t",
        "stat_kind": "t",
    },
    # --- card15: Pearson chi-square goodness-of-fit ---------------------- #
    "card15": {
        "name": "Pearson chi-square goodness-of-fit",
        "slide_refs": [598],
        "chapter": "25",
        "setup": (
            "Single categorical sample of n observations across k cells. "
            "Test whether the observed cell counts O_i are consistent "
            "with the model probabilities p_i^(0) (slide 598). VE401 "
            "convention: **df = k - 1 - m**, where m is the number of "
            "parameters estimated from the data."
        ),
        "hypotheses_fmt": (
            "H_0: cell probabilities equal the model values "
            "(p_1, ..., p_k)  vs.  H_1: at least one differs."
        ),
        "statistic": (
            "Under H_0,  chi^2 = sum_{i=1..k} (O_i - E_i)^2 / E_i  ~  "
            "chi^2_{k - 1 - m},  with E_i = n p_i^(0)."
        ),
        "computation_fmt": (
            "Observed counts: {observed_disp};  total n = {n_obs};  "
            "compute E_i = n p_i^(0) for each cell, then chi^2 = "
            "Σ (O_i - E_i)^2 / E_i."
        ),
        "decision_fmt": (
            "Reject H_0 if chi^2 > chi^2_{alpha, k - 1 - m} at level "
            "{alpha}. Course rule: **always upper-tail** for GoF."
        ),
        "compute": _chi2_gof,
        "stat_symbol": "chi^2",
        "stat_kind": "chi2-gof",
    },
    # --- card16: Chi-square test of independence ------------------------- #
    "card16": {
        "name": "Chi-square test of independence (rxc)",
        "slide_refs": [610],
        "chapter": "25",
        "setup": (
            "One sample of n observations cross-classified by two "
            "categorical variables (slide 610). df = (r - 1)(c - 1)."
        ),
        "hypotheses_fmt": (
            "H_0: row and column variables are independent  vs.  H_1: "
            "they are associated."
        ),
        "statistic": (
            "chi^2 = sum_{i,j} (O_{ij} - E_{ij})^2 / E_{ij}  ~  "
            "chi^2_{(r-1)(c-1)},  E_{ij} = (row_i_total * col_j_total) / n."
        ),
        "computation_fmt": "Build the expected-count table from row and column totals.",
        "decision_fmt": (
            "Reject H_0 if chi^2 > chi^2_{alpha,(r-1)(c-1)} at level {alpha}."
        ),
        "compute": None,
        "stat_symbol": "chi^2",
        "stat_kind": "chi2-table",
    },
    # --- card17: Chi-square test of homogeneity -------------------------- #
    "card17": {
        "name": "Chi-square test of homogeneity",
        "slide_refs": [620],
        "chapter": "25",
        "setup": (
            "**Several independent samples**, one per row, classified into "
            "the same c categories. The data table looks like an rxc table "
            "but the sampling design is different from independence "
            "(slide 620)."
        ),
        "hypotheses_fmt": (
            "H_0: the c-category distribution is the same in every row  "
            "vs.  H_1: at least one row differs."
        ),
        "statistic": (
            "chi^2 = sum_{i,j} (O_{ij} - E_{ij})^2 / E_{ij}  ~  "
            "chi^2_{(r-1)(c-1)},  E_{ij} = (row_i_total * col_j_total) / n."
        ),
        "computation_fmt": "Same arithmetic as the independence test.",
        "decision_fmt": (
            "Reject H_0 if chi^2 > chi^2_{alpha,(r-1)(c-1)} at level {alpha}."
        ),
        "compute": None,
        "stat_symbol": "chi^2",
        "stat_kind": "chi2-table",
    },
    # --- card18: SLR fit + inference ------------------------------------- #
    "card18": {
        "name": "Simple linear regression: fitting and inference",
        "slide_refs": [619],
        "chapter": "26",
        "setup": (
            "mu_{Y|x} = beta_0 + beta_1 x;  errors normal with mean 0 and "
            "variance sigma^2. Least-squares estimates "
            "b_1 = S_xy / S_xx,  b_0 = y_bar - b_1 x_bar [slide 619]."
        ),
        "hypotheses_fmt": (
            "H_0: beta_1 = 0  vs.  H_1: beta_1 {alt_op} 0  (slope test)."
        ),
        "statistic": (
            "T = b_1 / sqrt(s^2 / S_xx)  ~  T_{n - 2}  under H_0, with "
            "s^2 = SSE / (n - 2)."
        ),
        "computation_fmt": (
            "Compute b_1, b_0, SSE, then t = b_1 / sqrt(s^2 / S_xx). "
            "n = {n}."
        ),
        "decision_fmt": (
            "Reject H_0 if {reject_rule} with df = n - 2 at level {alpha}. "
            "A 100(1 - alpha)% CI for beta_1 is b_1 +/- t_{alpha/2, n-2} "
            "sqrt(s^2 / S_xx)."
        ),
        "compute": None,
        "stat_symbol": "t",
        "stat_kind": "t",
    },
    # --- card19: SLR prediction & diagnosis ------------------------------ #
    "card19": {
        "name": "SLR prediction & diagnosis",
        "slide_refs": [630],
        "chapter": "27",
        "setup": (
            "Two distinct intervals at x = x_0:  CI for the **mean** "
            "response,  PI for a **single new** observation. PI is wider "
            "by an extra `+1` inside the square root [slide 630]."
        ),
        "hypotheses_fmt": (
            "(Estimation, not a test.) Quantity of interest: mu_{Y|x_0}  "
            "or  Y_new at x_0."
        ),
        "statistic": (
            "y_hat = b_0 + b_1 x_0. SE for the mean: sqrt(s^2 (1/n + "
            "(x_0 - x_bar)^2 / S_xx)). SE for prediction: sqrt(s^2 (1 + "
            "1/n + (x_0 - x_bar)^2 / S_xx))."
        ),
        "computation_fmt": "Plug x_0 = ?, n = {n}, b_0, b_1, s^2, S_xx, x_bar.",
        "decision_fmt": (
            "Report (1 - alpha)% interval as y_hat +/- t_{alpha/2, n-2} * SE "
            "with the appropriate SE form."
        ),
        "compute": None,
        "stat_symbol": "t",
        "stat_kind": "t",
    },
    # --- card20: MLR estimation ------------------------------------------ #
    "card20": {
        "name": "Multiple linear regression: estimation",
        "slide_refs": [659],
        "chapter": "28",
        "setup": (
            "mu_{Y|x} = beta_0 + beta_1 x_1 + ... + beta_k x_k. b = "
            "(X^T X)^{-1} X^T y;  SSE = (y - X b)^T (y - X b);  s^2 = "
            "SSE / (n - k - 1) [slide 659]."
        ),
        "hypotheses_fmt": (
            "(Estimation step — no test yet. Use card21 for inference.)"
        ),
        "statistic": (
            "Var(b) = sigma^2 (X^T X)^{-1}; estimate by s^2 (X^T X)^{-1}."
        ),
        "computation_fmt": "Form (X^T X)^{-1}; n = {n}.",
        "decision_fmt": "Estimate phase only — see card21 for the F / T tests.",
        "compute": None,
        "stat_symbol": "b",
        "stat_kind": "mlr-fit",
    },
    # --- card21: MLR inference (3 F's and a T) --------------------------- #
    "card21": {
        "name": "MLR inference: three F's and a T",
        "slide_refs": [676],
        "chapter": "29",
        "setup": (
            "Three F-tests (regression-significance, partial / nested, "
            "lack-of-fit) and a T-test for an individual coefficient "
            "[slide 676]."
        ),
        "hypotheses_fmt": (
            "Regression significance:  H_0: beta_1 = ... = beta_k = 0  "
            "vs.  H_1: at least one nonzero. Partial F:  H_0: a specified "
            "subset of coefficients is zero."
        ),
        "statistic": (
            "F = (SSR / k) / (SSE / (n - k - 1))  ~  F_{k, n - k - 1}. "
            "Partial F = ((SSE_R - SSE_F) / q) / (SSE_F / (n - k - 1))."
        ),
        "computation_fmt": "Plug SSR, SSE, n = {n}, k, q.",
        "decision_fmt": (
            "Reject H_0 if F > F_{alpha, df1, df2} at level {alpha}."
        ),
        "compute": None,
        "stat_symbol": "F",
        "stat_kind": "F",
    },
    # --- card22: Model selection ----------------------------------------- #
    "card22": {
        "name": "Model selection (PRESS, adj-R^2, AIC)",
        "slide_refs": [702],
        "chapter": "30",
        "setup": (
            "Compare candidate MLR models by an information criterion "
            "(AIC, BIC), Mallows Cp, adjusted R^2, or PRESS [slide 702]."
        ),
        "hypotheses_fmt": "(Selection, not a hypothesis test.)",
        "statistic": (
            "PRESS = sum_i (y_i - y_hat_{(-i)})^2;  Cp = SSE_p / s^2_full "
            "- (n - 2 p);  adj R^2 = 1 - (1 - R^2)(n - 1)/(n - p - 1)."
        ),
        "computation_fmt": "Compute the criterion for each candidate model.",
        "decision_fmt": (
            "Choose the model with the smallest PRESS / Cp / AIC / BIC, "
            "or the largest adj R^2. Course preference: PRESS for prediction, "
            "adj R^2 for explanation."
        ),
        "compute": None,
        "stat_symbol": "PRESS",
        "stat_kind": "selection",
    },
    # --- card23: One-way ANOVA F-test ------------------------------------ #
    "card23": {
        "name": "One-way ANOVA F-test",
        "slide_refs": [724],
        "chapter": "31",
        "setup": (
            "k independent samples from normal populations with common "
            "variance. Decompose SST = SSTr + SSE (slide 724)."
        ),
        "hypotheses_fmt": (
            "H_0: mu_1 = mu_2 = ... = mu_k  vs.  H_1: at least one differs."
        ),
        "statistic": (
            "F = MSTr / MSE = (SSTr / (k - 1)) / (SSE / (N - k))  ~  "
            "F_{k - 1, N - k}."
        ),
        "computation_fmt": "Compute SSTr, SSE from the group totals.",
        "decision_fmt": "Reject H_0 if F > F_{alpha, k-1, N-k} at level {alpha}.",
        "compute": None,
        "stat_symbol": "F",
        "stat_kind": "F",
    },
    # --- card24: Bartlett's test ----------------------------------------- #
    "card24": {
        "name": "Bartlett's test for equal variances",
        "slide_refs": [758],
        "chapter": "32",
        "setup": (
            "Companion to ANOVA: tests the homogeneity-of-variance "
            "assumption [slide 758]. Sensitive to non-normality."
        ),
        "hypotheses_fmt": (
            "H_0: sigma_1^2 = ... = sigma_k^2  vs.  H_1: at least one differs."
        ),
        "statistic": (
            "B = (1/c) ((N - k) ln(s_p^2) - sum_i (n_i - 1) ln(s_i^2))  ~  "
            "chi^2_{k - 1}."
        ),
        "computation_fmt": "Compute s_p^2, c-correction, then B.",
        "decision_fmt": "Reject H_0 if B > chi^2_{alpha, k - 1} at level {alpha}.",
        "compute": None,
        "stat_symbol": "B",
        "stat_kind": "chi2",
    },
    # --- card25: Post-hoc multiple comparisons --------------------------- #
    "card25": {
        "name": "Post-hoc multiple comparisons",
        "slide_refs": [762],
        "chapter": "32",
        "setup": (
            "Run only after a significant ANOVA. Tukey's HSD or Bonferroni "
            "controls the family-wise error rate (slide 762)."
        ),
        "hypotheses_fmt": (
            "For each pair (i, j):  H_0: mu_i = mu_j  vs.  H_1: mu_i != mu_j."
        ),
        "statistic": (
            "Tukey HSD: |X_bar_i - X_bar_j| / sqrt(MSE/n) compared to the "
            "studentized-range q_{alpha, k, N-k}. Bonferroni: standard t "
            "with alpha replaced by alpha / m, m = k(k-1)/2."
        ),
        "computation_fmt": "Compute every pairwise difference; flag those exceeding the threshold.",
        "decision_fmt": (
            "Conclude pair (i, j) significant at family-wise level {alpha} "
            "if its statistic exceeds the chosen critical value."
        ),
        "compute": None,
        "stat_symbol": "q",
        "stat_kind": "tukey",
    },
}


def get_template(card_id: str) -> Optional[dict]:
    return TEMPLATES.get(card_id)


__all__ = ["TEMPLATES", "get_template"]
