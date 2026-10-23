import pandas as pd
import pytest

from agridisrupt.panel import COLUMNS, build_panel, load_composites


def _ndvi(cells=("c1", "c2")):
    return pd.DataFrame({
        "tile": "36UXA", "year": 2021, "period": 0, "period_start": "2021-04-01",
        "period_end": "2021-04-14", "n_scenes": 4, "n_skipped": 0, "cell_id": list(cells),
        "crop_pixels": 100, "valid_share": 1.0, "ndvi_median": [0.2, 0.3][:len(cells)],
    })


def _climate(cells=("c1", "c2")):
    return pd.DataFrame({
        "cell_id": list(cells), "year": 2021, "period": 0, "t2m_mean": 10.0, "swvl1_mean": 0.3,
        "precip_sum": 5.0, "precip_30d": 20.0, "precip_60d": 40.0, "t2m_anom": 0.5,
    })


def test_build_panel_keeps_every_row_and_renames_ndvi():
    panel = build_panel(_ndvi(), _climate(), min_valid_share=0.5)
    assert list(panel.columns) == COLUMNS
    assert len(panel) == 2
    assert panel.set_index("cell_id")["ndvi"].to_dict() == {"c1": 0.2, "c2": 0.3}


def test_build_panel_empties_ndvi_below_min_valid_share():
    ndvi = _ndvi()
    ndvi["valid_share"] = [0.49, 0.5]
    panel = build_panel(ndvi, _climate(), min_valid_share=0.5).set_index("cell_id")
    assert pd.isna(panel.loc["c1", "ndvi"]) and panel.loc["c1", "ndvi_raw"] == 0.2
    assert panel.loc["c2", "ndvi"] == 0.3   # exactly at the limit is kept


def test_build_panel_rejects_duplicate_key():
    ndvi = pd.concat([_ndvi(), _ndvi(("c1",))], ignore_index=True)
    with pytest.raises(pd.errors.MergeError):
        build_panel(ndvi, _climate(), min_valid_share=0.5)


def test_build_panel_rejects_key_missing_from_one_table():
    with pytest.raises(ValueError, match="keys do not match"):
        build_panel(_ndvi(), _climate(("c1",)), min_valid_share=0.5)


def test_load_composites_stacks_files(tmp_path):
    _ndvi(("c1",)).to_csv(tmp_path / "composites_2021_36UXA.csv", index=False)
    _ndvi(("c2",)).to_csv(tmp_path / "composites_2021_36UYA.csv", index=False)
    (tmp_path / "scenes_2021_36UXA.csv").write_text("not a composite")
    assert sorted(load_composites(tmp_path)["cell_id"]) == ["c1", "c2"]
