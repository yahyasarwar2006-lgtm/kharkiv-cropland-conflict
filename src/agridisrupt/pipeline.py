"""One season of Sentinel-2 -> 14-day cropland NDVI composites per 5 km cell.

Shared by the pilot (scripts/run_pilot_timeseries.py) and the whole-oblast run
(scripts/run_oblast_timeseries.py), so both use exactly the same processing.
"""

import resource
import socket
import time

import numpy as np
import pandas as pd
import planetary_computer

from agridisrupt.composites import cell_label_raster, cell_stats, median_composite, n_periods, period_dates, period_index
from agridisrupt.cropland import cropland_mask_like
from agridisrupt.sentinel2 import check_offset_consistency, load_scene_bands, masked_ndvi, one_scene_per_date


def peak_memory_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9  # bytes on macOS


def freshly_signed(item):
    """Copy of item whose asset links carry a fresh Planetary Computer access token.

    planetary_computer.sign() leaves links that already have a token untouched, even
    when that token has expired (it did after ~a day on 6 Oct 2026 -> HTTP 403), so the
    old token is stripped first."""
    item = item.clone()
    for asset in item.assets.values():
        asset.href = asset.href.split("?", 1)[0]
    return planetary_computer.sign(item)


def internet_ok(host: str = "planetarycomputer.microsoft.com") -> bool:
    try:
        socket.create_connection((host, 443), timeout=10).close()
        return True
    except OSError:
        return False


def wait_for_internet(max_hours: float = 6) -> None:
    """Block until the internet is back (checked every 30 s), so an outage pauses the
    run instead of making every scene fail (seen on 7 Oct 2026: 'Could not resolve host')."""
    if internet_ok():
        return
    print("    no internet connection - waiting for it to come back ...", flush=True)
    deadline = time.time() + max_hours * 3600
    while not internet_ok():
        if time.time() > deadline:
            raise ConnectionError(f"no internet for {max_hours} h")
        time.sleep(30)
    print("    internet is back", flush=True)


def load_with_retry(item, bbox, resolution_m, attempts=3):
    for attempt in range(1, attempts + 1):
        try:
            return load_scene_bands(freshly_signed(item), bbox, resolution_m)
        except Exception as err:  # network hiccups on remote reads
            if attempt == attempts:
                raise
            print(f"    retry {attempt} for {item.id}: {err}", flush=True)
            wait_for_internet()  # an outage does not use up the retries' purpose
            time.sleep(10 * attempt)


def season_items(catalog, year: int, bbox: tuple, config: dict, tile: str | None = None) -> list:
    """Scenes for one season over bbox: optionally one tile only, whole-tile cloud
    <= timeseries_max_scene_cloud, one scene per date, offset guard checked."""
    s2 = config["sentinel2"]
    end = period_dates(year, n_periods(year, config) - 1, config)[1]
    for attempt in range(1, 4):  # the catalogue connection occasionally drops (7 Oct 2026)
        try:
            items = catalog.search(
                collections=[s2["collection"]], bbox=bbox,
                datetime=f"{year}-{config['time']['season_start_month']:02d}-01/{end:%Y-%m-%d}",
            ).item_collection()
            break
        except Exception as err:
            if attempt == 3:
                raise
            print(f"    catalogue search failed ({err}); retrying in {30 * attempt} s", flush=True)
            time.sleep(30 * attempt)
    items = [i for i in items
             if i.properties["eo:cloud_cover"] <= s2["timeseries_max_scene_cloud"]
             and (tile is None or i.properties.get("s2:mgrs_tile") == tile)]
    items = one_scene_per_date(items)
    for item in items:
        check_offset_consistency(item.datetime, item.properties["s2:processing_baseline"], config)
    return items


def process_season(items: list, year: int, cells, bbox: tuple, worldcereal_tiles: list, config: dict,
                   resolution_m: int, with_uncorrected: bool = False, verbose: bool = True):
    """Composite one season of scenes (all from ONE Sentinel-2 tile, so they share a
    pixel grid) into per-cell, per-period cropland NDVI. Returns (composites, scenes)."""
    periods = period_index([i.datetime for i in items], config)
    grid_ref = labels = crop = None
    rows, scene_rows = [], []
    for p in range(n_periods(year, config)):
        p_items = [item for item, idx in zip(items, periods) if idx == p]
        stack, stack_raw = [], []
        for item in p_items:
            try:
                red, nir, scl = load_with_retry(item, bbox, resolution_m)
            except Exception as err:
                # one unreadable scene (e.g. a transient server error, 6 Oct 2026) must not
                # stop a multi-hour run: skip it, but record it for the data-quality report
                print(f"    SKIPPED {item.id}: {str(err)[:150]}", flush=True)
                scene_rows.append({"date": item.datetime.date(), "period": p,
                                   "tile": item.properties.get("s2:mgrs_tile"), "skipped": True})
                continue
            if grid_ref is None:  # first scene of the season fixes the pixel grid
                grid_ref = red
                labels = cell_label_raster(cells, red)
                crop = cropland_mask_like(worldcereal_tiles, red)
            elif red.shape != grid_ref.shape or red.rio.transform() != grid_ref.rio.transform():
                raise ValueError(f"{item.id} is on a different pixel grid than the first scene")

            ndvi = masked_ndvi(red, nir, scl, item.datetime, config).values
            stack.append(ndvi)
            if with_uncorrected:
                stack_raw.append(masked_ndvi(red, nir, scl, item.datetime, config, correct_offset=False).values)
            scene_rows.append({
                "date": item.datetime.date(), "period": p, "tile": item.properties.get("s2:mgrs_tile"),
                "baseline": item.properties["s2:processing_baseline"],
                "scene_cloud": item.properties["eo:cloud_cover"],
                "clear_cropland_share": float(np.mean(~np.isnan(ndvi[crop & (labels > 0)]))),
                "skipped": False,
            })

        first, last = period_dates(year, p, config)
        if stack:
            stats = cell_stats(median_composite(np.stack(stack)), labels, crop, list(cells["cell_id"]))
            if stack_raw:
                raw = cell_stats(median_composite(np.stack(stack_raw)), labels, crop, list(cells["cell_id"]))
                stats["ndvi_median_uncorrected"] = raw["ndvi_median"].values
        else:  # no usable scene in this period
            stats = pd.DataFrame({"cell_id": cells["cell_id"].values, "crop_pixels": np.nan,
                                  "valid_share": 0.0, "ndvi_median": np.nan})
        stats.insert(0, "year", year)
        stats.insert(1, "period", p)
        stats.insert(2, "period_start", first.date())
        stats.insert(3, "period_end", last.date())
        stats.insert(4, "n_scenes", len(stack))                 # scenes actually used
        stats.insert(5, "n_skipped", len(p_items) - len(stack))  # unreadable scenes
        rows.append(stats)
        if verbose:
            print(f"  period {p:2d} ({first:%d %b}-{last:%d %b}): {len(stack)} scenes, "
                  f"median cell valid share {stats['valid_share'].median():.0%}", flush=True)
    return pd.concat(rows, ignore_index=True), pd.DataFrame(scene_rows)
