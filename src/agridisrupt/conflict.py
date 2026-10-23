"""Conflict event data: load UCDP GED events and count them near areas of interest.

Output is always aggregated counts per area, never individual event maps
(ethics: historical and aggregated only, no front-line tracking).
"""

import geopandas as gpd
import pandas as pd


def load_ucdp_events(
    csv_path, country: str, period: tuple, max_where_prec: int
) -> gpd.GeoDataFrame:
    """Load UCDP GED events for one country whose start date falls in period
    (inclusive "YYYY-MM-DD" strings) and whose location precision (where_prec)
    is at most max_where_prec. Returns points in EPSG:4326.
    """
    columns = ["id", "country", "date_start", "where_prec", "latitude", "longitude", "best"]
    events = pd.read_csv(csv_path, usecols=columns, parse_dates=["date_start"])

    start, end = pd.Timestamp(period[0]), pd.Timestamp(period[1])
    keep = (
        (events["country"] == country)
        & events["date_start"].between(start, end)
        & (events["where_prec"] <= max_where_prec)
    )
    events = events[keep]

    return gpd.GeoDataFrame(
        events,
        geometry=gpd.points_from_xy(events["longitude"], events["latitude"]),
        crs="EPSG:4326",
    )


def count_events_near(events: gpd.GeoDataFrame, area, area_crs: str, buffer_m: float) -> int:
    """Number of events within buffer_m metres of area (a shapely geometry in a
    metres-based CRS, area_crs)."""
    zone = area.buffer(buffer_m)
    return int(events.to_crs(area_crs).within(zone).sum())
