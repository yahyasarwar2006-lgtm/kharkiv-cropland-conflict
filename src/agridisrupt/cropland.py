"""Cropland share per grid cell from the ESA WorldCereal 2021 temporary-crops map."""

import math

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.errors import WindowError
from rasterio.features import geometry_mask
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import Window, from_bounds
from shapely.geometry import box

CROP_VALUE = 100    # WorldCereal legend: 100 = temporary crops
NODATA_VALUE = 255  # 0 = other land cover, 255 = no data


def cropland_fraction(grid: gpd.GeoDataFrame, tile_paths: list) -> pd.DataFrame:
    """Return, per grid cell, the share of valid WorldCereal pixels that are cropland.

    Counts are summed across all tiles, so a cell that straddles two WorldCereal
    zones is handled correctly (each zone's file is no-data outside the zone).
    Output columns: cell_id, crop_pixels, valid_pixels, cropland_fraction.
    """
    crop = np.zeros(len(grid), dtype=np.int64)
    valid = np.zeros(len(grid), dtype=np.int64)

    for path in tile_paths:
        with rasterio.open(path) as src:
            tile_box = box(*src.bounds)
            full = Window(0, 0, src.width, src.height)
            cells = grid.to_crs(src.crs)

            for i, geom in enumerate(cells.geometry):
                if not tile_box.intersects(geom):
                    continue

                w = from_bounds(*geom.bounds, transform=src.transform)
                w = Window(
                    math.floor(w.col_off), math.floor(w.row_off),
                    math.ceil(w.width) + 1, math.ceil(w.height) + 1,
                ).intersection(full)

                data = src.read(1, window=w)
                inside = geometry_mask(
                    [geom], out_shape=data.shape,
                    transform=src.window_transform(w), invert=True,
                )
                values = data[inside]
                crop[i] += np.count_nonzero(values == CROP_VALUE)
                valid[i] += np.count_nonzero(values != NODATA_VALUE)

    with np.errstate(invalid="ignore", divide="ignore"):
        fraction = np.where(valid > 0, crop / valid, np.nan)

    return pd.DataFrame({
        "cell_id": grid["cell_id"].values,
        "crop_pixels": crop,
        "valid_pixels": valid,
        "cropland_fraction": fraction,
    })


def cropland_mask_like(tile_paths: list, like) -> np.ndarray:
    """Boolean cropland mask on the exact pixel grid of `like` (a rioxarray
    DataArray, e.g. a Sentinel-2 band), resampled from the WorldCereal tiles with
    nearest neighbour so class codes are never blended. Only the window of each
    tile under `like` is read.
    """
    dst = np.full(like.shape, NODATA_VALUE, dtype=np.uint8)
    for path in tile_paths:
        with rasterio.open(path) as src:
            bounds = transform_bounds(like.rio.crs, src.crs, *like.rio.bounds())
            w = from_bounds(*bounds, transform=src.transform)
            try:
                w = Window(
                    math.floor(w.col_off) - 2, math.floor(w.row_off) - 2,
                    math.ceil(w.width) + 5, math.ceil(w.height) + 5,
                ).intersection(Window(0, 0, src.width, src.height))
            except WindowError:  # tile does not overlap
                continue
            tile_part = np.full(like.shape, NODATA_VALUE, dtype=np.uint8)
            reproject(
                src.read(1, window=w), tile_part,
                src_transform=src.window_transform(w), src_crs=src.crs, src_nodata=NODATA_VALUE,
                dst_transform=like.rio.transform(), dst_crs=like.rio.crs, dst_nodata=NODATA_VALUE,
                resampling=Resampling.nearest,
            )
            # zones don't overlap in valid pixels: fill only where nothing is set yet
            fill = (dst == NODATA_VALUE) & (tile_part != NODATA_VALUE)
            dst[fill] = tile_part[fill]
    return dst == CROP_VALUE
