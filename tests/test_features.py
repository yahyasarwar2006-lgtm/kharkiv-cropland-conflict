import numpy as np
import pandas as pd
import pytest

from agridisrupt.features import season_peaks, season_shape


def test_season_peaks_ignores_empty_periods():
    panel = pd.DataFrame({
        "cell_id": ["c1"] * 4 + ["c2"] * 4,
        "year": 2021,
        "period": [0, 1, 2, 3] * 2,
        "ndvi": [0.2, 0.7, np.nan, 0.3,
                 0.1, np.nan, 0.5, 0.6],
    })
    peaks = season_peaks(panel).set_index("cell_id")
    assert peaks.loc["c1", "peak_ndvi"] == 0.7 and peaks.loc["c1", "peak_period"] == 1
    assert peaks.loc["c2", "peak_ndvi"] == 0.6 and peaks.loc["c2", "peak_period"] == 3
    assert peaks.loc["c1", "n_valid"] == 3


def test_season_shape_late_greenness_needs_enough_periods():
    panel = pd.DataFrame({
        "cell_id": ["c1"] * 4 + ["c2"] * 4,
        "year": 2022,
        "period": [0, 1, 2, 3] * 2,
        "ndvi": [0.2, 0.7, 0.4, 0.2,
                 0.2, 0.7, 0.5, np.nan],
    })
    shape = season_shape(panel, late_periods=[2, 3], late_min_periods=2).set_index("cell_id")
    assert shape.loc["c1", "late_ndvi"] == pytest.approx(0.3)   # mean of periods 2 and 3
    assert np.isnan(shape.loc["c2", "late_ndvi"])          # only 1 of 2 late periods usable
    assert shape.loc["c2", "peak_ndvi"] == 0.7
