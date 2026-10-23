import numpy as np
import pandas as pd
import pytest

from agridisrupt.analysis import bootstrap_diff, bootstrap_mean, morans_i, spatial_blocks, twfe


def test_spatial_blocks():
    b = spatial_blocks(pd.Series([1.0, 24.0, 26.0]), pd.Series([0.0, 0.0, 0.0]), 25)
    assert b[0] == b[1] != b[2]


def test_bootstrap_diff_recovers_group_difference():
    rng = np.random.default_rng(1)
    n = 400
    high = pd.Series(np.arange(n) % 2 == 0)
    values = pd.Series(np.where(high, 0.1, 0.0) + rng.normal(0, 0.01, n))
    blocks = pd.Series(np.arange(n) // 10)
    diff, lo, hi = bootstrap_diff(values, high, blocks, reps=200)
    assert diff == pytest.approx(0.1, abs=0.005) and lo < diff < hi


def test_twfe_recovers_beta_despite_unit_and_time_effects():
    rng = np.random.default_rng(2)
    units, times = np.repeat(np.arange(50), 6), np.tile(np.arange(6), 50)
    x = rng.uniform(0, 3, len(units))
    unit_eff, time_eff = rng.normal(0, 1, 50), rng.normal(0, 1, 6)
    y = unit_eff[units] + time_eff[times] + 0.5 * x + rng.normal(0, 0.05, len(units))
    res = twfe(pd.Series(y), pd.Series(x), pd.Series(units), pd.Series(times), pd.Series(units // 5))
    assert res["beta"] == pytest.approx(0.5, abs=0.02)
    assert res["ci_low"] < 0.5 < res["ci_high"]


def test_morans_i_detects_smooth_pattern_not_noise():
    xs, ys = np.meshgrid(np.arange(15), np.arange(15))
    x, y = xs.ravel().astype(float), ys.ravel().astype(float)
    smooth, _ = morans_i(x + y, x, y, max_dist=1.5, perms=49)
    noise, p = morans_i(np.random.default_rng(3).normal(size=x.size), x, y, max_dist=1.5, perms=49)
    assert smooth > 0.8 and abs(noise) < 0.15 and p > 0.05


def test_bootstrap_mean_interval_covers_mean():
    v = pd.Series(np.random.default_rng(4).normal(0.05, 0.02, 300))
    mean, lo, hi = bootstrap_mean(v, pd.Series(np.arange(300) // 10), reps=300)
    assert lo < mean < hi and mean == pytest.approx(0.05, abs=0.005)
