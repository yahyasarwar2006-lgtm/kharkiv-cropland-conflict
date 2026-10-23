"""14-day median composites and per-cell summaries of cropland NDVI."""

import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
from rasterio.features import rasterize


def _season_bounds(year: int, config: dict):
    t = config["time"]
    start = pd.Timestamp(year=year, month=t["season_start_month"], day=1)
    end = pd.Timestamp(year=year, month=t["season_end_month"], day=1) + pd.offsets.MonthEnd(0)
    return start, end


def n_periods(year: int, config: dict) -> int:
    start, end = _season_bounds(year, config)
    return ((end - start).days + 1) // config["time"]["composite_days"]


def period_index(dates, config: dict) -> np.ndarray:
    """0-based composite period for each date, counted from the season start
    (1 April). Leftover days at the season end join the last period; dates
    outside the season get -1."""
    days = config["time"]["composite_days"]
    out = []
    for d in pd.to_datetime(list(dates)):
        d = pd.Timestamp(d.date())  # drop time of day and time zone
        start, end = _season_bounds(d.year, config)
        if not start <= d <= end:
            out.append(-1)
            continue
        out.append(min((d - start).days // days, n_periods(d.year, config) - 1))
    return np.array(out, dtype=int)


def period_dates(year: int, index: int, config: dict):
    """First and last calendar day of composite period `index` in `year`."""
    days = config["time"]["composite_days"]
    start, season_end = _season_bounds(year, config)
    first = start + pd.Timedelta(days=index * days)
    last = season_end if index == n_periods(year, config) - 1 else first + pd.Timedelta(days=days - 1)
    return first, last


def median_composite(stack: np.ndarray) -> np.ndarray:
    """Per-pixel median over time (axis 0), ignoring NaN (cloudy) values.
    Pixels that were never clear stay NaN."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)  # all-NaN pixels
        return np.nanmedian(stack, axis=0)


def cell_stats(composite: np.ndarray, cell_labels: np.ndarray, crop_mask: np.ndarray, cell_ids: list) -> pd.DataFrame:
    """Summarise a composite per grid cell, using cropland pixels only.

    cell_labels: same shape as composite, value k (1..n) = inside cell_ids[k-1], 0 = outside.
    Returns cell_id, crop_pixels, valid_share (share of cropland pixels with a
    clear value) and ndvi_median (median over those clear cropland pixels).
    """
    rows = []
    for k, cell_id in enumerate(cell_ids, start=1):
        values = composite[(cell_labels == k) & crop_mask]
        clear = values[~np.isnan(values)]
        rows.append({
            "cell_id": cell_id,
            "crop_pixels": values.size,
            "valid_share": clear.size / values.size if values.size else np.nan,
            "ndvi_median": float(np.median(clear)) if clear.size else np.nan,
        })
    return pd.DataFrame(rows)


def cell_label_raster(cells: gpd.GeoDataFrame, like) -> np.ndarray:
    """Raster on the pixel grid of `like` where value k (1..n) marks pixels whose
    centre lies in the k-th cell of `cells` (0 = in no cell)."""
    cells = cells.to_crs(like.rio.crs)
    shapes = [(geom, k) for k, geom in enumerate(cells.geometry, start=1)]
    return rasterize(shapes, out_shape=like.shape, transform=like.rio.transform(), fill=0, dtype="int16")
