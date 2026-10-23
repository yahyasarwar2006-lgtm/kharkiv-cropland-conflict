"""Compute WorldCereal cropland share for every 5 km cell, then pick the
Experiment 1 pilot block using the rule in configs/kharkiv_v1.yaml (pilot:).

Run after scripts/download_boundary.py and scripts/download_worldcereal.py:
    python scripts/select_pilot_block.py
"""

import time
from pathlib import Path

import matplotlib.pyplot as plt

from agridisrupt.aoi import load_kharkiv_boundary, make_grid, select_pilot_block
from agridisrupt.config import load_config
from agridisrupt.conflict import count_events_near, load_ucdp_events
from agridisrupt.cropland import cropland_fraction


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    raw_dir = Path(config["paths"]["data_raw"]) / "worldcereal"
    interim_dir = Path(config["paths"]["data_interim"])
    tiles = [raw_dir / f"{a}_temporarycrops_classification.tif" for a in config["cropland"]["aez_ids"]]

    boundary = load_kharkiv_boundary(config)
    grid = make_grid(boundary, config["grid"]["cell_size_m"])

    start = time.time()
    fractions = cropland_fraction(grid, tiles)
    print(f"Cropland share computed for {len(grid)} cells in {time.time() - start:.0f} s")
    grid = grid.merge(fractions, on="cell_id")

    # sanity check: expected valid pixels per cell if the whole cell is covered.
    # WorldCereal pixels are 1/12000 degree; area shrinks with cos(latitude).
    median_valid = grid["valid_pixels"].median()
    print(f"Median valid pixels per cell: {median_valid:,.0f}")
    print(grid["cropland_fraction"].describe().round(3).to_string())
    min_frac = config["grid"]["min_cropland_fraction"]
    print(f"Cells with >= {min_frac:.0%} cropland: {(grid['cropland_fraction'] >= min_frac).sum()} of {len(grid)}")

    grid.to_file(interim_dir / "kharkiv_grid_5km_cropland.gpkg", driver="GPKG")

    n = config["pilot"]["block_cells"]
    centre = boundary.union_all().centroid

    # Block A: the base rule. Block B: same rule, cell centres restricted to the
    # western half of the SW quadrant.
    block_a = select_pilot_block(grid, boundary, n)
    west_half_x = (boundary.total_bounds[0] + centre.x) / 2
    block_b = select_pilot_block(grid[grid.geometry.centroid.x < west_half_x], boundary, n)

    # Exposure check (rule fixed in config before counting)
    check = config["pilot"]["exposure_check"]
    events = load_ucdp_events(
        Path(config["paths"]["data_raw"]) / "ucdp" / "GEDEvent_v26_1.csv",
        config["study_area"]["country"], check["period"], check["max_where_prec"],
    )
    exact = events[events["where_prec"] == 1]
    buffer_m = check["buffer_km"] * 1000
    print(f"\nUCDP events in Ukraine {check['period'][0]}..{check['period'][1]}, "
          f"where_prec <= {check['max_where_prec']}: {len(events)}")

    results = {}
    for name, block in [("A", block_a), ("B", block_b)]:
        outline = block.union_all()
        n_events = count_events_near(events, outline, config["crs"]["grid"], buffer_m)
        n_exact = count_events_near(exact, outline, config["crs"]["grid"], buffer_m)
        lon_min, lat_min, lon_max, lat_max = block.to_crs("EPSG:4326").total_bounds
        results[name] = n_events
        print(f"Block {name}: cropland {block['cropland_fraction'].mean():.1%} "
              f"(cells {block['cropland_fraction'].min():.0%}-{block['cropland_fraction'].max():.0%}), "
              f"lon {lon_min:.2f}-{lon_max:.2f}, lat {lat_min:.2f}-{lat_max:.2f}; "
              f"events within {check['buffer_km']} km: {n_events} (exact location: {n_exact})")

    chosen = "B" if results["B"] < results["A"] else "A"
    block = block_b if chosen == "B" else block_a
    print(f"Chosen pilot block: {chosen}")
    block.to_file(interim_dir / "pilot_block.gpkg", driver="GPKG")
    block_outline = block.union_all()
    fig, ax = plt.subplots(figsize=(7, 7))
    grid.plot(ax=ax, column="cropland_fraction", cmap="YlGn", vmin=0, vmax=1,
              legend=True, legend_kwds={"label": "WorldCereal 2021 cropland share", "shrink": 0.7})
    boundary.boundary.plot(ax=ax, color="black", linewidth=1)
    ax.axvline(centre.x, color="grey", linestyle="--", linewidth=0.8)
    ax.axhline(centre.y, color="grey", linestyle="--", linewidth=0.8)
    for name, candidate in [("A", block_a), ("B", block_b)]:
        outline = candidate.union_all()
        is_chosen = name == chosen
        ax.plot(*outline.exterior.xy, color="#c0392b" if is_chosen else "#555555",
                linewidth=2.5 if is_chosen else 1.5, linestyle="-" if is_chosen else ":")
        ax.annotate(name, (outline.bounds[0], outline.bounds[3]), xytext=(-10, 2),
                    textcoords="offset points", fontsize=10, fontweight="bold")
    ax.set_title(f"Cropland share per 5 km cell; candidate pilot blocks A and B,\n"
                 f"chosen block {chosen} in red (dashed lines = south-west quadrant)")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    out_path = Path(config["paths"]["reports_figures"]) / "cropland_share_pilot_block.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
