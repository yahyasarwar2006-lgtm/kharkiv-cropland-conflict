"""Download ERA5-Land (2 m temperature, top-layer soil moisture, precipitation)
for the Kharkiv box, years set in configs/kharkiv_v1.yaml (climate:).

Needs: CDS key in ~/.cdsapirc and the ERA5-Land terms accepted on the CDS website.
Safe to stop and re-run: finished files are skipped.

Run: python scripts/download_era5land.py
"""

from pathlib import Path

from agridisrupt.climate import download_era5land
from agridisrupt.config import load_config


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    download_era5land(config, Path(config["paths"]["data_raw"]) / "era5land",
                      max_per_dataset=config["climate"]["max_queued_requests"])


if __name__ == "__main__":
    main()
