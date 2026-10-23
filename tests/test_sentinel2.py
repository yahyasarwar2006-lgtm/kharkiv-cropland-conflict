from datetime import datetime, timezone

import numpy as np
import pytest
import xarray as xr

from agridisrupt.config import load_config
from agridisrupt.sentinel2 import apply_offset, check_offset_consistency, compute_ndvi, one_scene_per_date

CONFIG = load_config("configs/kharkiv_v1.yaml")


def test_compute_ndvi_known_values():
    red = xr.DataArray([100.0, 0.0, 500.0])
    nir = xr.DataArray([300.0, 0.0, 500.0])

    ndvi = compute_ndvi(red, nir)

    assert np.isclose(ndvi[0], 0.5)       # (300-100)/(300+100)
    assert np.isnan(ndvi[1])              # 0/0 -> NaN, not an error
    assert np.isclose(ndvi[2], 0.0)       # equal red/nir -> bare soil-like, NDVI 0


def test_compute_ndvi_stays_in_valid_range():
    rng = np.random.default_rng(0)
    red = xr.DataArray(rng.uniform(0, 3000, size=1000))
    nir = xr.DataArray(rng.uniform(0, 3000, size=1000))

    ndvi = compute_ndvi(red, nir)

    assert float(ndvi.min()) >= -1.0
    assert float(ndvi.max()) <= 1.0


def test_apply_offset_before_offset_date_is_unchanged():
    band = xr.DataArray([2000.0, 3000.0])
    date = datetime(2021, 6, 1, tzinfo=timezone.utc)

    corrected = apply_offset(band, date, CONFIG)

    assert np.allclose(corrected, band)


def test_apply_offset_on_and_after_offset_date_is_shifted():
    band = xr.DataArray([2000.0, 3000.0])
    offset = CONFIG["sentinel2"]["offset_value"]

    for date in [
        datetime(2022, 1, 25, tzinfo=timezone.utc),  # exact boundary
        datetime(2023, 7, 1, tzinfo=timezone.utc),
    ]:
        corrected = apply_offset(band, date, CONFIG)
        assert np.allclose(corrected, band - offset)


def test_offset_correction_prevents_fake_ndvi_jump():
    """The failure this correction exists for: identical ground reflectance
    on either side of 25 Jan 2022 must give the same NDVI once corrected, even
    though the raw (uncorrected) values differ by the offset.
    """
    true_red, true_nir = 400.0, 2400.0  # real reflectance values, same crop
    offset = CONFIG["sentinel2"]["offset_value"]

    red_before = xr.DataArray([true_red])
    nir_before = xr.DataArray([true_nir])
    ndvi_before = compute_ndvi(
        apply_offset(red_before, datetime(2021, 7, 1, tzinfo=timezone.utc), CONFIG),
        apply_offset(nir_before, datetime(2021, 7, 1, tzinfo=timezone.utc), CONFIG),
    )

    # same real reflectance, but as it would arrive raw from a post-baseline-04.00 scene
    red_after = xr.DataArray([true_red + offset])
    nir_after = xr.DataArray([true_nir + offset])
    ndvi_after = compute_ndvi(
        apply_offset(red_after, datetime(2023, 7, 1, tzinfo=timezone.utc), CONFIG),
        apply_offset(nir_after, datetime(2023, 7, 1, tzinfo=timezone.utc), CONFIG),
    )

    assert np.isclose(float(ndvi_before[0]), float(ndvi_after[0]))


class FakeItem:
    def __init__(self, day, baseline, tile="36UXA"):
        self.datetime = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
        self.properties = {"s2:processing_baseline": baseline, "s2:mgrs_tile": tile}


def test_one_scene_per_date_keeps_newest_baseline():
    items = [
        FakeItem("2022-05-01T08:00", "04.00"),
        FakeItem("2022-05-01T08:00", "05.10"),  # reprocessed copy of the same scene
        FakeItem("2022-05-06T08:00", "04.00"),
    ]
    kept = one_scene_per_date(items)
    assert [(i.datetime.day, i.properties["s2:processing_baseline"]) for i in kept] == [(1, "05.10"), (6, "04.00")]


def test_check_offset_consistency():
    check_offset_consistency(datetime(2021, 7, 1, tzinfo=timezone.utc), "03.00", CONFIG)  # fine
    check_offset_consistency(datetime(2022, 7, 1, tzinfo=timezone.utc), "05.10", CONFIG)  # fine
    with pytest.raises(ValueError):
        # a pre-2022 scene reprocessed with a new baseline would carry the offset
        check_offset_consistency(datetime(2021, 7, 1, tzinfo=timezone.utc), "05.00", CONFIG)
