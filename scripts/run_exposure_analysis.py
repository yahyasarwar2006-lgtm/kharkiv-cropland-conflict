"""Stage 7 (RQ2): conflict exposure per cell and season, and its association with the
weather-adjusted NDVI anomalies. Follows the plan written BEFORE any result (experiments.md,
Experiment 5; config `exposure:`). Wording: "associated with", never "caused by".

Run after scripts/evaluate_models.py and scripts/run_baseline.py:
    python scripts/run_exposure_analysis.py
Output: data/processed/exposure.csv, reports/exposure_results.csv,
        reports/figures/exposure_groups_map.png, reports/figures/exposure_event_study.png
"""

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from agridisrupt.analysis import bootstrap_diff, bootstrap_mean, morans_i, spatial_blocks, twfe
from agridisrupt.config import load_config
from agridisrupt.conflict import exposure_group, load_acled_events, load_ucdp_events, season_exposure
from agridisrupt.features import season_part_means, season_parts

POST = [2022, 2023, 2024]


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    e, a = config["exposure"], config["analysis"]
    raw, processed = Path(config["paths"]["data_raw"]), Path(config["paths"]["data_processed"])
    figs = Path(config["paths"]["reports_figures"])
    years = list(range(config["time"]["start_year"], config["time"]["end_year"] + 1))
    first, last = a["baseline_years"]

    cells = gpd.read_file(Path(config["paths"]["data_interim"]) / "kharkiv_grid_5km_cropland.gpkg")
    cells = cells[cells["cropland_fraction"] >= config["grid"]["min_cropland_fraction"]].reset_index(drop=True)
    lon0, lat0, lon1, lat1 = cells.to_crs("EPSG:4326").total_bounds
    bounds = (lon0 - 0.2, lat0 - 0.2, lon1 + 0.2, lat1 + 0.2)

    # Exposure per cell and season: ACLED (main) and UCDP (cross-check)
    acled = load_acled_events(next(raw.glob(e["source_glob"])), e["event_types"], e["max_geo_precision"], bounds)
    ucdp = load_ucdp_events(raw / "ucdp" / "GEDEvent_v26_1.csv", "Ukraine",
                            (f"{years[0]}-01-01", f"{years[-1]}-12-31"), max_where_prec=2)
    ucdp = ucdp.rename(columns={"date_start": "date"})
    buf = e["buffer_km"] * 1000
    exp = season_exposure(acled, cells, buf, years, a["war_start"], e["season_end"])
    exp_u = season_exposure(ucdp, cells, buf, years, a["war_start"], e["season_end"])
    exp = exp.merge(exp_u.rename(columns={"events": "events_ucdp"}), on=["cell_id", "year"])
    exp["group"] = exposure_group(exp["events"], e["low_max_events"], e["high_min_events"])
    exp["group_ucdp"] = exposure_group(exp["events_ucdp"], e["low_max_events"], e["high_min_events"])
    exp.to_csv(processed / "exposure.csv", index=False)
    print(f"ACLED events used: {len(acled)}; UCDP events: {len(ucdp)}. Saved {processed / 'exposure.csv'}")
    print("\nCells per exposure group and season (ACLED):")
    print(exp.pivot_table(index="year", columns="group", values="cell_id", aggfunc="count").fillna(0)
          .astype(int).to_string())

    # Outcomes per cell and season: weather-adjusted part means + late-season shape anomaly
    parts = season_parts(config)
    adj = pd.read_csv(processed / "adjusted_anomalies.csv")
    out = season_part_means(adj, "adjusted_anomaly", parts)
    shape = pd.read_csv(processed / "season_shape.csv")[["cell_id", "year", "late_ndvi_anomaly"]]
    out = out.merge(shape, on=["cell_id", "year"], how="left").rename(
        columns={"late_ndvi_anomaly": "late shape (not adj.)"})
    outcomes = list(parts) + ["late shape (not adj.)"]
    centre = cells.set_index("cell_id").geometry.centroid
    coords = pd.DataFrame({"x": centre.x / 1000, "y": centre.y / 1000})
    df = out.merge(exp, on=["cell_id", "year"]).join(coords, on="cell_id")
    df["block"] = spatial_blocks(df["x"], df["y"], e["cluster_block_km"])

    rows = []
    # 1) High vs low per post-war season (ACLED and UCDP)
    for source, gcol in [("ACLED", "group"), ("UCDP", "group_ucdp")]:
        for year in POST:
            d = df[(df["year"] == year) & df[gcol].isin(["high", "low"])]
            for o in outcomes:
                diff, lo, hi = bootstrap_diff(d[o], d[gcol] == "high", d["block"])
                rows.append({"analysis": "1 high-low", "source": source, "year": year, "outcome": o,
                             "estimate": diff, "ci_low": lo, "ci_high": hi,
                             "n_high": int((d[gcol] == "high").sum()), "n_low": int((d[gcol] == "low").sum()),
                             "median_high": d.loc[d[gcol] == "high", o].median(),
                             "median_low": d.loc[d[gcol] == "low", o].median()})

    # 2) Pre-trend / event study: cells grouped by their 2022 exposure, every year
    g22 = exp[exp["year"] == 2022].set_index("cell_id")["group"]
    df["group_2022"] = df["cell_id"].map(g22)
    ev = df[df["group_2022"].isin(["high", "low"])]
    study = {}
    for o in outcomes:
        for year in years:
            d = ev[ev["year"] == year]
            diff, lo, hi = bootstrap_diff(d[o], d["group_2022"] == "high", d["block"])
            study[(o, year)] = (diff, lo, hi)
            rows.append({"analysis": "2 event study (2022 groups)", "source": "ACLED", "year": year, "outcome": o,
                         "estimate": diff, "ci_low": lo, "ci_high": hi,
                         "n_high": int((d["group_2022"] == "high").sum()),
                         "n_low": int((d["group_2022"] == "low").sum())})

    # 3) Two-way fixed effects: outcome ~ log(1 + events) + cell + year, clustered by 25 km blocks
    residuals = {}
    for source, col in [("ACLED", "events"), ("UCDP", "events_ucdp")]:
        for o in outcomes:
            r = twfe(df[o], np.log1p(df[col]), df["cell_id"], df["year"], df["block"])
            rows.append({"analysis": "3 regression per log(1+events)", "source": source, "year": "all",
                         "outcome": o, "estimate": r["beta"], "ci_low": r["ci_low"], "ci_high": r["ci_high"],
                         "n_high": r["n"], "n_low": r["clusters"]})
            if source == "ACLED":
                residuals[o] = r["residuals"]

    # 4) Bias check: weather-adjusted anomaly in low-exposure cells should be ~0
    for year in POST:
        d = df[(df["year"] == year) & (df["group"] == "low")]
        for o in list(parts):
            mean, lo, hi = bootstrap_mean(d[o], d["block"])
            rows.append({"analysis": "4 low-exposure mean", "source": "ACLED", "year": year, "outcome": o,
                         "estimate": mean, "ci_low": lo, "ci_high": hi, "n_low": len(d)})

    # 5) Moran's I of regression residuals, 2022 (neighbours = adjacent cells incl. diagonals)
    for o in outcomes:
        res = df.loc[residuals[o].index].assign(e=residuals[o])
        d = res[res["year"] == 2022]
        i, p = morans_i(d["e"].to_numpy(), d["x"].to_numpy(), d["y"].to_numpy(), max_dist=7.5)
        rows.append({"analysis": "5 Moran's I residuals 2022", "source": "ACLED", "year": 2022, "outcome": o,
                     "estimate": i, "ci_low": np.nan, "ci_high": p, "n_high": len(d)})

    results = pd.DataFrame(rows)
    reports = figs.parent
    results.round(4).to_csv(reports / "exposure_results.csv", index=False)
    show = lambda q: results[results["analysis"] == q].drop(columns="analysis").round(3).to_string(index=False)
    for q in results["analysis"].unique():
        print(f"\n=== {q} ===")
        print(show(q))
    print("(Moran's I rows: estimate = I, ci_high = permutation p-value)")

    # Figures
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.6))
    colours = {"low": "#cfe3cf", "some": "#f6d58e", "high": "#c0504d"}
    for ax, year in zip(axes, POST):
        m = cells.merge(exp[exp["year"] == year], on="cell_id")
        for grp, colour in colours.items():
            m[m["group"] == grp].plot(ax=ax, color=colour, label=grp)
        ax.set_title(f"{year} season: exposure group (ACLED, ≤ {e['buffer_km']} km)", fontsize=10)
        ax.set_axis_off()
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in colours.values()]
    axes[-1].legend(handles, [f"low (0 events)", f"some (1–{e['high_min_events'] - 1})",
                              f"high ({e['high_min_events']}+)"], loc="lower right", fontsize=8)
    fig.suptitle("Conflict exposure per 5 km cropland cell and growing season (historical, aggregated)", fontsize=10)
    fig.tight_layout()
    fig.savefig(figs / "exposure_groups_map.png", dpi=150)

    fig, axes = plt.subplots(1, len(outcomes), figsize=(16, 3.8), sharey=True)
    for ax, o in zip(axes, outcomes):
        est = np.array([study[(o, y)] for y in years])
        ax.errorbar(years, est[:, 0], yerr=[est[:, 0] - est[:, 1], est[:, 2] - est[:, 0]], fmt="o-", capsize=3,
                    color="#c0504d")
        ax.axhline(0, color="grey", linewidth=0.8)
        ax.axvspan(2021.5, years[-1] + 0.5, color="#f3d3c8", alpha=0.4)
        ax.set_title(o, fontsize=10)
        ax.set_xticks(years, [str(y)[2:] for y in years])
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("high − low (2022 groups)")
    fig.suptitle("Weather-adjusted anomaly: cells with 10+ events in 2022 minus cells with 0, every year "
                 "(95% block-bootstrap intervals). Pre-war years should be ≈ 0.", fontsize=10)
    fig.tight_layout()
    fig.savefig(figs / "exposure_event_study.png", dpi=150)
    print(f"\nSaved {reports / 'exposure_results.csv'} and figures in {figs}/exposure_*.png")


if __name__ == "__main__":
    main()
