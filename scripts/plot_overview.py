"""Stage 4 overview figures of the whole-oblast panel (descriptive only):
1. maps: cropland share, pre-war peak NDVI and pre-war peak timing per cell
2. average seasonal NDVI curve per year
3. season peak NDVI vs spring rain, per cell and year

Run after scripts/build_panel.py:
    python scripts/plot_overview.py
Output: reports/figures/overview_{maps,seasonal_curves,ndvi_vs_rain}.png
"""

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd

from agridisrupt.config import load_config
from agridisrupt.features import season_peaks

SPRING_PERIODS = range(0, 7)   # 1 Apr - 7 Jul: rain while the crop is growing towards its peak


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    first, last = config["analysis"]["baseline_years"]
    figs = Path(config["paths"]["reports_figures"])
    panel = pd.read_csv(Path(config["paths"]["data_processed"]) / "panel.csv")
    starts = panel.groupby("period")["period_start"].first().str[5:]
    label = lambda p: pd.Timestamp(f"2000-{starts[round(p)]}").strftime("%-d %b")

    peaks = season_peaks(panel)
    prewar = peaks[peaks["year"].between(first, last)].groupby("cell_id")[["peak_ndvi", "peak_period"]].mean()
    print(f"Peaks: {len(peaks)} cell-seasons; pre-war ({first}-{last}) mean peak NDVI "
          f"{prewar['peak_ndvi'].median():.2f} (median over cells), typical peak period "
          f"{prewar['peak_period'].median():.1f} (~{label(prewar['peak_period'].median())})")

    # 1) Maps
    cells = gpd.read_file(Path(config["paths"]["data_interim"]) / "kharkiv_grid_5km_cropland.gpkg")
    cells = cells.merge(prewar.reset_index(), on="cell_id")
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    maps = [("cropland_fraction", "Cropland share (WorldCereal 2021)", "YlOrBr", None),
            ("peak_ndvi", f"Peak NDVI, mean {first}–{last}", "YlGn", None),
            ("peak_period", f"Peak timing, mean {first}–{last}", "viridis", None)]
    for ax, (col, title, cmap, _) in zip(axes, maps):
        cells.plot(column=col, cmap=cmap, legend=True, ax=ax, legend_kwds={"shrink": 0.7})
        ax.set_title(title, fontsize=10)
        ax.set_axis_off()
    cbar = fig.axes[-1]   # colour bar of the peak-timing map: period numbers -> dates
    lo, hi = cbar.get_ylim()
    ticks = [t for t in range(15) if lo <= t <= hi]
    cbar.set_yticks(ticks, [label(t) for t in ticks])
    fig.tight_layout()
    fig.savefig(figs / "overview_maps.png", dpi=150)

    # 2) Seasonal curves: median over cells with a usable value in that period
    curves = panel.groupby(["year", "period"])["ndvi"].median().unstack("year")
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for year in curves.columns:
        ax.plot(curves.index, curves[year], marker="o", ms=3, linewidth=1.4, label=str(year),
                linestyle="-" if year <= last else "--")
    ax.set_xticks(curves.index, starts.values, rotation=60, fontsize=8)
    ax.set_ylabel("NDVI (median over cells)")
    ax.set_title("Seasonal NDVI curve per year, Kharkiv oblast cropland cells "
                 f"(solid: {first}–{last}, dashed: later)", fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(figs / "overview_seasonal_curves.png", dpi=150)
    print("\nMedian NDVI per period and year:")
    print(curves.round(2).set_axis(starts.values).to_string())

    # 3) Peak NDVI vs spring rain, per cell-season
    rain = (panel[panel["period"].isin(SPRING_PERIODS)].groupby(["cell_id", "year"])["precip_sum"].sum()
            .rename("spring_rain").reset_index())
    pr = peaks.merge(rain, on=["cell_id", "year"])
    fig, ax = plt.subplots(figsize=(7, 4.6))
    for year, g in pr.groupby("year"):
        ax.scatter(g["spring_rain"], g["peak_ndvi"], s=4, alpha=0.35, label=str(year),
                   marker="o" if year <= last else "x")
    ax.set_xlabel(f"Rain {label(SPRING_PERIODS[0])} – early Jul (mm)")
    ax.set_ylabel("Season peak NDVI")
    ax.set_title("Season peak NDVI vs spring rain (one point = one cell in one year)", fontsize=10)
    ax.legend(fontsize=8, markerscale=3, ncol=2)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(figs / "overview_ndvi_vs_rain.png", dpi=150)
    by_year = pr.groupby("year")[["spring_rain", "peak_ndvi", "peak_period"]].median()
    print("\nPer year (median over cells): spring rain (mm), peak NDVI, peak period")
    print(by_year.round(2).to_string())
    print(f"correlation spring rain vs peak NDVI, pre-war cell-seasons: "
          f"{pr[pr['year'] <= last][['spring_rain', 'peak_ndvi']].corr().iloc[0, 1]:.2f}")
    print(f"\nSaved figures in {figs}/overview_*.png")


if __name__ == "__main__":
    main()
