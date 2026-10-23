"""Turn the downloaded ERA5-Land files into one climate table per 5 km cell and
14-day period (the same periods as the NDVI composites).

Run after scripts/download_era5land.py has fetched every file:
    python scripts/build_climate_table.py
Output: data/processed/climate_features.csv
"""

from pathlib import Path

import geopandas as gpd

from agridisrupt.climate import daily_mean, daily_precip_mm, period_features, values_at_cells
from agridisrupt.config import load_config


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    raw = Path(config["paths"]["data_raw"]) / "era5land"
    cells = gpd.read_file(Path(config["paths"]["data_interim"]) / "kharkiv_grid_5km_cropland.gpkg")
    keep = cells["cropland_fraction"] >= config["grid"]["min_cropland_fraction"]
    cells = cells[keep].reset_index(drop=True)
    print(f"{len(cells)} cells with >= {config['grid']['min_cropland_fraction']:.0%} cropland")

    t2m = values_at_cells(daily_mean(raw.glob("era5land_2m_temperature_*.nc")), cells) - 273.15
    swvl1 = values_at_cells(daily_mean(raw.glob("era5land_volumetric_soil_water_layer_1_*.nc")), cells)
    rain = values_at_cells(daily_precip_mm(raw.glob("era5land_total_precipitation_*.nc")), cells)

    for name, da in [("temperature", t2m), ("soil moisture", swvl1), ("rain", rain)]:
        days = da["date"].values
        n_missing = int(da.isnull().sum())
        print(f"{name}: {str(days[0])[:10]} to {str(days[-1])[:10]}, {da.sizes['date']} days, {n_missing} missing values")

    t = config["time"]
    years = list(range(t["start_year"], t["end_year"] + 1))
    features = period_features(t2m, swvl1, rain, years, config)

    out = Path(config["paths"]["data_processed"]) / "climate_features.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    features.round(4).to_csv(out, index=False)
    print(f"\nSaved {out}: {len(features)} rows ({features['cell_id'].nunique()} cells x "
          f"{len(years)} years x {features['period'].nunique()} periods)")
    print(features.drop(columns=["cell_id", "year", "period"]).describe().round(3).to_string())


if __name__ == "__main__":
    main()
