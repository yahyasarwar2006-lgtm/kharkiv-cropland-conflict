"""Overview figure of the climate table: oblast-average temperature, rain and soil
moisture per 14-day period, one line per year.

Run: python scripts/plot_climate_overview.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from agridisrupt.config import load_config


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    df = pd.read_csv(Path(config["paths"]["data_processed"]) / "climate_features.csv")
    avg = df.groupby(["year", "period"])[["t2m_mean", "precip_sum", "swvl1_mean"]].mean().reset_index()

    panels = [("t2m_mean", "temperature (°C)"), ("precip_sum", "rain per 14 days (mm)"),
              ("swvl1_mean", "top-soil moisture (m³/m³)")]
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    for ax, (col, label) in zip(axes, panels):
        for year, g in avg.groupby("year"):
            ax.plot(g["period"], g[col], marker="o", ms=2.5, linewidth=1.2, label=str(year),
                    linestyle="-" if year < 2022 else "--")
        ax.set_title(label, fontsize=10)
        ax.set_xlabel("14-day period (0 = 1 April, 14 = late October)")
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=7, ncol=2)
    fig.suptitle("ERA5-Land weather, average over the 1,192 cropland cells (dashed = 2022–2024)", fontsize=11)
    fig.tight_layout()
    out = Path(config["paths"]["reports_figures"]) / "climate_overview.png"
    fig.savefig(out, dpi=150)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
