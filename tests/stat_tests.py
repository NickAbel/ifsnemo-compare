"""Statistical tests applied to pairs of norm arrays.

All arithmetic lives here.  Callers (compare_norms, future check_gribs, …)
are responsible only for extracting raw {varname: [float, …]} dicts and
passing them in — no manipulation on their side.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

try:
    from scipy import stats as _scipy_stats
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False


# ---------------------------------------------------------------------------
# Tuneable thresholds
# ---------------------------------------------------------------------------
KS_PVAL_THRESHOLD     = 0.05   # p-value below which the KS test raises a warning
EFFECT_SIZE_THRESHOLD = 1.0    # |effect size| above which the effect-size test warns


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------
@dataclass
class StatResult:
    varname:         str
    n_ref:           int
    n_test:          int
    # effect-size test
    mean_ref:        float
    mean_test:       float
    sigma_pooled:    float    # pooled std of both groups
    effect_size:     float    # (mean_ref - mean_test) / sigma_pooled  [dimensionless]
    effect_passed:   bool     # |effect_size| <= EFFECT_SIZE_THRESHOLD
    # KS test (None when scipy is unavailable)
    ks_stat:         float | None = None
    ks_pval:         float | None = None
    ks_passed:       bool  | None = None
    # bookkeeping
    skipped:         bool  = False
    skip_reason:     str   = ""


# ---------------------------------------------------------------------------
# Core statistics
# ---------------------------------------------------------------------------
def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _sample_var(xs: list[float], mean: float) -> float:
    """Unbiased sample variance  s^2 = 1/(n-1) * sum((x_i - mean)^2)."""
    n = len(xs)
    if n < 2:
        return 0.0
    return sum((x - mean) ** 2 for x in xs) / (n - 1)


def pooled_std(x: list[float], y: list[float]) -> float:
    """
    Pooled standard deviation of two independent groups:

        s = sqrt( ((n1-1)*s1^2 + (n2-1)*s2^2) / (n1 + n2 - 2) )

    where s1^2 = 1/(n1-1) * sum((x_i - x_bar)^2)  and s2^2 similarly.
    """
    n1, n2 = len(x), len(y)
    if n1 + n2 - 2 <= 0:
        return 0.0
    s1_sq = _sample_var(x, _mean(x))
    s2_sq = _sample_var(y, _mean(y))
    return math.sqrt(((n1 - 1) * s1_sq + (n2 - 1) * s2_sq) / (n1 + n2 - 2))


# ---------------------------------------------------------------------------
# Per-variable tests
# ---------------------------------------------------------------------------
def _effect_size_test(
    ref: list[float], test: list[float]
) -> tuple[float, float, float, float, bool]:
    """
    Effect-size test.
    Returns (mean_ref, mean_test, sigma_pooled, effect_size, passed).

    Effect size = (mean_ref - mean_test) / sigma_pooled — the difference in
    means expressed in units of the pooled standard deviation.
    Warns when |effect_size| > EFFECT_SIZE_THRESHOLD.
    """
    mean_ref  = _mean(ref)
    mean_test = _mean(test)
    sp        = pooled_std(ref, test)
    effect    = (mean_ref - mean_test) / sp if sp != 0.0 else float("nan")
    passed    = abs(effect) <= EFFECT_SIZE_THRESHOLD if sp != 0.0 else (mean_ref == mean_test)
    return mean_ref, mean_test, sp, effect, passed


def _ks_test(
    ref: list[float], test: list[float]
) -> tuple[float | None, float | None, bool | None]:
    """
    Two-sample Kolmogorov-Smirnov test via scipy.stats.ks_2samp.
    Returns (statistic, p-value, passed).  All None when scipy is absent.
    """
    if not _SCIPY_AVAILABLE:
        return None, None, None
    stat, pval = _scipy_stats.ks_2samp(ref, test)
    return stat, pval, pval >= KS_PVAL_THRESHOLD


def _test_var(varname: str, ref: list[float], test: list[float]) -> StatResult:
    mean_ref, mean_test, sp, effect, effect_passed = _effect_size_test(ref, test)
    ks_stat, ks_pval, ks_passed                    = _ks_test(ref, test)
    return StatResult(
        varname       = varname,
        n_ref         = len(ref),
        n_test        = len(test),
        mean_ref      = mean_ref,
        mean_test     = mean_test,
        sigma_pooled  = sp,
        effect_size   = effect,
        effect_passed = effect_passed,
        ks_stat       = ks_stat,
        ks_pval       = ks_pval,
        ks_passed     = ks_passed,
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------
def run(
    ref:  dict[str, list[float]],
    test: dict[str, list[float]],
) -> dict[str, StatResult]:
    """
    Run all statistical tests on every variable common to ref and test.

    Parameters
    ----------
    ref, test : {varname: [float, …]}
        Raw arrays extracted by the calling test module.

    Returns
    -------
    {varname: StatResult}
    """
    results: dict[str, StatResult] = {}

    only_ref  = sorted(set(ref)  - set(test))
    only_test = sorted(set(test) - set(ref))
    common    = sorted(set(ref)  & set(test))

    _nan = float("nan")

    for varname in only_ref:
        results[varname] = StatResult(
            varname=varname, n_ref=len(ref[varname]), n_test=0,
            mean_ref=_mean(ref[varname]), mean_test=_nan,
            sigma_pooled=_nan, effect_size=_nan, effect_passed=False,
            skipped=True, skip_reason="variable absent in test",
        )

    for varname in only_test:
        results[varname] = StatResult(
            varname=varname, n_ref=0, n_test=len(test[varname]),
            mean_ref=_nan, mean_test=_mean(test[varname]),
            sigma_pooled=_nan, effect_size=_nan, effect_passed=False,
            skipped=True, skip_reason="variable absent in ref",
        )

    for varname in common:
        ref_arr  = ref[varname]
        test_arr = test[varname]

        if len(ref_arr) != len(test_arr):
            results[varname] = StatResult(
                varname=varname, n_ref=len(ref_arr), n_test=len(test_arr),
                mean_ref=_mean(ref_arr), mean_test=_mean(test_arr),
                sigma_pooled=_nan, effect_size=_nan, effect_passed=False,
                skipped=True,
                skip_reason=f"array length mismatch ({len(ref_arr)} vs {len(test_arr)})",
            )
            continue

        results[varname] = _test_var(varname, ref_arr, test_arr)

    return results


def report(results: dict[str, StatResult]) -> None:
    """Print a human-readable summary of stat-test results to stdout."""
    for varname, r in sorted(results.items()):
        print(f"  {varname}:")
        if r.skipped:
            print(f"    [SKIP] {r.skip_reason}")
            continue

        effect_label = "pass" if r.effect_passed else "WARN"
        print(
            f"    effect-size: d={r.effect_size:.4e}"
            f"  sigma_pooled={r.sigma_pooled:.4e}"
            f"  [{effect_label}]"
        )

        if r.ks_stat is not None:
            ks_label = "pass" if r.ks_passed else "WARN"
            print(
                f"    KS:          stat={r.ks_stat:.4e}"
                f"  p={r.ks_pval:.4e}"
                f"  [{ks_label}]"
            )
        else:
            print("    KS:          [SKIP] scipy unavailable")
