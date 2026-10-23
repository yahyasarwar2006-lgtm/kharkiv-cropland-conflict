"""Join the whole-oblast NDVI composites and the climate features into one panel
(one row per cell x year x 14-day period).

Run after scripts/run_oblast_timeseries.py and scripts/build_climate_table.py:
    python scripts/build_panel.py
Output: data/processed/panel.csv (+ panel.xlsx, a copy for viewing in Excel)
"""

from pathlib import Path

import pandas as pd

from agridisrupt.config import load_config
from agridisrupt.panel import KEY, build_panel, load_composites


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    processed = Path(config["paths"]["data_processed"])
    ndvi = load_composites(Path(config["paths"]["data_interim"]) / "oblast")
    climate = pd.read_csv(processed / "climate_features.csv")
    print(f"NDVI composites: {len(ndvi)} rows | climate features: {len(climate)} rows")

    min_valid = config["panel"]["min_valid_share"]
    panel = build_panel(ndvi, climate, min_valid)

    out = processed / "panel.csv"
    panel.to_csv(out, index=False)
    # Viewing copy for Excel: with Dutch region settings Excel expects ';' and decimal commas,
    # so it shows the CSV as one column. Code always reads the CSV, never this file.
    with pd.ExcelWriter(processed / "panel.xlsx") as xl:
        panel.to_excel(xl, index=False, sheet_name="panel", freeze_panes=(1, 0))
    print(f"\nSaved {out}: {len(panel)} rows ({panel['cell_id'].nunique()} cells x "
          f"{panel['year'].nunique()} years x {panel['period'].nunique()} periods), "
          f"{len(panel.columns)} columns")
    print(f"empty ndvi_raw (no clear image in the period): {panel['ndvi_raw'].isna().mean():.1%}")
    print(f"empty ndvi (also < {min_valid:.0%} of cropland clear): {panel['ndvi'].isna().mean():.1%}")
    n_missing = int(panel.drop(columns=["ndvi_raw", "ndvi"]).isna().sum().sum())
    print(f"missing values in other columns: {n_missing}")
    print(panel.drop(columns=KEY).describe().round(3).to_string())


if __name__ == "__main__":
    main()
