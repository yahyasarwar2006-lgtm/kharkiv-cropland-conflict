"""Stage 5: weather-aware models of "normal" NDVI.

Target = NDVI anomaly vs the cell's own seasonal baseline from the TRAINING years (leave-one-year-out
inside the training years, so training targets look like test targets). A model predicts that anomaly
from season, place and weather; predicted NDVI = baseline + predicted anomaly. The seasonal baseline
itself is the case "predicted anomaly = 0", so all models are compared on equal terms.
No past NDVI is used as input: from 2022 on it would carry war effects into "normal".
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from agridisrupt.models.baseline import baseline_anomalies, seasonal_baseline

FEATURE_GROUPS = {
    "season + place": ["period", "x", "y", "cropland_fraction", "expected"],
    "rain": ["precip_sum", "precip_30d", "precip_60d", "rain_cum"],
    "temperature": ["t2m_mean", "t2m_anom", "gdd_cum"],
    "soil moisture": ["swvl1_mean"],
}
ALL_FEATURES = [c for cols in FEATURE_GROUPS.values() for c in cols]


def load_model_data(config: dict) -> pd.DataFrame:
    """Panel + static cell features (centroid x, y in km in EPSG:3035, cropland share) + weather features."""
    panel = pd.read_csv(Path(config["paths"]["data_processed"]) / "panel.csv")
    cells = gpd.read_file(Path(config["paths"]["data_interim"]) / "kharkiv_grid_5km_cropland.gpkg")
    centre = cells.geometry.centroid
    static = pd.DataFrame({"cell_id": cells["cell_id"], "x": centre.x / 1000, "y": centre.y / 1000,
                           "cropland_fraction": cells["cropland_fraction"]})
    df = panel.merge(static, on="cell_id", how="left")
    return add_weather_features(df, config["models"]["gdd_base_c"], config["time"]["composite_days"])


def add_weather_features(panel: pd.DataFrame, gdd_base: float, period_days: int) -> pd.DataFrame:
    """Season-to-date growing degree days (warmth above `gdd_base` °C) and rain, per cell and year."""
    df = panel.sort_values(["cell_id", "year", "period"]).copy()
    gdd = (df["t2m_mean"] - gdd_base).clip(lower=0) * period_days
    by = [df["cell_id"], df["year"]]
    df["gdd_cum"] = gdd.groupby(by).cumsum()
    df["rain_cum"] = df["precip_sum"].groupby(by).cumsum()
    return df


def split_frames(df: pd.DataFrame, train_years: list[int], test_year: int, min_years: int):
    """Training rows: anomaly vs the leave-one-year-out baseline inside the training years.
    Test rows: anomaly vs the baseline of all training years. Rows without an anomaly are dropped."""
    train_min = min(min_years, len(train_years) - 1)
    train = baseline_anomalies(df[df["year"].isin(train_years)], train_years, train_min)
    base = seasonal_baseline(df, train_years, min_years)
    test = df[df["year"] == test_year].merge(base, on=["cell_id", "period"], how="left")
    test["anomaly"] = test["ndvi"] - test["expected"]
    return train.dropna(subset=["anomaly"]), test.dropna(subset=["anomaly"])


def ridge_design(df: pd.DataFrame, cols: list[str], n_periods: int) -> pd.DataFrame:
    """Linear design: one-hot period, numeric columns, and each weather column x period
    (lets the effect of rain or heat differ through the season)."""
    onehot = pd.get_dummies(pd.Categorical(df["period"], categories=range(n_periods)), prefix="p", dtype=float)
    onehot.index = df.index
    numeric = [c for c in cols if c != "period"]
    weather = [c for c in numeric if c not in FEATURE_GROUPS["season + place"]]
    parts = [onehot, df[numeric]]
    for c in weather:
        parts.append(onehot.mul(df[c], axis=0).add_prefix(f"{c}_x_"))
    return pd.concat(parts, axis=1)


def fit_ridge(train: pd.DataFrame, cols: list[str], n_periods: int, alphas: list[float]):
    """Ridge on standardised features; alpha chosen by leave-one-training-year-out MAE."""
    X, y, years = ridge_design(train, cols, n_periods), train["anomaly"], train["year"]
    model = lambda a: make_pipeline(StandardScaler(), Ridge(alpha=a))

    def cv_mae(a):
        return np.mean([np.abs(model(a).fit(X[years != yr], y[years != yr]).predict(X[years == yr])
                               - y[years == yr]).mean() for yr in years.unique()])
    best = min(alphas, key=cv_mae)
    return model(best).fit(X, y), best


def fit_gbm(train: pd.DataFrame, cols: list[str], params: dict):
    """Gradient-boosted trees with fixed settings; no early stopping (it would use a random split)."""
    gbm = HistGradientBoostingRegressor(early_stopping=False, random_state=0, **params)
    return gbm.fit(train[cols], train["anomaly"])


def scores(anomaly: pd.Series, predicted_anomaly: np.ndarray, ndvi: pd.Series) -> dict:
    """Errors of predicted NDVI (= baseline + predicted anomaly). R² anomaly = share of the
    deviation from normal that the model explains (0 or below = no better than the baseline's 0)."""
    err = predicted_anomaly - anomaly
    return {
        "MAE": np.abs(err).mean(),
        "RMSE": np.sqrt((err ** 2).mean()),
        "bias": err.mean(),
        "R2 NDVI": 1 - (err ** 2).sum() / ((ndvi - ndvi.mean()) ** 2).sum(),
        "R2 anomaly": 1 - (err ** 2).sum() / ((anomaly - anomaly.mean()) ** 2).sum(),
        "n": len(err),
    }


def predict_normal(df: pd.DataFrame, train_years: list[int], test_year: int, cols: list[str],
                   gbm_params: dict, min_years: int) -> pd.DataFrame:
    """Train gradient boosting on `train_years` and predict normal NDVI for `test_year`.
    Returns the test rows with: expected (seasonal baseline), predicted (baseline + predicted anomaly),
    anomaly (observed - baseline) and adjusted_anomaly (observed - predicted = weather-adjusted)."""
    train, test = split_frames(df, train_years, test_year, min_years)
    model = fit_gbm(train, cols, gbm_params)
    test = test.copy()
    test["predicted"] = test["expected"] + model.predict(test[cols])
    test["adjusted_anomaly"] = test["ndvi"] - test["predicted"]
    return test
