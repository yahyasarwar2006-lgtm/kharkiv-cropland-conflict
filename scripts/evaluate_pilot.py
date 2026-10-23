"""Experiment 1: score the four pre-set checks and plot the pilot NDVI curves.

The scoring rules are those written in reports/experiments.md on 29 Sep 2026,
before any composite existed. Run after scripts/run_pilot_timeseries.py.

Run: python scripts/evaluate_pilot.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from agridisrupt.config import load_config

VALID_SHARE_MIN = 0.5      # check 1: a cell-composite is valid if >= 50% of its cropland pixels are clear
SUMMER_MONTHS = [5, 6, 7, 8]
AUTUMN_MONTHS = [9, 10]
MIN_HARVEST_DROP = 0.2     # check 2
LEVEL_TOLERANCE = 0.05     # check 3
MAX_MINUTES, MAX_MEMORY_GB = 120, 4.0  # check 4


def block_curve(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Block-average NDVI per period: mean over cells whose composite is valid."""
    valid = df[df["valid_share"] >= VALID_SHARE_MIN]
    curve = valid.groupby(["year", "period", "period_start"])[column].agg(["mean", "min", "max", "count"])
    return curve.reset_index()


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    interim = Path(config["paths"]["data_interim"])
    figures = Path(config["paths"]["reports_figures"])
    years = config["pilot"]["years"]

    df = pd.concat([pd.read_csv(interim / f"pilot_composites_{y}.csv", parse_dates=["period_start"]) for y in years])
    df["start_month"] = df["period_start"].dt.month
    runs = pd.read_csv(interim / "pilot_run_log.csv").drop_duplicates("year", keep="last")

    # ---- Check 1: valid data in May-Aug
    summer = df[df["start_month"].isin(SUMMER_MONTHS)]
    c1 = summer.assign(ok=summer["valid_share"] >= VALID_SHARE_MIN).groupby("year")["ok"].mean()
    c1_pass = bool((c1 > 0.5).all())

    # ---- Check 2: recognisable season (peak May-Aug, drop >= 0.2 to lowest Sep-Oct value)
    curve = block_curve(df, "ndvi_median")
    curve["start_month"] = curve["period_start"].dt.month
    c2_rows = []
    for year, g in curve.groupby("year"):
        peak = g.loc[g["mean"].idxmax()]
        autumn = g[g["start_month"].isin(AUTUMN_MONTHS)]["mean"]
        drop = peak["mean"] - autumn.min() if len(autumn) else float("nan")
        c2_rows.append({"year": year, "peak_ndvi": round(peak["mean"], 3),
                        "peak_period_start": peak["period_start"].date(),
                        "harvest_drop": round(drop, 3),
                        "ok": peak["start_month"] in SUMMER_MONTHS and drop >= MIN_HARVEST_DROP})
    c2 = pd.DataFrame(c2_rows)
    c2_pass = bool(c2["ok"].all())

    # ---- Check 3: seasonal median level of 2022-23 (corrected) within 2019-21 range +- 0.05
    level = curve.groupby("year")["mean"].median()
    pre = level[level.index < 2022]
    low, high = pre.min() - LEVEL_TOLERANCE, pre.max() + LEVEL_TOLERANCE
    post = level[level.index >= 2022]
    c3_pass = bool(((post >= low) & (post <= high)).all())
    raw_curve = block_curve(df[df["year"] >= 2022], "ndvi_median_uncorrected")
    raw_level = raw_curve.groupby("year")["mean"].median()

    # ---- Check 4: resources
    total_minutes, peak_mem = runs["minutes"].sum(), runs["peak_memory_gb"].max()
    c4_pass = bool(total_minutes < MAX_MINUTES and peak_mem < MAX_MEMORY_GB)

    print("CHECK 1 - share of May-Aug cell-composites with >= 50% clear cropland, per year:")
    print(c1.round(3).to_string(), f"\n  -> {'PASS' if c1_pass else 'FAIL'} (need > 0.5 every year)\n")
    print("CHECK 2 - block-average curve: peak and drop to lowest Sep-Oct value:")
    print(c2.to_string(index=False), f"\n  -> {'PASS' if c2_pass else 'FAIL'}\n")
    print("CHECK 3 - seasonal median of block-average NDVI:")
    for y, v in level.items():
        extra = f"   (uncorrected: {raw_level[y]:.3f})" if y in raw_level else ""
        print(f"  {y}: {v:.3f}{extra}")
    print(f"  allowed range for 2022-23 (2019-21 range +- {LEVEL_TOLERANCE}): {low:.3f} to {high:.3f}")
    print(f"  -> {'PASS' if c3_pass else 'FAIL'}\n")
    print("CHECK 4 - resources:")
    print(runs.to_string(index=False))
    print(f"  total {total_minutes:.1f} min (limit {MAX_MINUTES}), peak memory {peak_mem:.2f} GB (limit {MAX_MEMORY_GB})")
    print(f"  -> {'PASS' if c4_pass else 'FAIL'}")

    # ---- Figure 1: block-average curves per year (x = day of season)
    fig, ax = plt.subplots(figsize=(9, 5))
    colors = {2019: "#1b9e77", 2020: "#7570b3", 2021: "#66a61e", 2022: "#d95f02", 2023: "#e7298a"}
    for year, g in curve.groupby("year"):
        x = g["period_start"].dt.dayofyear
        ax.plot(x, g["mean"], marker="o", ms=3, color=colors[year], label=str(year))
        ax.fill_between(x, g["min"], g["max"], color=colors[year], alpha=0.08)
    for year, g in raw_curve.groupby("year"):
        ax.plot(g["period_start"].dt.dayofyear, g["mean"], linestyle=":", color=colors[year],
                label=f"{year} without offset fix")
    month_starts = pd.date_range("2021-04-01", "2021-10-01", freq="MS")
    ax.set_xticks(month_starts.dayofyear, month_starts.strftime("%b"))
    ax.set_ylabel("NDVI (cropland, 14-day median)")
    ax.set_title("Pilot block: cropland NDVI through the season\n"
                 "line = mean of 5 km cells, band = cell range; only composites with >= 50% clear cropland")
    ax.legend(ncol=2, fontsize=8)
    ax.grid(alpha=0.3)
    fig.savefig(figures / "pilot_ndvi_curves.png", dpi=150, bbox_inches="tight")

    # ---- Figure 2: data availability
    avail = df.groupby(["year", "period_start"])["valid_share"].median().reset_index()
    fig, ax = plt.subplots(figsize=(9, 3.5))
    for year, g in avail.groupby("year"):
        ax.plot(g["period_start"].dt.dayofyear, g["valid_share"], marker="o", ms=3, color=colors[year], label=str(year))
    ax.axhline(VALID_SHARE_MIN, color="grey", linestyle="--", linewidth=0.8)
    ax.set_xticks(month_starts.dayofyear, month_starts.strftime("%b"))
    ax.set_ylabel("clear cropland share\n(median over cells)")
    ax.set_ylim(0, 1.02)
    ax.set_title("Pilot block: how much cropland was cloud-free in each 14-day composite")
    ax.legend(ncol=5, fontsize=8)
    ax.grid(alpha=0.3)
    fig.savefig(figures / "pilot_valid_share.png", dpi=150, bbox_inches="tight")
    print("\nSaved reports/figures/pilot_ndvi_curves.png and pilot_valid_share.png")


if __name__ == "__main__":
    main()
