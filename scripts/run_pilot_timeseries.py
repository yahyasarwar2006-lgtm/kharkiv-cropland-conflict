"""Experiment 1: 14-day cropland NDVI composites per 5 km cell for the pilot block.

Processes one season at a time and saves one CSV per year to data/interim/
(finished years are skipped on re-run). 2022+ are also computed WITHOUT the
offset correction, only to show the size of the jump the correction removes.

Run: python scripts/run_pilot_timeseries.py                  (all pilot years, 10 m)
     python scripts/run_pilot_timeseries.py 2021             (one year)
     python scripts/run_pilot_timeseries.py 2021 --res 20    (read at 20 m; saved as ..._20m.csv)
     python scripts/run_pilot_timeseries.py 2021 --suffix _retime   (extra copy, e.g. to re-time a run)
"""

import argparse
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import planetary_computer
import pystac_client

from agridisrupt.config import load_config
from agridisrupt.pipeline import peak_memory_gb, process_season, season_items
from agridisrupt.sentinel2 import STAC_API_URL


def process_year(year, config, block, bbox, tiles, catalog, resolution_m):
    start = time.time()
    items = season_items(catalog, year, bbox, config)
    print(f"{year}: {len(items)} scenes after cloud filter + de-duplication")
    composites, scenes = process_season(items, year, block, bbox, tiles, config, resolution_m,
                                        with_uncorrected=year >= 2022)
    minutes = (time.time() - start) / 60
    print(f"{year} done in {minutes:.1f} min, peak memory so far {peak_memory_gb():.2f} GB")
    return composites, scenes, minutes


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    interim = Path(config["paths"]["data_interim"])
    block = gpd.read_file(interim / "pilot_block.gpkg")
    bbox = tuple(block.to_crs("EPSG:4326").total_bounds)
    tiles = [Path(config["paths"]["data_raw"]) / "worldcereal" / f"{a}_temporarycrops_classification.tif"
             for a in config["cropland"]["aez_ids"]]
    catalog = pystac_client.Client.open(STAC_API_URL, modifier=planetary_computer.sign_inplace)

    parser = argparse.ArgumentParser()
    parser.add_argument("years", nargs="*", type=int)
    parser.add_argument("--res", type=int, default=10, choices=[10, 20], help="read resolution in metres")
    parser.add_argument("--suffix", default="", help="extra text for output file names")
    args = parser.parse_args()
    years = args.years or config["pilot"]["years"]
    suffix = ("" if args.res == 10 else f"_{args.res}m") + args.suffix

    timing_path = interim / "pilot_run_log.csv"
    for year in years:
        out = interim / f"pilot_composites_{year}{suffix}.csv"
        if out.exists():
            print(f"{out} exists, skipping {year}")
            continue
        composites, scenes, minutes = process_year(year, config, block, bbox, tiles, catalog, args.res)
        composites.to_csv(out, index=False)
        scenes.to_csv(interim / f"pilot_scenes_{year}{suffix}.csv", index=False)
        pd.DataFrame([{"year": year, "minutes": round(minutes, 1), "scenes": len(scenes),
                       "peak_memory_gb": round(peak_memory_gb(), 2),
                       "resolution_m": args.res, "run": suffix or "main"}]).to_csv(
            timing_path, mode="a", header=not timing_path.exists(), index=False)
        print(f"Saved {out}")


if __name__ == "__main__":
    main()
