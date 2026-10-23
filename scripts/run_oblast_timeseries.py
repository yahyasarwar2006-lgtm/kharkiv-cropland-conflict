"""Stage 3: 14-day cropland NDVI composites for every cropland cell in the oblast.

Works one (year, tile) piece at a time: each cell was assigned to ONE Sentinel-2
tile by scripts/inventory_oblast_scenes.py, and only the window around that tile's
cells is read, at the resolution set in the config (sentinel2.read_resolution_m).
Each piece is saved to data/interim/oblast/ and skipped on re-run, so the run can
be stopped and resumed at any time.

Run: python scripts/run_oblast_timeseries.py                 (all years, all tiles)
     python scripts/run_oblast_timeseries.py 2021            (one year)
     python scripts/run_oblast_timeseries.py 2021 --tile 36UYV   (one piece, e.g. a trial)
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

MAX_MEMORY_GB = 4.0  # same limit as Experiment 1 check 4 (half of the 8 GB laptop)
# a piece is only saved if at most this many scenes were unreadable (whichever is larger)
MAX_SKIPPED_SCENES = 2
MAX_SKIPPED_SHARE = 0.05


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    interim = Path(config["paths"]["data_interim"])
    out_dir = interim / "oblast"
    out_dir.mkdir(exist_ok=True)
    res = config["sentinel2"]["read_resolution_m"]
    t = config["time"]

    parser = argparse.ArgumentParser()
    parser.add_argument("years", nargs="*", type=int)
    parser.add_argument("--tile", help="process only this tile")
    parser.add_argument("--max-pieces", type=int, default=None,
                        help="exit after this many new pieces (a fresh process resets memory)")
    args = parser.parse_args()
    years = args.years or list(range(t["start_year"], t["end_year"] + 1))

    cells = gpd.read_file(interim / "kharkiv_grid_5km_cropland.gpkg")
    cells = cells.merge(pd.read_csv(interim / "oblast_cell_tiles.csv")[["cell_id", "tile_id"]], on="cell_id")
    tiles = sorted(cells["tile_id"].dropna().unique())
    if args.tile:
        tiles = [args.tile]
    worldcereal = [Path(config["paths"]["data_raw"]) / "worldcereal" / f"{a}_temporarycrops_classification.tif"
                   for a in config["cropland"]["aez_ids"]]
    catalog = pystac_client.Client.open(STAC_API_URL, modifier=planetary_computer.sign_inplace)
    log_path = out_dir / "run_log.csv"

    pieces = [(y, tile) for y in years for tile in tiles]
    failed = []
    done_now = 0
    for i, (year, tile) in enumerate(pieces, start=1):
        out = out_dir / f"composites_{year}_{tile}.csv"
        if out.exists():
            continue
        tile_cells = cells[cells["tile_id"] == tile].reset_index(drop=True)
        bbox = tuple(tile_cells.to_crs("EPSG:4326").total_bounds)
        start = time.time()
        try:
            items = season_items(catalog, year, bbox, config, tile=tile)
            print(f"[{i}/{len(pieces)}] {year} {tile}: {len(tile_cells)} cells, {len(items)} scenes", flush=True)
            composites, scenes = process_season(items, year, tile_cells, bbox, worldcereal, config, res,
                                                verbose=False)
        except Exception as err:
            # one failed piece (e.g. a dropped connection) must not end a multi-hour run;
            # it is not saved, so the next run of this script picks it up again
            print(f"[{i}/{len(pieces)}] {year} {tile} FAILED, moving on: {str(err)[:200]}", flush=True)
            failed.append((year, tile))
            continue
        n_skipped = int(scenes["skipped"].sum()) if "skipped" in scenes else 0
        if n_skipped > max(MAX_SKIPPED_SCENES, MAX_SKIPPED_SHARE * len(items)):
            # too many missing scenes would bias the composites: redo the piece later instead
            print(f"[{i}/{len(pieces)}] {year} {tile} NOT SAVED: {n_skipped} of {len(items)} scenes "
                  f"unreadable, will be retried", flush=True)
            failed.append((year, tile))
            continue
        minutes = (time.time() - start) / 60
        composites.insert(0, "tile", tile)
        composites.to_csv(out, index=False)
        scenes.to_csv(out_dir / f"scenes_{year}_{tile}.csv", index=False)
        pd.DataFrame([{"year": year, "tile": tile, "cells": len(tile_cells), "scenes": len(items),
                       "minutes": round(minutes, 1), "peak_memory_gb": round(peak_memory_gb(), 2),
                       "resolution_m": res}]).to_csv(log_path, mode="a", header=not log_path.exists(), index=False)
        print(f"[{i}/{len(pieces)}] {year} {tile} done in {minutes:.1f} min, "
              f"median valid share {composites['valid_share'].median():.0%}, "
              f"peak memory {peak_memory_gb():.2f} GB", flush=True)
        done_now += 1
        if args.max_pieces and done_now >= args.max_pieces:
            print(f"processed {done_now} pieces in this process; exiting so a fresh one can continue", flush=True)
            return
        if peak_memory_gb() > MAX_MEMORY_GB:  # protect the 8 GB laptop; finished pieces are kept
            raise SystemExit(f"Stopping: peak memory {peak_memory_gb():.2f} GB > {MAX_MEMORY_GB} GB limit")
    if failed:
        print(f"finished with {len(failed)} failed piece(s), re-run this script to retry: {failed}", flush=True)
    else:
        print("all pieces done", flush=True)


if __name__ == "__main__":
    main()
