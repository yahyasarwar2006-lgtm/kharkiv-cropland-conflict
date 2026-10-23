"""Join the NDVI composites and the climate features into one panel:
one row per cell x year x 14-day period."""

from pathlib import Path

import pandas as pd

KEY = ["cell_id", "year", "period"]
COLUMNS = KEY + [
    "period_start", "tile", "n_scenes", "valid_share", "ndvi_raw", "ndvi",
    "t2m_mean", "t2m_anom", "swvl1_mean", "precip_sum", "precip_30d", "precip_60d",
]


def load_composites(folder: str | Path) -> pd.DataFrame:
    """Stack every composites_{year}_{tile}.csv in `folder` into one table."""
    files = sorted(Path(folder).glob("composites_*.csv"))
    if not files:
        raise FileNotFoundError(f"no composites_*.csv in {folder}")
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)


def build_panel(ndvi: pd.DataFrame, climate: pd.DataFrame, min_valid_share: float) -> pd.DataFrame:
    """Merge NDVI and climate on (cell_id, year, period).

    Every key must appear exactly once in each table, and in both tables:
    a row lost or doubled here would silently bias everything downstream.
    `ndvi_raw` is the composite as computed; `ndvi` is emptied where less than
    `min_valid_share` of the cell's cropland was clear (those values read too low).
    """
    panel = ndvi.rename(columns={"ndvi_median": "ndvi_raw"}).merge(
        climate, on=KEY, how="inner", validate="one_to_one")
    if len(panel) != len(ndvi) or len(panel) != len(climate):
        raise ValueError(f"keys do not match: {len(ndvi)} NDVI rows, {len(climate)} climate rows, "
                         f"{len(panel)} in both")
    panel["ndvi"] = panel["ndvi_raw"].where(panel["valid_share"] >= min_valid_share)
    return panel[COLUMNS].sort_values(KEY).reset_index(drop=True)
