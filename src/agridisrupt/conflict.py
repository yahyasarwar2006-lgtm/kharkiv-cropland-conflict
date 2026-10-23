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


def load_acled_events(csv_path, event_types: list[str], max_geo_precision: int,
                      bounds: tuple) -> gpd.GeoDataFrame:
    """Load ACLED events of the given types, located to geo_precision <= max_geo_precision, inside
    bounds = (min_lon, min_lat, max_lon, max_lat). Any country: events just across the border also
    count as nearby. Returns points in EPSG:4326 with a `date` column."""
    columns = ["event_id_cnty", "event_date", "event_type", "latitude", "longitude", "geo_precision"]
    events = pd.read_csv(csv_path, usecols=columns, parse_dates=["event_date"])
    lon0, lat0, lon1, lat1 = bounds
    keep = (
        events["event_type"].isin(event_types)
        & (events["geo_precision"] <= max_geo_precision)
        & events["longitude"].between(lon0, lon1)
        & events["latitude"].between(lat0, lat1)
    )
    events = events[keep].rename(columns={"event_date": "date"})
    return gpd.GeoDataFrame(
        events,
        geometry=gpd.points_from_xy(events["longitude"], events["latitude"]),
        crs="EPSG:4326",
    )


def season_exposure(events: gpd.GeoDataFrame, cells: gpd.GeoDataFrame, buffer_m: float,
                    years: list[int], war_start: str, season_end: str) -> pd.DataFrame:
    """Events per cell and growing season: inside the cell or within buffer_m of it, from 1 Jan
    (or war_start, if later in that year) to season_end ("MM-DD"). Cells without events get 0.
    Aggregated counts only (rule 6)."""
    zones = cells[["cell_id", "geometry"]].copy()
    zones["geometry"] = zones.buffer(buffer_m)
    hits = gpd.sjoin(events.to_crs(cells.crs)[["date", "geometry"]], zones, predicate="within")
    out = []
    for year in years:
        start = max(pd.Timestamp(f"{year}-01-01"), pd.Timestamp(war_start)) if year == pd.Timestamp(war_start).year \
            else pd.Timestamp(f"{year}-01-01")
        end = pd.Timestamp(f"{year}-{season_end}")
        n = hits[hits["date"].between(start, end)].groupby("cell_id").size()
        out.append(pd.DataFrame({"cell_id": cells["cell_id"], "year": year,
                                 "events": n.reindex(cells["cell_id"], fill_value=0).to_numpy()}))
    return pd.concat(out, ignore_index=True)


def exposure_group(events: pd.Series, low_max: int, high_min: int) -> pd.Series:
    """'low' (<= low_max events), 'high' (>= high_min), otherwise 'some'."""
    group = pd.Series("some", index=events.index)
    group[events <= low_max] = "low"
    group[events >= high_min] = "high"
    return group
