"""Seasonal baseline: the expected value of a cell (per period, or per season for shape measures)
= its mean over the pre-war years.

Anomaly = observed - expected. For a baseline year itself, the expected value is computed from the
OTHER baseline years (leave-one-year-out), so pre-war anomalies show how far an ordinary year strays
from "normal" without being compared with itself.
"""

import pandas as pd


def seasonal_baseline(df: pd.DataFrame, years: list[int], min_years: int,
                      value: str = "ndvi", by: tuple = ("cell_id", "period")) -> pd.DataFrame:
    """Expected `value` per `by` group from `years`; empty if fewer than `min_years` usable values."""
    base = df[df["year"].isin(years)].groupby(list(by))[value].agg(["mean", "count"])
    base.columns = ["expected", "n_years"]
    base.loc[base["n_years"] < min_years, "expected"] = float("nan")
    return base.reset_index()


def baseline_anomalies(df: pd.DataFrame, baseline_years: list[int], min_years: int,
                       value: str = "ndvi", by: tuple = ("cell_id", "period")) -> pd.DataFrame:
    """Every row of `df` with the expected `value`, the number of years behind it, and the anomaly."""
    parts = []
    for year in sorted(df["year"].unique()):
        years = [y for y in baseline_years if y != year]   # leave the year itself out
        base = seasonal_baseline(df, years, min_years, value, by)
        parts.append(df[df["year"] == year].merge(base, on=list(by), how="left"))
    out = pd.concat(parts, ignore_index=True)
    out["n_years"] = out["n_years"].fillna(0).astype(int)
    out["anomaly"] = out[value] - out["expected"]
    return out
