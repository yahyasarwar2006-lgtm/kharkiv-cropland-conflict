"""Study-area boundary and grid: load Kharkiv oblast, build a square grid over it."""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box


def load_kharkiv_boundary(config: dict, raw_path: str | Path | None = None) -> gpd.GeoDataFrame:
    """Load the Kharkiv oblast boundary and reproject it to config['crs']['grid'].

    raw_path defaults to the file scripts/download_boundary.py produces.
    """
    if raw_path is None:
        raw_path = Path(config["paths"]["data_raw"]) / "boundaries" / "ukraine_adm1.geojson"
    raw_path = Path(raw_path)

    if not raw_path.exists():
        raise FileNotFoundError(
            f"{raw_path} not found. Run scripts/download_boundary.py first."
        )

    ukraine = gpd.read_file(raw_path)

    oblast_name = config["study_area"]["oblast"]  # e.g. "Kharkiv"
    match = ukraine[ukraine["shapeName"].str.contains(oblast_name)]

    if len(match) != 1:
        raise ValueError(
            f"Expected exactly one boundary matching '{oblast_name}', found {len(match)}"
        )

    return match.to_crs(config["crs"]["grid"])


def make_grid(boundary: gpd.GeoDataFrame, cell_size_m: int) -> gpd.GeoDataFrame:
    """Build a square grid covering boundary, keeping only cells that touch it.

    boundary must already be in a metres-based CRS (e.g. EPSG:3035), so
    cell_size_m produces cells that are actually cell_size_m wide.
    """
    minx, miny, maxx, maxy = boundary.total_bounds
    # snap the grid to round multiples of cell_size_m, so re-running this
    # with the same cell size always produces the same cell edges
    minx = np.floor(minx / cell_size_m) * cell_size_m
    miny = np.floor(miny / cell_size_m) * cell_size_m

    cells = []
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            cells.append(box(x, y, x + cell_size_m, y + cell_size_m))
            y += cell_size_m
        x += cell_size_m

    grid = gpd.GeoDataFrame(geometry=cells, crs=boundary.crs)
    grid = grid[grid.intersects(boundary.union_all())].reset_index(drop=True)
    grid["cell_id"] = [f"cell_{i:05d}" for i in range(len(grid))]

    return grid


def select_pilot_block(
    grid: gpd.GeoDataFrame, boundary: gpd.GeoDataFrame, block_cells: int
) -> gpd.GeoDataFrame:
    """Pick the block_cells x block_cells block of grid cells with the highest
    mean cropland_fraction, among cells whose centre lies inside the oblast and
    in its south-west quadrant (west and south of the oblast centroid).

    grid must come from make_grid and carry a cropland_fraction column.
    """
    cell_size = grid.geometry.iloc[0].bounds[2] - grid.geometry.iloc[0].bounds[0]
    bounds = grid.geometry.bounds
    col = ((bounds["minx"] - bounds["minx"].min()) / cell_size).round().astype(int)
    row = ((bounds["miny"] - bounds["miny"].min()) / cell_size).round().astype(int)

    oblast = boundary.union_all()
    centre = oblast.centroid
    cell_centres = grid.geometry.centroid
    candidate = (
        (cell_centres.x < centre.x)
        & (cell_centres.y < centre.y)
        & cell_centres.within(oblast)
        & grid["cropland_fraction"].notna()
    )
    lookup = {(col[i], row[i]): i for i in grid.index[candidate]}

    best_score, best_members = -1.0, None
    for c, r in sorted(lookup):  # (c, r) = lower-left cell of a possible block
        members = [(c + dc, r + dr) for dc in range(block_cells) for dr in range(block_cells)]
        if not all(m in lookup for m in members):
            continue
        idx = [lookup[m] for m in members]
        score = grid.loc[idx, "cropland_fraction"].mean()
        if score > best_score:
            best_score, best_members = score, idx

    if best_members is None:
        raise ValueError(f"No complete {block_cells}x{block_cells} block of candidate cells found")

    return grid.loc[best_members]


def assign_cells_to_tiles(cells: gpd.GeoDataFrame, tiles: gpd.GeoDataFrame) -> pd.Series:
    """For each cell, the id of ONE tile that fully contains it: the tile whose
    centre is closest to the cell's centre. Cells no tile fully contains get a missing value (NaN).

    cells: needs cell_id; tiles: needs tile_id and the tile's data footprint.
    Both are compared in the cells' CRS (metres). Returns a Series indexed by cell_id.
    """
    tiles = tiles.to_crs(cells.crs)
    tile_centres = tiles.geometry.centroid
    out = {}
    for cell_id, geom in zip(cells["cell_id"], cells.geometry):
        containing = tiles.geometry.contains(geom)
        if not containing.any():
            out[cell_id] = None
            continue
        distances = tile_centres[containing].distance(geom.centroid)
        out[cell_id] = tiles.loc[distances.idxmin(), "tile_id"]
    return pd.Series(out, name="tile_id")
