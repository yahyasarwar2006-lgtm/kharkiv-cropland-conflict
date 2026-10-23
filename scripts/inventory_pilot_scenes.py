"""Experiment 1, step 1: list every Sentinel-2 scene over the pilot block
(Apr-Oct of each pilot year) without downloading any pixels.

Run: python scripts/inventory_pilot_scenes.py
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd
import planetary_computer
import pystac_client

from agridisrupt.config import load_config
from agridisrupt.sentinel2 import STAC_API_URL


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    block = gpd.read_file(Path(config["paths"]["data_interim"]) / "pilot_block.gpkg")
    bbox = tuple(block.to_crs("EPSG:4326").total_bounds)
    months = (config["time"]["season_start_month"], config["time"]["season_end_month"])

    catalog = pystac_client.Client.open(STAC_API_URL, modifier=planetary_computer.sign_inplace)
    rows = []
    for year in config["pilot"]["years"]:
        start = f"{year}-{months[0]:02d}-01"
        end = (pd.Timestamp(year=year, month=months[1], day=1) + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
        items = catalog.search(
            collections=[config["sentinel2"]["collection"]], bbox=bbox, datetime=f"{start}/{end}"
        ).item_collection()
        for item in items:
            rows.append({
                "id": item.id,
                "datetime": pd.Timestamp(item.datetime),
                "tile": item.properties.get("s2:mgrs_tile"),
                "cloud_cover": item.properties.get("eo:cloud_cover"),
                "baseline": item.properties.get("s2:processing_baseline"),
            })

    df = pd.DataFrame(rows)
    df["year"] = df["datetime"].dt.year
    df["date"] = df["datetime"].dt.date

    out = Path(config["paths"]["data_interim"]) / "pilot_scene_inventory.csv"
    df.sort_values("datetime").to_csv(out, index=False)

    print(f"Pilot bbox (lon/lat): {tuple(round(v, 3) for v in bbox)}")
    print(f"Scenes found: {len(df)}  |  tiles: {sorted(df['tile'].unique())}")
    print("\nPer year: scenes, distinct dates, and dates with scene cloud cover < 20 / < 50 / < 80 %")
    for year, g in df.groupby("year"):
        best = g.groupby("date")["cloud_cover"].min()  # clearest tile per date
        print(f"  {year}: {len(g):4d} scenes, {g['date'].nunique():3d} dates | "
              f"{(best < 20).sum():3d} / {(best < 50).sum():3d} / {(best < 80).sum():3d}")
    print("\nProcessing baseline by year (count of scenes):")
    print(pd.crosstab(df["year"], df["baseline"]).to_string())
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
