"""Season-level features from the panel (one row per cell x year)."""

import pandas as pd


def season_peaks(panel: pd.DataFrame) -> pd.DataFrame:
    """Highest NDVI of each cell's season, the period it occurred in, and how many
    periods had a usable NDVI value. Empty periods are ignored."""
    seen = panel.dropna(subset=["ndvi"])
    top = seen.loc[seen.groupby(["cell_id", "year"])["ndvi"].idxmax(), ["cell_id", "year", "ndvi", "period"]]
    top = top.rename(columns={"ndvi": "peak_ndvi", "period": "peak_period"})
    n_valid = seen.groupby(["cell_id", "year"]).size().rename("n_valid").reset_index()
    return top.merge(n_valid, on=["cell_id", "year"]).sort_values(["cell_id", "year"]).reset_index(drop=True)


def season_shape(panel: pd.DataFrame, late_periods: list[int], late_min_periods: int) -> pd.DataFrame:
    """Season-shape measures per cell x year (rule 4: level alone can miss weedy, unharvested fields):
    peak_ndvi, peak_period, and late_ndvi = mean NDVI over `late_periods` (does the field brown down
    after harvest?), left empty if fewer than `late_min_periods` of them have a usable value."""
    late = panel[panel["period"].isin(late_periods)].groupby(["cell_id", "year"])["ndvi"].agg(["mean", "count"])
    late["late_ndvi"] = late["mean"].where(late["count"] >= late_min_periods)
    shape = season_peaks(panel).merge(late["late_ndvi"].reset_index(), on=["cell_id", "year"], how="outer")
    return shape.sort_values(["cell_id", "year"]).reset_index(drop=True)


def season_parts(config: dict) -> dict[str, list[int]]:
    """Parts of the season from the config, as lists of period numbers: {"spring": [0, ..., 4], ...}."""
    return {name: list(range(lo, hi + 1)) for name, (lo, hi) in config["analysis"]["season_parts"].items()}


def season_part_means(df: pd.DataFrame, column: str, parts: dict[str, list[int]]) -> pd.DataFrame:
    """Mean of `column` per cell, year and part of the season (one column per part)."""
    out = [df[df["period"].isin(periods)].groupby(["cell_id", "year"])[column].mean().rename(name)
           for name, periods in parts.items()]
    return pd.concat(out, axis=1).reset_index()
