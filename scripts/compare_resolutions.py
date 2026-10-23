"""Experiment 1b: score 20 m vs 10 m Sentinel-2 reading on the pilot block.

Criteria were written in reports/experiments.md before any 20 m result existed.
Run after: python scripts/run_pilot_timeseries.py 2021 --suffix _10m_retime
           python scripts/run_pilot_timeseries.py 2021 2022 --res 20
Run: python scripts/compare_resolutions.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from agridisrupt.config import load_config

YEARS = [2021, 2022]
VALID = 0.5
MAX_MEDIAN_DIFF, MAX_P95_DIFF = 0.02, 0.05   # criterion 1
MAX_CURVE_DIFF = 0.02                         # criterion 2
MAX_VALID_SHARE_GAP = 0.05                    # criterion 3
MAX_TIME_RATIO = 0.5                          # criterion 4


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    interim = Path(config["paths"]["data_interim"])
    key = ["year", "period", "cell_id"]

    ten = pd.concat([pd.read_csv(interim / f"pilot_composites_{y}.csv") for y in YEARS])
    twenty = pd.concat([pd.read_csv(interim / f"pilot_composites_{y}_20m.csv") for y in YEARS])
    both = ten.merge(twenty, on=key, suffixes=("_10", "_20"))
    valid = both[(both["valid_share_10"] >= VALID) & (both["valid_share_20"] >= VALID)].copy()
    valid["diff"] = valid["ndvi_median_20"] - valid["ndvi_median_10"]
    abs_diff = valid["diff"].abs()

    # 1. agreement per cell-composite
    med, p95 = abs_diff.median(), abs_diff.quantile(0.95)
    c1 = med <= MAX_MEDIAN_DIFF and p95 <= MAX_P95_DIFF

    # 2. block-average curves
    curves = valid.groupby(["year", "period"])[["ndvi_median_10", "ndvi_median_20"]].mean()
    curve_gap = (curves["ndvi_median_20"] - curves["ndvi_median_10"]).abs()
    c2 = curve_gap.max() <= MAX_CURVE_DIFF

    # 3. valid data
    share10 = (both["valid_share_10"] >= VALID).mean()
    share20 = (both["valid_share_20"] >= VALID).mean()
    c3 = abs(share20 - share10) <= MAX_VALID_SHARE_GAP

    # 4. speed (same-day 2021 runs)
    runs = pd.read_csv(interim / "pilot_run_log.csv")
    t10 = runs[(runs.year == 2021) & (runs.run == "_10m_retime")]["minutes"].iloc[-1]
    t20 = runs[(runs.year == 2021) & (runs.resolution_m == 20)]["minutes"].iloc[-1]
    c4 = t20 / t10 <= MAX_TIME_RATIO

    print(f"Cell-composites compared (valid at both resolutions): {len(valid)} of {len(both)}")
    print(f"1. |NDVI 20 m - 10 m|: median {med:.4f} (limit {MAX_MEDIAN_DIFF}), 95th pct {p95:.4f} "
          f"(limit {MAX_P95_DIFF}); mean signed diff {valid['diff'].mean():+.4f} -> {'PASS' if c1 else 'FAIL'}")
    print(f"2. largest block-average curve gap: {curve_gap.max():.4f} (limit {MAX_CURVE_DIFF}) -> {'PASS' if c2 else 'FAIL'}")
    print(f"3. valid cell-composites: 10 m {share10:.1%}, 20 m {share20:.1%} -> {'PASS' if c3 else 'FAIL'}")
    print(f"4. 2021 run time: 10 m {t10:.1f} min, 20 m {t20:.1f} min (ratio {t20 / t10:.2f}, limit {MAX_TIME_RATIO}) "
          f"-> {'PASS' if c4 else 'FAIL'}")
    print("ALL PASS -> propose 20 m" if all([c1, c2, c3, c4]) else "NOT ALL PASS -> stay at 10 m")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    ax = axes[0]
    ax.scatter(valid["ndvi_median_10"], valid["ndvi_median_20"], s=6, alpha=0.5)
    ax.plot([0, 1], [0, 1], color="grey", linewidth=0.8)
    ax.set_xlabel("NDVI per cell-composite, 10 m")
    ax.set_ylabel("NDVI per cell-composite, 20 m")
    ax.set_title("Each dot = one 5 km cell in one 14-day period")
    ax = axes[1]
    for year, g in curves.reset_index().groupby("year"):
        ax.plot(g["period"], g["ndvi_median_10"], marker="o", ms=3, label=f"{year} 10 m")
        ax.plot(g["period"], g["ndvi_median_20"], linestyle="--", label=f"{year} 20 m")
    ax.set_xlabel("14-day period (0 = 1 April)")
    ax.set_ylabel("block-average NDVI")
    ax.set_title("Block-average curves")
    ax.legend(fontsize=8)
    out = Path(config["paths"]["reports_figures"]) / "resolution_test_10m_vs_20m.png"
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
