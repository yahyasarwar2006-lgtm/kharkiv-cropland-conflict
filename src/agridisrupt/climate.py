"""ERA5-Land climate data: download from the Copernicus CDS."""

import json
import time
from pathlib import Path

ALL_MONTHS = [f"{m:02d}" for m in range(1, 13)]
ALL_DAYS = [f"{d:02d}" for d in range(1, 32)]  # CDS ignores days that don't exist


def era5land_requests(config: dict) -> list:
    """List of (file name, CDS dataset, CDS request).

    Mean variables: all 24 hourly values, one request per variable per half-year
    (a full year is over the CDS size limit); daily means are computed locally.
    Sum variables (accumulated since 00 UTC): 00:00 only, one request per year,
    because the 00 UTC value of day D+1 is the total of day D. One extra request
    fetches 1 January of the year after end_year, to complete the last day.
    """
    c = config["climate"]
    base = {"area": c["area"], "data_format": "netcdf", "download_format": "unarchived"}
    years = range(c["start_year"], c["end_year"] + 1)
    hours = [f"{h:02d}:00" for h in range(24)]
    out = []
    for var in c["mean_variables"]:
        for year in years:
            for months in c["chunk_months"]:
                out.append((f"era5land_{var}_{year}_{months[0]}-{months[-1]}.nc", c["dataset"], {
                    **base, "variable": [var], "year": str(year),
                    "month": months, "day": ALL_DAYS, "time": hours,
                }))
    for var in c["sum_variables"]:
        for year in years:
            out.append((f"era5land_{var}_{year}.nc", c["dataset"], {
                **base, "variable": [var], "year": str(year),
                "month": ALL_MONTHS, "day": ALL_DAYS, "time": ["00:00"],
            }))
        out.append((f"era5land_{var}_{c['end_year'] + 1}-01-01.nc", c["dataset"], {
            **base, "variable": [var], "year": str(c["end_year"] + 1),
            "month": ["01"], "day": ["01"], "time": ["00:00"],
        }))
    return out


def _cds_client():
    """CDS client using the key in ~/.cdsapirc (the same file cdsapi uses)."""
    from ecmwf.datastores import Client  # imported here so the rest of the module works without it

    settings = dict(line.split(":", 1) for line in (Path.home() / ".cdsapirc").read_text().strip().splitlines())
    # The default is up to 500 retries, 120 s apart (~16 h) after a dropped connection;
    # one such drop once stalled the download for over an hour. Fail sooner instead:
    # the request ids in cds_jobs.json make a re-run resume where it stopped.
    return Client(url=settings["url"].strip(), key=settings["key"].strip(),
                  maximum_tries=10, retry_after=30)


def download_era5land(
    config: dict, out_dir: Path, poll_seconds: int = 60, max_per_dataset: int = 1, retry_wait: int = 300
) -> None:
    """Download every request from era5land_requests that isn't on disk yet.

    The CDS limits how many requests one user may have queued per dataset (sending
    all 31 at once got almost all rejected), so at most max_per_dataset requests per
    dataset are in the queue at a time; the daily-statistics and hourly datasets run
    side by side. A rejected request is retried after retry_wait seconds. Request ids
    are kept in cds_jobs.json, so stopping and re-running never re-queues a request.
    Needs a CDS key in ~/.cdsapirc and the dataset's terms accepted once on the website.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    client = _cds_client()
    jobs_file = out_dir / "cds_jobs.json"
    jobs = json.loads(jobs_file.read_text()) if jobs_file.exists() else {}
    todo = {name: (dataset, request) for name, dataset, request in era5land_requests(config)
            if not (out_dir / name).exists()}
    jobs = {name: job_id for name, job_id in jobs.items() if name in todo}
    not_before = {}  # dataset -> earliest time to submit again after a rejection
    print(f"{len(todo)} files to fetch, {len(jobs)} already in the CDS queue", flush=True)

    while todo:
        for name in list(todo):  # check queued requests
            if name not in jobs:
                continue
            remote = client.get_remote(jobs[name])
            state = remote.status
            if state == "successful":
                path = out_dir / name
                part = path.with_suffix(".nc.part")
                try:
                    remote.download(str(part))
                except Exception as err:
                    if "expired" not in str(err):
                        raise
                    # CDS deletes finished results after a few days (seen on 6 Oct 2026
                    # for requests finished ~4 days earlier): request the file again
                    print(f"result for {name} has expired on the CDS, requesting it again", flush=True)
                    del jobs[name]
                    continue
                part.rename(path)
                del todo[name], jobs[name]
                print(f"saved {name} ({path.stat().st_size / 1e6:.1f} MB) - {len(todo)} to go", flush=True)
            elif state in ("failed", "rejected", "dismissed", "deleted"):
                print(f"request for {name} ended as '{state}', retrying in {retry_wait // 60} min", flush=True)
                del jobs[name]
                not_before[todo[name][0]] = time.time() + retry_wait

        for name, (dataset, request) in todo.items():  # top up each dataset's queue slot
            in_queue = sum(1 for n in jobs if todo[n][0] == dataset)
            if name in jobs or in_queue >= max_per_dataset or time.time() < not_before.get(dataset, 0):
                continue
            try:
                jobs[name] = client.submit(dataset, request).request_id
                print(f"submitted {name}", flush=True)
            except Exception as err:
                print(f"could not submit {name}: {err}", flush=True)
                not_before[dataset] = time.time() + retry_wait
        jobs_file.write_text(json.dumps(jobs, indent=1))

        if todo:
            time.sleep(poll_seconds)
    print("all ERA5-Land files downloaded", flush=True)


def daily_precip_mm(paths) -> "xr.DataArray":
    """Daily precipitation totals in mm per ERA5-Land grid point.

    The files hold the 00 UTC value of every day, which is the total of the PREVIOUS
    day (accumulation runs from 00 UTC), so each time stamp is shifted back one day.
    """
    import numpy as np
    import xarray as xr

    tp = xr.concat([xr.open_dataset(p)["tp"].load() for p in sorted(paths)], dim="valid_time")
    tp = tp.sortby("valid_time")
    tp = tp.assign_coords(valid_time=tp["valid_time"] - np.timedelta64(1, "D")).rename(valid_time="date")
    tp = tp.drop_vars([v for v in ("expver", "number") if v in tp.coords])
    return (tp * 1000).rename("precip_mm")


def values_at_cells(da, cells) -> "xr.DataArray":
    """Value of the nearest ERA5-Land grid point (0.1 deg, ~11 x 7 km here) for each
    grid cell's centre. Result has a 'cell' dimension labelled with cell_id."""
    import xarray as xr

    centres = cells.geometry.centroid.to_crs("EPSG:4326")
    picked = da.sel(
        latitude=xr.DataArray(centres.y.values, dims="cell"),
        longitude=xr.DataArray(centres.x.values, dims="cell"),
        method="nearest",
    )
    # plain numpy strings: xarray cannot label with pandas' Arrow-backed string arrays
    return picked.assign_coords(cell_id=("cell", cells["cell_id"].to_numpy(dtype=str)))


def daily_mean(paths) -> "xr.DataArray":
    """Daily (UTC) mean per ERA5-Land grid point from hourly files of ONE variable.
    A day only gets a value if all 24 hourly values are present."""
    import xarray as xr

    # Daily means are computed file by file (each file holds whole UTC days), so only
    # one half-year of hourly data is in memory at a time instead of ten years.
    days = []
    for p in sorted(paths):
        ds = xr.open_dataset(p)
        (name,) = list(ds.data_vars)  # each file holds a single variable
        hourly = ds[name].load()
        hourly = hourly.drop_vars([v for v in ("expver", "number") if v in hourly.coords])
        resampled = hourly.resample(valid_time="1D")
        days.append(resampled.mean().where(resampled.count() == 24))
        ds.close()
    daily = xr.concat(days, dim="valid_time").sortby("valid_time")
    return daily.rename(valid_time="date")


def period_features(t2m_c, swvl1, precip_mm, years, config: dict) -> "pd.DataFrame":
    """Climate features per cell and 14-day period (same periods as the NDVI composites).

    Inputs are daily DataArrays with dims (date, cell) and a cell_id coordinate:
    temperature in deg C, soil moisture in m3/m3, precipitation in mm.
    Output columns: cell_id, year, period, t2m_mean, swvl1_mean, precip_sum,
    precip_<N>d (rain in the N days up to the period's last day) and t2m_anom
    (t2m_mean minus that cell's mean for the same period over the baseline years).
    """
    import pandas as pd

    from agridisrupt.composites import n_periods, period_dates

    c = config["climate"]
    rolling = {n: precip_mm.rolling(date=n).sum() for n in c["precip_windows_days"]}
    base_from, base_to = c["anomaly_baseline_years"]
    rows = []
    for year in sorted(set(years) | set(range(base_from, base_to + 1))):
        for p in range(n_periods(year, config)):
            first, last = period_dates(year, p, config)
            window = slice(first, last)
            part = pd.DataFrame({
                "cell_id": t2m_c["cell_id"].values,
                "year": year,
                "period": p,
                "t2m_mean": t2m_c.sel(date=window).mean("date").values,
                "swvl1_mean": swvl1.sel(date=window).mean("date").values,
                "precip_sum": precip_mm.sel(date=window).sum("date", min_count=1).values,
            })
            for n, r in rolling.items():
                part[f"precip_{n}d"] = r.sel(date=last).values
            rows.append(part)
    df = pd.concat(rows, ignore_index=True)

    baseline = df[df["year"].between(base_from, base_to)]
    normal = baseline.groupby(["cell_id", "period"])["t2m_mean"].mean().rename("t2m_normal")
    df = df.join(normal, on=["cell_id", "period"])
    df["t2m_anom"] = df["t2m_mean"] - df.pop("t2m_normal")
    return df[df["year"].isin(list(years))].reset_index(drop=True)
