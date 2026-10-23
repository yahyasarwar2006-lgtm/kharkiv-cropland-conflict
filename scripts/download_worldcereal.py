"""Download the ESA WorldCereal 2021 temporary-crops tiles covering Kharkiv.

WorldCereal is published on Zenodo as one 15.5 GB global zip. Instead of
downloading all of it, GDAL copies only the zip members we need (one GeoTIFF
per agro-ecological zone, ~1 GB each) using HTTP range requests. Zenodo
rate-limits (HTTP 429), so GDAL is told to retry with a delay.

Run: python scripts/download_worldcereal.py   (needs the `gdal` CLI from the agri env)
"""

import os
import subprocess
from pathlib import Path

from agridisrupt.config import load_config

ZIP_URL = (
    "https://zenodo.org/records/7875105/files/"
    "WorldCereal_2021_tc-annual_temporarycrops_classification.zip"
)
MEMBER_DIR = "data/worldcereal_data/MAP-v3/2021/tc-annual/temporarycrops/aez/classification"
# season dates differ per zone and are part of each file name inside the zip
MEMBER_DATES = {
    22096: "2020-10-20_2021-10-20",
    22190: "2020-11-01_2021-11-01",
    22194: "2020-10-17_2021-10-17",
}

GDAL_RETRY_ENV = {
    "GDAL_HTTP_MAX_RETRY": "20",
    "GDAL_HTTP_RETRY_DELAY": "30",
    "GDAL_HTTP_RETRY_CODES": "429,500,502,503,504",
    "CPL_VSIL_CURL_CHUNK_SIZE": "10485760",  # 10 MB requests -> fewer of them
}


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    out_dir = Path(config["paths"]["data_raw"]) / "worldcereal"
    out_dir.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, **GDAL_RETRY_ENV}

    for aez_id in config["cropland"]["aez_ids"]:
        out_path = out_dir / f"{aez_id}_temporarycrops_classification.tif"
        if out_path.exists():
            print(f"{out_path} already exists, skipping")
            continue

        member = f"{MEMBER_DIR}/{aez_id}_tc-annual_temporarycrops_{MEMBER_DATES[aez_id]}_classification.tif"
        part_path = out_path.with_suffix(".tif.part")
        print(f"Copying AEZ {aez_id} ...")
        subprocess.run(
            ["gdal", "vsi", "copy", f"/vsizip//vsicurl/{ZIP_URL}/{member}", str(part_path)],
            env=env,
            check=True,
        )
        part_path.rename(out_path)
        print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
