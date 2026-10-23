"""Load project configuration from a YAML file (see configs/kharkiv_v1.yaml)."""

from pathlib import Path

import yaml

REQUIRED_SECTIONS = ["study_area", "crs", "grid", "time", "sentinel2", "paths"]


def load_config(path: str | Path) -> dict:
    """Read a config YAML file and return it as a dict.

    Raises ValueError if a required top-level section is missing, so a typo
    or an unfinished config fails loudly instead of causing a confusing
    error deep inside the pipeline.
    """
    path = Path(path)
    with path.open("r") as f:
        config = yaml.safe_load(f)

    missing = [section for section in REQUIRED_SECTIONS if section not in config]
    if missing:
        raise ValueError(f"Config {path} is missing required section(s): {missing}")

    return config
