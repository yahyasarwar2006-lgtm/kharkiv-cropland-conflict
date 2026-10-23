import numpy as np
import pandas as pd
import pytest

from agridisrupt.models.baseline import baseline_anomalies, seasonal_baseline


def _panel():
    # one cell, one period, NDVI per year; 2020 is cloudy (empty)
    return pd.DataFrame({
        "cell_id": "c1", "period": 0,
        "year": [2018, 2019, 2020, 2021, 2022],
        "ndvi": [0.6, 0.7, np.nan, 0.8, 0.5],
    })


def test_seasonal_baseline_mean_and_min_years():
    base = seasonal_baseline(_panel(), [2018, 2019, 2020, 2021], min_years=2)
    assert base.loc[0, "expected"] == pytest.approx(0.7) and base.loc[0, "n_years"] == 3
    assert np.isnan(seasonal_baseline(_panel(), [2018, 2020], min_years=2).loc[0, "expected"])


def test_baseline_anomalies_leave_one_year_out():
    out = baseline_anomalies(_panel(), [2018, 2019, 2020, 2021], min_years=2).set_index("year")
    assert out.loc[2022, "expected"] == pytest.approx(0.7)            # all baseline years
    assert out.loc[2022, "anomaly"] == pytest.approx(-0.2)
    assert out.loc[2018, "expected"] == pytest.approx(0.75)           # 2019 + 2021, not itself
    assert out.loc[2018, "n_years"] == 2
    assert np.isnan(out.loc[2020, "anomaly"])                          # no observation -> no anomaly


def test_baseline_anomalies_per_cell_for_shape_measures():
    shape = pd.DataFrame({"cell_id": "c1", "year": [2018, 2019, 2022], "late_ndvi": [0.2, 0.3, 0.5]})
    out = baseline_anomalies(shape, [2018, 2019], min_years=1, value="late_ndvi", by=("cell_id",))
    out = out.set_index("year")
    assert out.loc[2022, "anomaly"] == pytest.approx(0.25)
    assert out.loc[2018, "expected"] == pytest.approx(0.3)   # 2019 only
