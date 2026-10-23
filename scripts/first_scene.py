"""Stage 1 sanity check: load one Sentinel-2 scene over Kharkiv, compute NDVI,
apply the SCL cloud mask, and plot it.

Run: python scripts/first_scene.py
"""

import matplotlib.pyplot as plt

from agridisrupt.aoi import load_kharkiv_boundary
from agridisrupt.config import load_config
from agridisrupt.sentinel2 import load_scene_ndvi, search_scenes

DATE_RANGE = "2021-06-01/2021-08-31"  # peak growing season, pre-war
HALF_BOX_KM = 10  # ~20 x 20 km box


def main():
    config = load_config("configs/kharkiv_v1.yaml")

    boundary = load_kharkiv_boundary(config)
    centroid = boundary.geometry.centroid.iloc[0]  # in EPSG:3035 (metres)
    half_m = HALF_BOX_KM * 1000
    box_3035 = (centroid.x - half_m, centroid.y - half_m, centroid.x + half_m, centroid.y + half_m)

    # STAC search and rioxarray clipping both expect WGS84 (lon/lat) boxes
    import geopandas as gpd
    from shapely.geometry import box as shapely_box

    box_gdf = gpd.GeoDataFrame(geometry=[shapely_box(*box_3035)], crs=config["crs"]["grid"])
    bbox_wgs84 = tuple(box_gdf.to_crs("EPSG:4326").total_bounds)

    print(f"Searching {DATE_RANGE} over bbox {bbox_wgs84} ...")
    items = search_scenes(config, bbox_wgs84, DATE_RANGE)
    print(f"Found {len(items)} scenes under {config['sentinel2']['max_cloud_cover']}% cloud cover")

    if not items:
        raise SystemExit("No scenes found — try a wider date range or higher cloud threshold.")

    item = items[0]
    print(f"Using scene {item.id}")
    print(f"  date: {item.datetime}")
    print(f"  cloud cover: {item.properties['eo:cloud_cover']:.1f}%")

    ndvi = load_scene_ndvi(item, bbox_wgs84, config)

    valid_frac = float(ndvi.notnull().mean())
    print(f"  valid (clear land) pixels: {valid_frac:.1%}")
    print(f"  NDVI range: {float(ndvi.min()):.2f} to {float(ndvi.max()):.2f}")

    fig, ax = plt.subplots(figsize=(6, 6))
    ndvi.plot(ax=ax, cmap="RdYlGn", vmin=-0.2, vmax=0.9, cbar_kwargs={"label": "NDVI"})
    ax.set_title(f"NDVI — {item.id}\n{str(item.datetime)[:10]}, cloud cover {item.properties['eo:cloud_cover']:.0f}%")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    out_path = "reports/figures/first_scene_ndvi.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
