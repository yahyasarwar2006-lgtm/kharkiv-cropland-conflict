import numpy as np
import pandas as pd
import pytest

from agridisrupt.models.ml import add_weather_features, fit_ridge, ridge_design, scores, split_frames


def _panel(years=(2018, 2019, 2020, 2021), cells=("c1", "c2"), periods=3, seed=0):
    rng = np.random.default_rng(seed)
    rows = [(c, y, p) for c in cells for y in years for p in range(periods)]
    df = pd.DataFrame(rows, columns=["cell_id", "year", "period"])
    df["precip_sum"] = rng.uniform(0, 50, len(df))
    df["t2m_mean"] = 10.0
    df["ndvi"] = 0.3 + 0.1 * df["period"] + 0.004 * df["precip_sum"]   # wetter -> greener
    return df


def test_add_weather_features_accumulates_within_each_season():
    df = add_weather_features(_panel(), gdd_base=5, period_days=14)
    one = df[(df.cell_id == "c1") & (df.year == 2018)]
    assert list(one["gdd_cum"]) == [70, 140, 210]                       # (10 - 5) * 14 per period
    assert one["rain_cum"].iloc[-1] == pytest.approx(one["precip_sum"].sum())


def test_split_frames_never_uses_the_test_year_for_its_baseline():
    df = _panel()
    df.loc[df.year == 2021, "ndvi"] += 1.0                               # test year very different
    train, test = split_frames(df, [2018, 2019, 2020], 2021, min_years=2)
    assert set(train.year) == {2018, 2019, 2020} and set(test.year) == {2021}
    assert test["expected"].max() < 1.0                                  # baseline from 2018-20 only
    assert (test["anomaly"] > 0.8).all()


def test_ridge_learns_rain_effect_and_beats_zero_anomaly():
    df = _panel(cells=[f"c{i}" for i in range(30)])
    train, test = split_frames(df, [2018, 2019, 2020], 2021, min_years=2)
    cols = ["period", "expected", "precip_sum"]
    model, alpha = fit_ridge(train, cols, n_periods=3, alphas=[0.01, 1, 100])
    pred = model.predict(ridge_design(test, cols, 3))
    assert scores(test["anomaly"], pred, test["ndvi"])["MAE"] < scores(test["anomaly"], 0 * pred, test["ndvi"])["MAE"] / 2


def test_predict_normal_removes_the_weather_effect():
    from agridisrupt.models.ml import predict_normal
    df = _panel(years=(2018, 2019, 2020, 2021, 2022), cells=[f"c{i}" for i in range(40)])
    out = predict_normal(df, [2018, 2019, 2020, 2021], 2022, ["period", "expected", "precip_sum"],
                         {"max_iter": 200, "learning_rate": 0.1, "min_samples_leaf": 5}, min_years=2)
    assert set(out.year) == {2022}
    # NDVI here depends only on season + rain, so after the weather adjustment little is left
    assert out["adjusted_anomaly"].abs().mean() < out["anomaly"].abs().mean() / 2
