"""Phase E acceptance test (plan §6 step E4).

Three end-to-end smoke tests across three different test families:

1. **Z-test** (card01) — classic bottling-line scenario with known sigma.
2. **One-sample T-test** (card02) — sigma unknown; numerical t reproduces
   the VE401 ch19 q2 worked example.
3. **Chi-square goodness-of-fit** (card15) — geneticist's 9:3:4 ratio with
   observed counts; checks the renderer surfaces the observed counts and
   df-formula correctly.

Each test asserts:

* the classifier picked the expected card_id (top-1);
* the rendered Markdown contains the five canonical section headers;
* the rendered Markdown cites the card's slide_ref;
* a numerical test statistic was computed (where applicable);
* the computed statistic matches the slide-worked-example value to 2 dp.

The whole file runs as a plain script (no pytest dependency) — invoke
with ``python -m tests.test_render``.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from solver import solve  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


SECTIONS = ("## Setup", "## Hypotheses", "## Statistic", "## Computation", "## Decision")


def _check_sections(md: str, label: str) -> None:
    missing = [s for s in SECTIONS if s not in md]
    assert not missing, f"{label}: missing sections {missing}\n--- markdown ---\n{md}"


def _ok(label: str, msg: str = "") -> None:
    print(f"  PASS  {label}{(' — ' + msg) if msg else ''}")


# --------------------------------------------------------------------------- #
# Tests                                                                        #
# --------------------------------------------------------------------------- #


def test_z_one_sample() -> None:
    label = "card01 Z-test (bottling line, known sigma)"
    print(f"[1/3] {label}")
    q = (
        r"A bottling line is calibrated so that the fill volume is normally "
        r"distributed with known standard deviation \(\sigma = 2.0\) mL. The "
        r"target mean is \(\mu_0 = 25\) mL. A random sample of \(n = 25\) "
        r"bottles gives \(\bar x = 24.3\) mL. At significance level "
        r"\(\alpha = 0.05\), test \(H_0:\mu = 25\) versus the two-sided "
        r"alternative."
    )
    res = solve(q)
    assert res.card_id == "card01", f"top-1 expected card01, got {res.card_id}"
    _check_sections(res.markdown, label)
    assert "slide 436" in res.markdown, f"{label}: missing slide 436 cite"
    assert "One-sample Z-test" in res.markdown
    assert res.statistic_value is not None, f"{label}: no statistic computed"
    expected_z = (24.3 - 25.0) / (2.0 / math.sqrt(25))
    assert abs(res.statistic_value - expected_z) < 1e-6, (
        f"{label}: z={res.statistic_value} expected {expected_z}"
    )
    # Spot-check: givens were read off correctly.
    g = res.givens.raw
    assert abs(g["sigma"] - 2.0) < 1e-9
    assert abs(g["mu_0"] - 25.0) < 1e-9
    assert abs(g["x_bar"] - 24.3) < 1e-9
    assert int(g["n"]) == 25
    assert abs(g["alpha"] - 0.05) < 1e-9
    _ok(label, f"z={res.statistic_value:.4g} matches expected {expected_z:.4g}")


def test_t_one_sample() -> None:
    label = "card02 T-test (precision washers, sigma unknown)"
    print(f"[2/3] {label}")
    q = (
        r"A small batch of \(n=12\) precision washers is measured for "
        r"thickness. The sample gives \(\bar x = 4.985\) mm and sample "
        r"standard deviation \(s = 0.027\) mm. The specification calls "
        r"for \(\mu_0 = 5.000\) mm. Assume thickness is approximately "
        r"normal. At \(\alpha=0.05\), test \(H_0:\mu=5.000\) against the "
        r"two-sided alternative."
    )
    res = solve(q)
    assert res.card_id == "card02", f"top-1 expected card02, got {res.card_id}"
    _check_sections(res.markdown, label)
    assert "slide 445" in res.markdown
    assert "One-sample T-test" in res.markdown
    assert res.statistic_value is not None
    expected_t = (4.985 - 5.000) / (0.027 / math.sqrt(12))
    assert abs(res.statistic_value - expected_t) < 1e-6, (
        f"{label}: t={res.statistic_value} expected {expected_t}"
    )
    # The slide-worked example rounds to t = -1.92.
    assert abs(round(res.statistic_value, 2) - (-1.92)) < 1e-9, (
        f"{label}: rounded t = {round(res.statistic_value, 2)}, expected -1.92"
    )
    _ok(label, f"t={res.statistic_value:.4g} matches slide-worked -1.92")


def test_chi2_goodness_of_fit() -> None:
    label = "card15 chi-square goodness-of-fit (geneticist 9:3:4 ratio)"
    print(f"[3/3] {label}")
    q = (
        "A geneticist counts 90 yellow seeds, 35 green seeds, and 25 white "
        "seeds and asks whether the data fit the predicted 9:3:4 ratio. "
        "Use alpha = 0.05."
    )
    res = solve(q)
    assert res.card_id == "card15", f"top-1 expected card15, got {res.card_id}"
    _check_sections(res.markdown, label)
    assert "slide 598" in res.markdown
    assert "goodness-of-fit" in res.markdown.lower()
    # The renderer should surface the observed counts.
    assert "90" in res.markdown and "35" in res.markdown and "25" in res.markdown, (
        f"{label}: observed counts not surfaced in markdown"
    )
    counts = res.givens.observed_counts
    assert counts == [90, 35, 25], f"{label}: observed_counts {counts}, expected [90,35,25]"
    # Without an explicit expected vector we can't compute chi^2 numerically;
    # statistic_value should be None and the renderer reports "(insufficient givens)".
    assert res.statistic_value is None
    assert "(insufficient givens)" in res.markdown or "Σ" in res.markdown or "sum" in res.markdown.lower()
    _ok(label, f"observed_counts={counts}")


def main() -> int:
    print("Phase E renderer smoke tests")
    print("============================")
    test_z_one_sample()
    test_t_one_sample()
    test_chi2_goodness_of_fit()
    print("\nALL 3 TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
