import numpy as np
import pandas as pd

from agridisrupt.composites import cell_stats, median_composite, n_periods, period_dates, period_index
from agridisrupt.config import load_config

CONFIG = load_config("configs/kharkiv_v1.yaml")


def test_period_index_boundaries():
    dates = ["2021-03-31", "2021-04-01", "2021-04-14", "2021-04-15", "2021-10-28", "2021-10-31", "2021-11-01"]
    # Apr-Oct = 214 days -> 15 periods of 14 days; the 4 leftover days join period 14
    assert n_periods(2021, CONFIG) == 15
    assert list(period_index(dates, CONFIG)) == [-1, 0, 0, 1, 14, 14, -1]


def test_period_index_ignores_time_zone():
    assert period_index([pd.Timestamp("2022-04-14 23:30", tz="UTC")], CONFIG)[0] == 0


def test_period_dates():
    assert period_dates(2021, 0, CONFIG) == (pd.Timestamp("2021-04-01"), pd.Timestamp("2021-04-14"))
    assert period_dates(2021, 14, CONFIG) == (pd.Timestamp("2021-10-14"), pd.Timestamp("2021-10-31"))


def test_median_composite_ignores_clouds():
    stack = np.array([
        [[0.2, np.nan]],
        [[0.4, np.nan]],
        [[0.9, np.nan]],
    ])  # 3 dates, 1 x 2 pixels; second pixel was never clear
    comp = median_composite(stack)
    assert comp[0, 0] == 0.4
    assert np.isnan(comp[0, 1])


def test_cell_stats_uses_cropland_only():
    composite = np.array([[0.8, 0.8, np.nan, 0.1]])
    labels = np.array([[1, 1, 1, 2]])
    crop = np.array([[True, True, True, False]])  # pixel 4 is not cropland

    stats = cell_stats(composite, labels, crop, ["a", "b"]).set_index("cell_id")

    assert stats.loc["a", "crop_pixels"] == 3
    assert np.isclose(stats.loc["a", "valid_share"], 2 / 3)
    assert stats.loc["a", "ndvi_median"] == 0.8
    # cell b has no cropland pixels -> no value rather than a misleading 0
    assert stats.loc["b", "crop_pixels"] == 0
    assert np.isnan(stats.loc["b", "ndvi_median"])
