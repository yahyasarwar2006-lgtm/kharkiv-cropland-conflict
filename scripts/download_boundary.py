"""Download the Ukraine ADM1 (oblast-level) boundary from geoBoundaries.

Run once, or whenever you want to refresh it:
    python scripts/download_boundary.py
"""

import json
import urllib.request
from pathlib import Path

from agridisrupt.config import load_config

API_URL = "https://www.geoboundaries.org/api/current/gbOpen/UKR/ADM1/"


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    raw_dir = Path(config["paths"]["data_raw"]) / "boundaries"
    raw_dir.mkdir(parents=True, exist_ok=True)

    with urllib.request.urlopen(API_URL) as response:
        meta = json.load(response)
    geojson_url = meta["simplifiedGeometryGeoJSON"]

    out_path = raw_dir / "ukraine_adm1.geojson"
    urllib.request.urlretrieve(geojson_url, out_path)
    print(f"Saved boundary to {out_path}")


if __name__ == "__main__":
    main()
