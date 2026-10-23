from agridisrupt.climate import era5land_requests
from agridisrupt.config import load_config

CONFIG = load_config("configs/kharkiv_v1.yaml")


def test_era5land_requests_cover_all_years_and_last_day():
    reqs = {name: (dataset, req) for name, dataset, req in era5land_requests(CONFIG)}
    c = CONFIG["climate"]
    n_years = c["end_year"] - c["start_year"] + 1
    n_chunks = len(c["chunk_months"])
    # mean variables: one file per half-year; sum variables: one per year + 1 Jan of the next year
    expected = len(c["mean_variables"]) * n_years * n_chunks + len(c["sum_variables"]) * (n_years + 1)
    assert len(reqs) == expected
    # the chunks together cover every month exactly once
    assert sorted(m for chunk in c["chunk_months"] for m in chunk) == [f"{m:02d}" for m in range(1, 13)]

    _, t2m = reqs[f"era5land_2m_temperature_{c['start_year']}_01-06.nc"]
    assert len(t2m["time"]) == 24

    dataset, tp = reqs[f"era5land_total_precipitation_{c['end_year']}.nc"]
    assert dataset == c["dataset"]
    assert tp["time"] == ["00:00"]  # 00 UTC of day D+1 = total of day D
    assert f"era5land_total_precipitation_{c['end_year'] + 1}-01-01.nc" in reqs


def test_daily_precip_mm_shifts_to_previous_day(tmp_path):
    import numpy as np
    import pandas as pd
    import xarray as xr
    from agridisrupt.climate import daily_precip_mm

    times = pd.to_datetime(["2021-07-02", "2021-07-03"])  # 00 UTC values
    tp = xr.DataArray(np.array([[[0.004]], [[0.0]]]), dims=("valid_time", "latitude", "longitude"),
                      coords={"valid_time": times, "latitude": [49.7], "longitude": [35.4]}, name="tp")
    path = tmp_path / "tp.nc"
    tp.to_dataset().to_netcdf(path)

    daily = daily_precip_mm([path])
    # 4 mm read at 00 UTC on 2 July fell during 1 July
    assert daily.sel(date="2021-07-01").item() == 4.0
    assert daily.sel(date="2021-07-02").item() == 0.0


def test_values_at_cells_picks_nearest_point():
    import geopandas as gpd
    import numpy as np
    import xarray as xr
    from shapely.geometry import box
    from agridisrupt.climate import values_at_cells

    da = xr.DataArray(np.array([[1.0, 2.0], [3.0, 4.0]]), dims=("latitude", "longitude"),
                      coords={"latitude": [49.8, 49.7], "longitude": [35.4, 35.5]})
    # a small cell around 49.71 N, 35.49 E -> nearest point (49.7, 35.5) = 4.0
    cell = gpd.GeoDataFrame({"cell_id": ["c1"]}, geometry=[box(35.485, 49.705, 35.495, 49.715)], crs="EPSG:4326")
    out = values_at_cells(da, cell.to_crs("EPSG:3035"))
    assert out.sel(cell=0).item() == 4.0
    assert out["cell_id"].values[0] == "c1"


def test_daily_mean_needs_all_24_hours(tmp_path):
    import numpy as np
    import pandas as pd
    import xarray as xr
    from agridisrupt.climate import daily_mean

    times = pd.date_range("2021-07-01", periods=24 + 23, freq="h")  # day 1 complete, day 2 missing 1 h
    values = np.concatenate([np.arange(24.0), np.full(23, 5.0)]).reshape(-1, 1, 1)
    da = xr.DataArray(values, dims=("valid_time", "latitude", "longitude"),
                      coords={"valid_time": times, "latitude": [49.7], "longitude": [35.4]}, name="t2m")
    path = tmp_path / "t2m.nc"
    da.to_dataset().to_netcdf(path)

    daily = daily_mean([path])
    assert daily.sel(date="2021-07-01").item() == 11.5        # mean of 0..23
    assert np.isnan(daily.sel(date="2021-07-02").item())      # incomplete day -> no value


def test_period_features_sums_means_windows_and_anomaly():
    import numpy as np
    import pandas as pd
    import xarray as xr
    from agridisrupt.climate import period_features

    cfg = {**CONFIG, "climate": {**CONFIG["climate"], "precip_windows_days": [30],
                                 "anomaly_baseline_years": [2020, 2021]}}
    dates = pd.date_range("2020-01-01", "2021-12-31", freq="D")
    def daily(values):
        return xr.DataArray(np.asarray(values, dtype=float).reshape(-1, 1), dims=("date", "cell"),
                            coords={"date": dates, "cell_id": ("cell", ["c1"])})
    t2m = daily(np.where(dates.year == 2020, 10.0, 12.0))   # 2021 is 2 degrees warmer
    swvl = daily(np.full(len(dates), 0.3))
    rain = daily(np.full(len(dates), 1.0))                   # 1 mm every day

    df = period_features(t2m, swvl, rain, years=[2021], config=cfg)
    first = df[(df.period == 0)].iloc[0]                     # 1-14 Apr 2021
    assert set(df["year"]) == {2021} and len(df) == 15
    assert first["precip_sum"] == 14 and first["precip_30d"] == 30
    assert first["t2m_mean"] == 12 and np.isclose(first["swvl1_mean"], 0.3)
    assert first["t2m_anom"] == 1.0                          # normal = mean(10, 12) = 11
    assert df[df.period == 14].iloc[0]["precip_sum"] == 18   # last period: 14-31 Oct
