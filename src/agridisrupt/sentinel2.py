"""Search, load, and process Sentinel-2 L2A scenes from Microsoft Planetary Computer."""

import os

import pandas as pd
import planetary_computer
import pystac_client
import rioxarray
import xarray as xr

STAC_API_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"

# GDAL settings for faster remote (cloud-optimised GeoTIFF) reads; user settings win
for _key, _value in {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",   # don't list the remote folder on open
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",   # fewer, larger HTTP requests
    "GDAL_HTTP_MULTIPLEX": "YES",
    "VSI_CACHE": "TRUE",
    # a stalled download once hung the run for 15+ min: time out and retry instead
    "GDAL_HTTP_TIMEOUT": "60",
    "GDAL_HTTP_MAX_RETRY": "3",
    "GDAL_HTTP_RETRY_DELAY": "5",
}.items():
    os.environ.setdefault(_key, _value)


def search_scenes(config: dict, bbox: tuple, date_range: str) -> list:
    """Search for Sentinel-2 scenes covering bbox (WGS84: minx, miny, maxx, maxy)
    within date_range (e.g. "2021-06-01/2021-08-31") and under the configured
    max cloud cover. Returns items sorted from least to most cloudy.
    """
    catalog = pystac_client.Client.open(STAC_API_URL, modifier=planetary_computer.sign_inplace)

    search = catalog.search(
        collections=[config["sentinel2"]["collection"]],
        bbox=bbox,
        datetime=date_range,
        query={"eo:cloud_cover": {"lt": config["sentinel2"]["max_cloud_cover"]}},
    )
    items = list(search.items())
    items.sort(key=lambda item: item.properties["eo:cloud_cover"])
    return items


def apply_offset(band: xr.DataArray, acquisition_date, config: dict) -> xr.DataArray:
    """Subtract the fixed reflectance offset Sentinel-2 added from 25 Jan 2022
    onward (processing baseline 04.00). Without this, NDVI shows a fake jump
    exactly at that date — and so at the start of the war.
    """
    offset_date = pd.Timestamp(config["sentinel2"]["offset_start_date"], tz="UTC")
    if pd.Timestamp(acquisition_date) >= offset_date:
        return band - config["sentinel2"]["offset_value"]
    return band


def compute_ndvi(red: xr.DataArray, nir: xr.DataArray) -> xr.DataArray:
    """NDVI = (NIR - Red) / (NIR + Red). Both inputs must already be float
    and offset-corrected (see apply_offset)."""
    return (nir - red) / (nir + red)


def check_offset_consistency(acquisition_date, baseline: str, config: dict) -> None:
    """Raise if the date rule used by apply_offset disagrees with the scene's
    processing baseline (baselines >= offset_min_baseline carry the offset)."""
    by_date = pd.Timestamp(acquisition_date) >= pd.Timestamp(config["sentinel2"]["offset_start_date"], tz="UTC")
    by_baseline = float(baseline) >= float(config["sentinel2"]["offset_min_baseline"])
    if by_date != by_baseline:
        raise ValueError(
            f"Offset rule mismatch for scene on {acquisition_date}: baseline {baseline} "
            f"{'has' if by_baseline else 'has no'} offset, but the date rule says the opposite"
        )


def one_scene_per_date(items: list) -> list:
    """Keep one scene per acquisition date and tile: the one with the highest
    processing baseline (ESA re-processed some dates, and both copies are listed)."""
    best = {}
    for item in items:
        key = (item.datetime.date(), item.properties.get("s2:mgrs_tile"))
        baseline = float(item.properties.get("s2:processing_baseline", 0))
        if key not in best or baseline > best[key][0]:
            best[key] = (baseline, item)
    return sorted((item for _, item in best.values()), key=lambda i: i.datetime)


def load_scene_bands(item, bbox: tuple, resolution_m: int = 10):
    """Load one scene's red, NIR (float32, raw values) and SCL clipped to bbox
    (WGS84), all on one pixel grid. All scenes of the same tile come back on the
    same grid.

    resolution_m=10: native B04/B08; SCL (natively 20 m) is resampled onto it.
    resolution_m=20: the files' built-in half-resolution overview of B04/B08
    (~4x fewer pixels to download); SCL is then used at its native 20 m.
    """
    overview = {10: {}, 20: {"overview_level": 0}}[resolution_m]
    # No dask chunks here: opened lazily without chunks, clip_box makes rasterio
    # fetch only the bbox window. With chunks=True whole blocks were downloaded
    # and then cut (~98 s vs ~7 s per scene, measured 29 Sep 2026).
    red = rioxarray.open_rasterio(item.assets["B04"].href, **overview).squeeze("band", drop=True)
    nir = rioxarray.open_rasterio(item.assets["B08"].href, **overview).squeeze("band", drop=True)
    scl = rioxarray.open_rasterio(item.assets["SCL"].href).squeeze("band", drop=True)

    # cast to float before any arithmetic: the raw bands are uint16, and
    # nir - red would silently wrap around to a huge number wherever red > nir
    red = red.rio.clip_box(*bbox, crs="EPSG:4326").astype("float32")
    nir = nir.rio.clip_box(*bbox, crs="EPSG:4326").astype("float32")
    scl = scl.rio.clip_box(*bbox, crs="EPSG:4326")

    # put SCL on exactly the red/nir grid (at 10 m this resamples 20 m -> 10 m;
    # default resampling is nearest, which keeps class codes intact)
    scl_matched = scl.rio.reproject_match(red)
    return red, nir, scl_matched


def masked_ndvi(red, nir, scl, acquisition_date, config: dict, correct_offset: bool = True):
    """NDVI with the 2022 offset corrected (unless correct_offset=False) and every
    pixel that SCL does not class as clear land set to NaN."""
    if correct_offset:
        red = apply_offset(red, acquisition_date, config)
        nir = apply_offset(nir, acquisition_date, config)
    ndvi = compute_ndvi(red, nir)
    return ndvi.where(scl.isin(config["sentinel2"]["valid_scl_classes"]))


def load_scene_ndvi(item, bbox: tuple, config: dict) -> xr.DataArray:
    """Load one STAC item clipped to bbox (WGS84) and return cloud-masked,
    offset-corrected NDVI as a 2D DataArray."""
    red, nir, scl = load_scene_bands(item, bbox)
    return masked_ndvi(red, nir, scl, item.datetime, config)
