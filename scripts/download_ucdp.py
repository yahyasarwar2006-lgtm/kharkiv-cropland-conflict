"""Download UCDP GED 26.1 (global georeferenced event dataset, 1989-2025, CC BY 4.0)
and its codebook. No account needed.

Run: python scripts/download_ucdp.py
"""

import urllib.request
import zipfile
from pathlib import Path

from agridisrupt.config import load_config

FILES = {
    "ged261-csv.zip": "https://ucdp.uu.se/downloads/ged/ged261-csv.zip",
    "ged261_codebook.pdf": "https://ucdp.uu.se/downloads/ged/ged261.pdf",
}


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    out_dir = Path(config["paths"]["data_raw"]) / "ucdp"
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, url in FILES.items():
        out_path = out_dir / name
        if out_path.exists():
            print(f"{out_path} already exists, skipping")
            continue
        urllib.request.urlretrieve(url, out_path)
        print(f"Saved {out_path}")

    with zipfile.ZipFile(out_dir / "ged261-csv.zip") as z:
        z.extractall(out_dir)
        print("Extracted:", z.namelist())


if __name__ == "__main__":
    main()
