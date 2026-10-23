import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from agridisrupt.aoi import load_kharkiv_boundary, make_grid, select_pilot_block
from agridisrupt.config import load_config

CONFIG = load_config("configs/kharkiv_v1.yaml")


def test_load_kharkiv_boundary_shape():
    boundary = load_kharkiv_boundary(CONFIG)
    assert len(boundary) == 1
    assert boundary.crs.to_string() == CONFIG["crs"]["grid"]


def test_load_kharkiv_boundary_area_is_plausible():
    boundary = load_kharkiv_boundary(CONFIG)
    area_km2 = boundary.geometry.area.iloc[0] / 1e6
    # Kharkiv oblast is about 31,000 km²; allow generous slack for a
    # simplified boundary geometry.
    assert 25_000 < area_km2 < 37_000


def test_make_grid_cell_size_and_ids():
    boundary = load_kharkiv_boundary(CONFIG)
    cell_size_m = CONFIG["grid"]["cell_size_m"]
    grid = make_grid(boundary, cell_size_m)

    # every cell is a full cell_size_m x cell_size_m square
    assert (grid.geometry.area == cell_size_m**2).all()
    # cell_id is unique
    assert grid["cell_id"].is_unique
    # every cell actually touches the oblast
    assert grid.intersects(boundary.union_all()).all()


def test_make_grid_cell_count_is_plausible():
    boundary = load_kharkiv_boundary(CONFIG)
    cell_size_m = CONFIG["grid"]["cell_size_m"]
    grid = make_grid(boundary, cell_size_m)

    oblast_area_km2 = boundary.geometry.area.iloc[0] / 1e6
    cell_area_km2 = (cell_size_m / 1000) ** 2
    min_cells = oblast_area_km2 / cell_area_km2  # if grid were a perfect fit
    # bounding-box tiling always covers somewhat more than the oblast itself
    assert min_cells < len(grid) < min_cells * 1.6


def test_select_pilot_block_picks_best_southwest_block():
    # 40 x 40 km square "oblast" -> 8 x 8 grid of 5 km cells, centre at (20 km, 20 km)
    boundary = gpd.GeoDataFrame(geometry=[box(0, 0, 40_000, 40_000)], crs="EPSG:3035")
    grid = make_grid(boundary, 5000)
    minx, miny = grid.geometry.bounds["minx"], grid.geometry.bounds["miny"]
    col, row = (minx // 5000).astype(int), (miny // 5000).astype(int)

    grid["cropland_fraction"] = 0.1
    target = (col.isin([2, 3])) & (row.isin([1, 2]))       # 2x2 block inside the SW quadrant
    grid.loc[target, "cropland_fraction"] = 0.9
    grid.loc[col.isin([5, 6]) & row.isin([5, 6]), "cropland_fraction"] = 1.0  # NE: must be ignored
    grid.loc[col.isin([3, 4]) & row.isin([0]), "cropland_fraction"] = 0.95    # straddles quadrant edge

    block = select_pilot_block(grid, boundary, block_cells=2)

    assert sorted(block["cell_id"]) == sorted(grid.loc[target, "cell_id"])


def test_assign_cells_to_tiles_prefers_containing_and_closest_tile():
    from agridisrupt.aoi import assign_cells_to_tiles

    # two overlapping 100 km "tiles": A covers x 0-100 km, B covers x 80-180 km
    tiles = gpd.GeoDataFrame({"tile_id": ["A", "B"]},
                             geometry=[box(0, 0, 100_000, 100_000), box(80_000, 0, 180_000, 100_000)],
                             crs="EPSG:3035")
    cells = gpd.GeoDataFrame({"cell_id": ["west", "overlap_near_A", "overlap_near_B", "straddles_edge", "outside"]},
                             geometry=[box(10_000, 0, 15_000, 5_000),       # only in A
                                       box(80_000, 0, 85_000, 5_000),       # in both, closer to A's centre (50 km)
                                       box(95_000, 0, 100_000, 5_000),      # in both, closer to B's centre (130 km)
                                       box(178_000, 0, 183_000, 5_000),     # sticks out of B
                                       box(300_000, 0, 305_000, 5_000)],
                             crs="EPSG:3035")
    result = assign_cells_to_tiles(cells, tiles)
    assert result["west"] == "A"
    assert result["overlap_near_A"] == "A"
    assert result["overlap_near_B"] == "B"
    assert pd.isna(result["straddles_edge"])   # never read a cell from a tile that only partly covers it
    assert pd.isna(result["outside"])
