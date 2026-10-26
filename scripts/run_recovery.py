"""Stage 8 (RQ3): did weather-adjusted greenness return to normal where conflict exposure ended?
Follows the plan written BEFORE any result (experiments.md, Experiment 6; config `recovery:`).

Run after scripts/run_exposure_analysis.py:
    python scripts/run_recovery.py
Output: reports/recovery_results.csv, reports/figures/recovery_gaps.png, reports/figures/recovery_map.png
"""

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from agridisrupt.analysis import bootstrap_diff, spatial_blocks
from agridisrupt.config import load_config
from agridisrupt.conflict import exposure_history
from agridisrupt.features import season_part_means, season_parts

GROUPS = ["ended", "persistent"]


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    r, e = config["recovery"], config["exposure"]
    processed, figs = Path(config["paths"]["data_processed"]), Path(config["paths"]["reports_figures"])
    first, last = config["analysis"]["baseline_years"]

    exp = pd.read_csv(processed / "exposure.csv")
    history = exposure_history(exp, r["start_year"], r["later_years"], e["high_min_events"])
    print("Cells per exposure history:", history.value_counts().to_dict())

    parts = season_parts(config)
    adj = pd.read_csv(processed / "adjusted_anomalies.csv")
    df = season_part_means(adj, "adjusted_anomaly", parts)
    shape = pd.read_csv(processed / "season_shape.csv")[["cell_id", "year", "late_ndvi_anomaly"]]
    df = df.merge(shape, on=["cell_id", "year"], how="left").rename(
        columns={"late_ndvi_anomaly": "late shape (not adj.)"})
    outcomes = list(parts) + ["late shape (not adj.)"]
    cells = gpd.read_file(Path(config["paths"]["data_interim"]) / "kharkiv_grid_5km_cropland.gpkg")
    centre = cells.set_index("cell_id").geometry.centroid
    df["history"] = df["cell_id"].map(history)
    df["block"] = spatial_blocks(df["cell_id"].map(centre.x / 1000), df["cell_id"].map(centre.y / 1000),
                                 e["cluster_block_km"])

    # Gap to the never-exposed reference, every season
    rows = []
    years = sorted(df["year"].unique())
    for group in GROUPS:
        for o in outcomes:
            for year in years:
                d = df[(df["year"] == year) & df["history"].isin([group, "reference"])]
                gap, lo, hi = bootstrap_diff(d[o], d["history"] == group, d["block"])
                rows.append({"group": group, "outcome": o, "year": year, "gap": gap, "ci_low": lo, "ci_high": hi,
                             "n_group": int((d["history"] == group).sum()),
                             "n_reference": int((d["history"] == "reference").sum())})
    res = pd.DataFrame(rows)

    # Recovery rule: within the group's pre-war range AND interval includes 0
    pre = res[res["year"].between(first, last)].groupby(["group", "outcome"])["gap"].apply(lambda g: g.abs().max())
    res["prewar_max_abs_gap"] = [pre[(g, o)] for g, o in zip(res["group"], res["outcome"])]
    rule = (res["gap"].abs() <= res["prewar_max_abs_gap"]) & (res["ci_low"] <= 0) & (res["ci_high"] >= 0)
    res["recovered"] = rule.astype("boolean").where(res["year"].isin(r["later_years"]))   # only for later seasons
    reports = figs.parent
    res.round(4).to_csv(reports / "recovery_results.csv", index=False)

    print("\nGap to never-exposed cells (weather-adjusted), with 95% interval; pre-war max |gap|; recovered?")
    for group in GROUPS:
        for o in outcomes:
            d = res[(res["group"] == group) & (res["outcome"] == o)].set_index("year")
            line = "  ".join(f"{y}: {d.loc[y, 'gap']:+.3f} [{d.loc[y, 'ci_low']:+.3f},{d.loc[y, 'ci_high']:+.3f}]"
                             for y in years if y >= r["start_year"])
            rec = [y for y in r["later_years"] if d.loc[y, "recovered"] == True]   # noqa: E712
            print(f"{group:>10} | {o:<22} pre-war max |gap| {d['prewar_max_abs_gap'].iloc[0]:.3f} | {line} | "
                  f"recovered: {rec[0] if rec else 'not by ' + str(r['later_years'][-1])}")

    # Figure: gaps over time per outcome, ended vs persistent
    fig, axes = plt.subplots(1, len(outcomes), figsize=(16, 3.8), sharey=True)
    colours = {"ended": "#2e75b6", "persistent": "#c0504d"}
    for ax, o in zip(axes, outcomes):
        for k, group in enumerate(GROUPS):
            d = res[(res["group"] == group) & (res["outcome"] == o)]
            xs = d["year"] + (k - 0.5) * 0.15
            ax.errorbar(xs, d["gap"], yerr=[d["gap"] - d["ci_low"], d["ci_high"] - d["gap"]], fmt="o-",
                        capsize=2, color=colours[group], label=f"{group} (n={d['n_group'].iloc[0]})")
            band = d["prewar_max_abs_gap"].iloc[0]
            ax.axhspan(-band, band, color=colours[group], alpha=0.06)
        ax.axhline(0, color="grey", linewidth=0.8)
        ax.axvline(2021.5, color="grey", linestyle=":", linewidth=1)
        ax.set_title(o, fontsize=10)
        ax.set_xticks(years, [str(y)[2:] for y in years])
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("gap to never-exposed cells")
    axes[-1].legend(fontsize=8)
    fig.suptitle("Weather-adjusted greenness: cells where exposure ENDED after 2022 vs PERSISTENT, minus never-exposed "
                 "cells (shaded = pre-war range)", fontsize=10)
    fig.tight_layout()
    fig.savefig(figs / "recovery_gaps.png", dpi=150)

    # Map: per ended cell, relative anomaly (cell - reference mean that season), 2022 vs 2024, peak and spring
    ref_mean = df[df["history"] == "reference"].groupby("year")[outcomes].mean()
    rel = df[df["history"] == "ended"].copy()
    for o in outcomes:
        rel[o] = rel[o] - rel["year"].map(ref_mean[o])
    fig, axes = plt.subplots(1, 4, figsize=(17, 4.4))
    base = cells[cells["cell_id"].isin(df["cell_id"])]
    for ax, (o, year) in zip(axes, [("peak", 2022), ("peak", 2024), ("spring", 2022), ("spring", 2024)]):
        base.plot(ax=ax, color="#eeeeee")
        m = cells.merge(rel[rel["year"] == year][["cell_id", o]], on="cell_id")
        m.plot(column=o, cmap="RdYlGn", vmin=-0.2, vmax=0.2, ax=ax, legend=True, legend_kwds={"shrink": 0.6})
        ax.set_title(f"{o} {year}: ended cells vs never-exposed", fontsize=9)
        ax.set_axis_off()
    fig.suptitle("Cells where exposure ended after 2022 (coloured; grey = other cells). Green = greener than "
                 "never-exposed cells that season, red = browner. Historical, 5 km aggregates.", fontsize=10)
    fig.tight_layout()
    fig.savefig(figs / "recovery_map.png", dpi=150)
    print(f"\nSaved {reports / 'recovery_results.csv'} and figures in {figs}/recovery_*.png")


if __name__ == "__main__":
    main()
