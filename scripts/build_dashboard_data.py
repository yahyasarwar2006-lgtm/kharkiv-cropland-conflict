"""Stage 10: small public summary files for the Streamlit dashboard (committed, unlike data/).
Only historical, 5 km, per-season aggregates (rule 6); exposure as a group label, never ACLED counts.

Run after scripts/run_recovery.py:
    python scripts/build_dashboard_data.py
Output (config dashboard.assets_dir): cells.geojson, cell_seasons.csv, cell_curves.csv, curves.csv
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd

from agridisrupt.config import load_config
from agridisrupt.conflict import exposure_history
from agridisrupt.features import season_part_means, season_parts


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    processed = Path(config["paths"]["data_processed"])
    out = Path(config["dashboard"]["assets_dir"])
    out.mkdir(parents=True, exist_ok=True)
    parts = season_parts(config)

    cells = gpd.read_file(Path(config["paths"]["data_interim"]) / "kharkiv_grid_5km_cropland.gpkg")
    cells = cells[cells["cropland_fraction"] >= config["grid"]["min_cropland_fraction"]]
    cells = cells[["cell_id", "cropland_fraction", "geometry"]].to_crs("EPSG:4326")
    cells["cropland_fraction"] = cells["cropland_fraction"].round(3)
    cells.to_file(out / "cells.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)

    adj = pd.read_csv(processed / "adjusted_anomalies.csv")
    base = pd.read_csv(processed / "baseline_anomalies.csv")
    seasons = season_part_means(adj, "adjusted_anomaly", parts).rename(columns={p: f"adj_{p}" for p in parts})
    seasons = seasons.merge(season_part_means(base, "anomaly", parts).rename(columns={p: f"raw_{p}" for p in parts}),
                            on=["cell_id", "year"], how="outer")
    shape = pd.read_csv(processed / "season_shape.csv")[["cell_id", "year", "peak_ndvi", "peak_period", "late_ndvi"]]
    exp = pd.read_csv(processed / "exposure.csv")
    history = exposure_history(exp, config["recovery"]["start_year"], config["recovery"]["later_years"],
                               config["exposure"]["high_min_events"])
    seasons = (seasons.merge(shape, on=["cell_id", "year"], how="left")
               .merge(exp[["cell_id", "year", "group"]].rename(columns={"group": "exposure"}), on=["cell_id", "year"]))
    seasons["history"] = seasons["cell_id"].map(history)
    seasons.round(3).to_csv(out / "cell_seasons.csv", index=False)

    curves = adj[["cell_id", "year", "period", "ndvi", "predicted"]].round(3)
    curves.to_csv(out / "cell_curves.csv", index=False)

    panel = pd.read_csv(processed / "panel.csv", usecols=["cell_id", "year", "period", "period_start", "ndvi"])
    g22 = exp[exp["year"] == 2022].set_index("cell_id")["group"]
    panel["group_2022"] = panel["cell_id"].map(g22)
    med = panel.groupby(["year", "period"]).agg(start=("period_start", "first"), all_cells=("ndvi", "median"))
    for grp in ["high", "low"]:
        med[f"{grp}_2022"] = panel[panel["group_2022"] == grp].groupby(["year", "period"])["ndvi"].median()
    med["start"] = med["start"].str[5:]
    med.round(3).reset_index().to_csv(out / "curves.csv", index=False)

    for f in sorted(out.iterdir()):
        print(f"{f}: {f.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
