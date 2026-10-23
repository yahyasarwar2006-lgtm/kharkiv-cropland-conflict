import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from agridisrupt.cropland import cropland_fraction


def make_tile(path):
    """20 x 10 pixels of 100 m: left half all crop; right half 5 crop columns,
    5 'other' columns, with the top row of the 'other' part set to no-data."""
    data = np.full((10, 20), 100, dtype=np.uint8)
    data[:, 15:] = 0
    data[0, 15:] = 255
    with rasterio.open(
        path, "w", driver="GTiff", width=20, height=10, count=1, dtype="uint8",
        crs="EPSG:3035", transform=from_origin(0, 1000, 100, 100), nodata=255,
    ) as dst:
        dst.write(data, 1)


def test_cropland_fraction_known_values(tmp_path):
    tile = tmp_path / "tile.tif"
    make_tile(tile)
    grid = gpd.GeoDataFrame(
        {"cell_id": ["left", "right", "outside"]},
        geometry=[box(0, 0, 1000, 1000), box(1000, 0, 2000, 1000), box(5000, 0, 6000, 1000)],
        crs="EPSG:3035",
    )

    result = cropland_fraction(grid, [tile]).set_index("cell_id")

    assert result.loc["left", "crop_pixels"] == 100
    assert result.loc["left", "cropland_fraction"] == 1.0
    # right cell: 50 crop pixels, 100 pixels minus 5 no-data = 95 valid
    assert result.loc["right", "crop_pixels"] == 50
    assert result.loc["right", "valid_pixels"] == 95
    assert np.isclose(result.loc["right", "cropland_fraction"], 50 / 95)
    # a cell the tile doesn't cover has no valid pixels -> NaN, not 0
    assert np.isnan(result.loc["outside", "cropland_fraction"])
