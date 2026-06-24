
from reliability.stats.bootstrap import bootstrap_ci, paired_delta_ci, wilson_ci
from reliability.stats.significance import mcnemar, wilcoxon_signed_rank


def test_bootstrap_ci_is_seeded_and_brackets_point():
    vals = [1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0]
    ci1 = bootstrap_ci(vals, seed=42)
    ci2 = bootstrap_ci(vals, seed=42)
    assert ci1.low == ci2.low and ci1.high == ci2.high  # reproducible
    assert ci1.low <= ci1.point <= ci1.high


def test_paired_delta_ci_detects_regression():
    base = [1.0] * 8 + [1.0, 1.0]
    cand = [0.2] * 8 + [1.0, 1.0]
    ci = paired_delta_ci(base, cand, seed=1)
    assert ci.high < 0  # entirely below zero -> regression
    assert ci.excludes_zero


def test_paired_delta_ci_no_change_straddles_zero():
    base = [1.0, 0.0, 1.0, 0.0, 1.0, 0.0]
    ci = paired_delta_ci(base, base, seed=1)
    assert ci.low == 0.0 and ci.high == 0.0


def test_wilson_ci_bounds():
    ci = wilson_ci(7, 10)
    assert 0.0 <= ci.low <= ci.point <= ci.high <= 1.0


def test_mcnemar_exact_pvalue():
    # 7 pass->fail, 0 fail->pass: exact two-sided p = 2 * 0.5^7
    base = [True] * 10
    cand = [False] * 7 + [True] * 3
    res = mcnemar(base, cand)
    assert res.detail["b_regressions"] == 7
    assert res.detail["c_fixes"] == 0
    assert abs(res.p_value - 2 * 0.5 ** 7) < 1e-9


def test_mcnemar_no_discordant_is_nonsignificant():
    res = mcnemar([True, False, True], [True, False, True])
    assert res.p_value == 1.0


def test_wilcoxon_directional():
    base = [1.0] * 9 + [1.0]
    cand = [0.3] * 9 + [1.0]
    res = wilcoxon_signed_rank(base, cand)
    assert res.p_value < 0.05
