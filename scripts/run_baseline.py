"""Stage 4 seasonal baseline: expected NDVI per cell + period from the pre-war years, anomalies
for every year (leave-one-year-out for the pre-war years), summaries and the first anomaly maps.

Run after scripts/build_panel.py:
    python scripts/run_baseline.py
Output: data/processed/baseline_anomalies.csv,
        data/processed/season_shape.csv, reports/figures/baseline_{anomaly_by_year,shape_by_year}.png,
        reports/figures/baseline_anomaly_map_{year}.png
"""

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd

from agridisrupt.config import load_config
from agridisrupt.features import season_part_means, season_parts, season_shape
from agridisrupt.models.baseline import baseline_anomalies

MAP_YEARS = [2022, 2023, 2024]


def part_labels(parts: dict, panel: pd.DataFrame) -> dict:
    """{"spring": "spring (1 Apr – 9 Jun)", ...} from the period start dates."""
    starts = panel.groupby("period")["period_start"].first()
    def day(p, end=False):
        if end and p == starts.index.max():   # the last period also takes the leftover days of the season
            return "end " + pd.Timestamp(starts[p]).strftime("%b")
        return (pd.Timestamp(starts[p]) + pd.Timedelta(days=13 if end else 0)).strftime("%-d %b")
    return {name: f"{name} ({day(ps[0])} – {day(ps[-1], end=True)})" for name, ps in parts.items()}


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    a = config["analysis"]
    first, last = a["baseline_years"]
    baseline_years = list(range(first, last + 1))
    figs = Path(config["paths"]["reports_figures"])
    panel = pd.read_csv(Path(config["paths"]["data_processed"]) / "panel.csv")

    anom = baseline_anomalies(panel, baseline_years, a["baseline_min_years"])
    out = Path(config["paths"]["data_processed"]) / "baseline_anomalies.csv"
    anom[["cell_id", "year", "period", "ndvi", "expected", "n_years", "anomaly"]].round(4).to_csv(out, index=False)
    print(f"Saved {out}: {len(anom)} rows; anomaly available for {anom['anomaly'].notna().mean():.1%} "
          f"(empty when NDVI is empty or fewer than {a['baseline_min_years']} baseline years)")

    # Per year: pre-war rows are leave-one-year-out = honest 'ordinary year' reference
    g = anom.groupby("year")["anomaly"]
    by_year = pd.DataFrame({"mean": g.mean(), "median": g.median(), "MAE": g.apply(lambda s: s.abs().mean()),
                            "n": g.count()})
    print("\nAnomaly per 14-day value (observed - expected), per year:")
    print(by_year.round(3).to_string())

    labels = part_labels(season_parts(config), panel)
    parts = season_part_means(anom, "anomaly", season_parts(config)).rename(columns=labels)
    PARTS = list(labels.values())
    print("\nMedian over cells of the mean anomaly per part of the season:")
    print(parts.groupby("year")[list(PARTS)].median().round(3).to_string())
    pre = parts[parts["year"] <= last]
    print("\nPre-war spread (5th to 95th percentile over cell-years) = range of an ordinary year:")
    print(pre[list(PARTS)].quantile([0.05, 0.95]).round(3).to_string())

    # Figure 1: distribution of part-of-season anomalies per year
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=True)
    years = sorted(parts["year"].unique())
    for ax, name in zip(axes, PARTS):
        data = [parts.loc[parts["year"] == y, name].dropna() for y in years]
        box = ax.boxplot(data, tick_labels=[str(y) for y in years], showfliers=False, patch_artist=True)
        for patch, y in zip(box["boxes"], years):
            patch.set_facecolor("#cfe3cf" if y <= last else "#f3d3c8")
        ax.axhline(0, color="grey", linewidth=0.8)
        ax.set_title(f"Mean anomaly, {name}", fontsize=10)
        ax.grid(axis="y", alpha=0.3)
    axes[0].set_ylabel("NDVI anomaly (observed − expected)")
    fig.suptitle(f"Seasonal-baseline anomaly per cell (green: {first}–{last}, leave-one-year-out; "
                 "red: later years)", fontsize=10)
    fig.tight_layout()
    fig.savefig(figs / "baseline_anomaly_by_year.png", dpi=150)

    # Figure 2: anomaly maps per year and part of the season (descriptive, 5 km cells)
    cells = gpd.read_file(Path(config["paths"]["data_interim"]) / "kharkiv_grid_5km_cropland.gpkg")
    cells = cells[cells["cell_id"].isin(parts["cell_id"])]
    lim = 0.25
    for year in MAP_YEARS:
        m = cells.merge(parts[parts["year"] == year], on="cell_id", how="left")
        fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
        for ax, name in zip(axes, PARTS):
            m.plot(column=name, cmap="RdYlGn", vmin=-lim, vmax=lim, ax=ax, legend=True,
                   legend_kwds={"shrink": 0.7, "label": "NDVI anomaly"},
                   missing_kwds={"color": "lightgrey"})
            ax.set_title(f"{year}, {name}", fontsize=10)
            ax.set_axis_off()
        fig.suptitle(f"{year}: NDVI vs seasonal baseline ({first}–{last}). Red = browner than normal, "
                     "green = greener. Not climate-adjusted.", fontsize=10)
        fig.tight_layout()
        fig.savefig(figs / f"baseline_anomaly_map_{year}.png", dpi=150)
    # Season shape: peak NDVI, peak timing, late-season greenness, each vs its own pre-war normal per cell
    shape = season_shape(panel, season_parts(config)["late"], a["late_min_periods"])
    measures = {"peak_ndvi": "peak NDVI", "peak_period": "peak timing (periods of 14 days)",
                "late_ndvi": "late-season NDVI (5 Aug – Oct)"}
    for col in measures:
        res = baseline_anomalies(shape, baseline_years, a["baseline_min_years"], value=col, by=("cell_id",))
        shape = shape.merge(res[["cell_id", "year", "expected", "anomaly"]]
                            .rename(columns={"expected": f"{col}_expected", "anomaly": f"{col}_anomaly"}),
                            on=["cell_id", "year"])
    shape_out = Path(config["paths"]["data_processed"]) / "season_shape.csv"
    shape.round(4).to_csv(shape_out, index=False)
    anomaly_cols = [f"{c}_anomaly" for c in measures]
    print(f"\nSaved {shape_out}: {len(shape)} cell-seasons")
    print("Median shape anomaly per year (pre-war = leave-one-year-out):")
    print(shape.groupby("year")[anomaly_cols].median().round(3).to_string())
    print("Pre-war 5th / 95th percentile:")
    print(shape[shape["year"] <= last][anomaly_cols].quantile([0.05, 0.95]).round(3).to_string())

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for ax, (col, name) in zip(axes, measures.items()):
        data = [shape.loc[shape["year"] == y, f"{col}_anomaly"].dropna() for y in years]
        box = ax.boxplot(data, tick_labels=[str(y) for y in years], showfliers=False, patch_artist=True)
        for patch, y in zip(box["boxes"], years):
            patch.set_facecolor("#cfe3cf" if y <= last else "#f3d3c8")
        ax.axhline(0, color="grey", linewidth=0.8)
        ax.set_title(f"Anomaly of {name}", fontsize=10)
        ax.grid(axis="y", alpha=0.3)
    fig.suptitle(f"Season-shape anomalies per cell vs its {first}–{last} normal (green: pre-war, "
                 "leave-one-year-out; red: later years). Timing > 0 = later peak.", fontsize=10)
    fig.tight_layout()
    fig.savefig(figs / "baseline_shape_by_year.png", dpi=150)
    print(f"\nSaved figures in {figs}/baseline_*.png")


if __name__ == "__main__":
    main()
