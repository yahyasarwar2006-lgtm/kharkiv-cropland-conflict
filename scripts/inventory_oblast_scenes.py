"""Stage 3, step 1: list every Sentinel-2 scene over the oblast (Apr-Oct, all study
years, metadata only) and assign each cropland cell (>= min cropland share) to ONE tile.

Run: python scripts/inventory_oblast_scenes.py
Outputs: data/interim/oblast_scene_inventory.csv, data/interim/oblast_cell_tiles.csv
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd
import planetary_computer
import pystac_client
from shapely.geometry import shape
from shapely.ops import unary_union

from agridisrupt.aoi import assign_cells_to_tiles
from agridisrupt.config import load_config
from agridisrupt.sentinel2 import STAC_API_URL


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    interim = Path(config["paths"]["data_interim"])
    t = config["time"]

    cells = gpd.read_file(interim / "kharkiv_grid_5km_cropland.gpkg")
    cells = cells[cells["cropland_fraction"] >= config["grid"]["min_cropland_fraction"]].reset_index(drop=True)
    bbox = tuple(cells.to_crs("EPSG:4326").total_bounds)

    catalog = pystac_client.Client.open(STAC_API_URL, modifier=planetary_computer.sign_inplace)
    rows, footprints = [], {}
    for year in range(t["start_year"], t["end_year"] + 1):
        start = f"{year}-{t['season_start_month']:02d}-01"
        end = (pd.Timestamp(year=year, month=t["season_end_month"], day=1) + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
        items = catalog.search(collections=[config["sentinel2"]["collection"]], bbox=bbox,
                               datetime=f"{start}/{end}").item_collection()
        for item in items:
            tile = item.properties["s2:mgrs_tile"]
            rows.append({"id": item.id, "datetime": item.datetime, "tile": tile,
                         "cloud_cover": item.properties["eo:cloud_cover"],
                         "baseline": item.properties.get("s2:processing_baseline"),
                         "orbit": item.properties.get("sat:relative_orbit")})
            footprints.setdefault(tile, []).append(shape(item.geometry))
        print(f"{year}: {len(items)} scenes")

    df = pd.DataFrame(rows)
    df["year"] = pd.to_datetime(df["datetime"], utc=True).dt.year
    df["date"] = pd.to_datetime(df["datetime"], utc=True).dt.date
    df.sort_values("datetime").to_csv(interim / "oblast_scene_inventory.csv", index=False)

    # a tile's usable area = union of where its scenes actually have data (orbits differ)
    tiles = gpd.GeoDataFrame({"tile_id": list(footprints)},
                             geometry=[unary_union(g) for g in footprints.values()], crs="EPSG:4326")
    cells["tile_id"] = cells["cell_id"].map(assign_cells_to_tiles(cells, tiles))
    cells[["cell_id", "tile_id", "cropland_fraction"]].to_csv(interim / "oblast_cell_tiles.csv", index=False)

    usable = df[df["cloud_cover"] <= config["sentinel2"]["timeseries_max_scene_cloud"]]
    per_tile_dates = usable.groupby(["tile", "year"])["date"].nunique().unstack("year")
    summary = pd.DataFrame({"cells": cells["tile_id"].value_counts()}).join(per_tile_dates, how="outer")
    print(f"\nTiles touching the oblast: {sorted(footprints)}")
    print(f"Cropland cells: {len(cells)}; assigned to a tile: {cells['tile_id'].notna().sum()}; "
          f"unassigned (no tile fully contains them): {cells['tile_id'].isna().sum()}")
    print("\nCells per tile, and usable dates per season (scene cloud <= "
          f"{config['sentinel2']['timeseries_max_scene_cloud']}%):")
    print(summary.fillna(0).astype(int).to_string())
    print(f"\nScenes to read (cloud filter, one per tile+date), tiles with cells only: "
          f"{usable[usable['tile'].isin(cells['tile_id'].dropna())].groupby(['tile', 'date']).ngroups}")


if __name__ == "__main__":
    main()
