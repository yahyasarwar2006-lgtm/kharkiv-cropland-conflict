import pytest

from agridisrupt.config import load_config

CONFIG_PATH = "configs/kharkiv_v1.yaml"


def test_load_config_has_required_sections():
    config = load_config(CONFIG_PATH)
    for section in ["study_area", "crs", "grid", "time", "sentinel2", "paths"]:
        assert section in config


def test_load_config_values():
    config = load_config(CONFIG_PATH)
    assert config["grid"]["cell_size_m"] == 5000
    assert config["crs"]["grid"] == "EPSG:3035"
    assert config["time"]["start_year"] == 2018


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config("configs/does_not_exist.yaml")
