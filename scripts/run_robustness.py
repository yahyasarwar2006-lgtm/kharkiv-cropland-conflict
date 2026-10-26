"""Stage 9: do the RQ2 results survive other reasonable choices? Plan written BEFORE running
(experiments.md, Experiment 7; config `robustness:`).
  main = Stage 7 setting (5 km, ML-adjusted anomaly)    R1 = only nearby low cells (<= 25 km of a high cell)
  R2 = exposure within 10 km                             R3 = seasonal-baseline anomaly (no weather adjustment)

Run after scripts/run_exposure_analysis.py:
    python scripts/run_robustness.py
Output: reports/robustness_results.csv, reports/figures/robustness_forest.png
"""

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd

from agridisrupt.analysis import bootstrap_diff, spatial_blocks, twfe
from agridisrupt.config import load_config
from agridisrupt.conflict import exposure_group, load_acled_events, season_exposure
from agridisrupt.features import season_part_means, season_parts

# (test, year, outcome, expected sign); sign 0 = interval should include 0
TESTS = [("a", 2022, "peak", -1), ("b", 2023, "spring", +1), ("c", 2024, "spring", +1), ("c", 2024, "peak", +1),
         ("c", 2024, "late", +1), ("d", "all", "spring", +1), ("d", "all", "late", +1), ("d", "all", "peak", 0)]


def nearby_low(d: pd.DataFrame, max_km: float) -> pd.Series:
    """True for low cells whose centre is within max_km of some high cell (same rows = one season)."""
    hi = d[d["group"] == "high"][["x", "y"]].to_numpy()
    lo = d[["x", "y"]].to_numpy()
    if len(hi) == 0:
        return pd.Series(False, index=d.index)
    dist = np.hypot(lo[:, None, 0] - hi[None, :, 0], lo[:, None, 1] - hi[None, :, 1]).min(axis=1)
    return pd.Series(dist <= max_km, index=d.index)


def run_tests(df: pd.DataFrame, variant: str, nearby_km: float | None) -> list[dict]:
    rows = []
    for test, year, o, sign in TESTS:
        if year == "all":
            r = twfe(df[o], np.log1p(df["events"]), df["cell_id"], df["year"], df["block"])
            est, lo, hi, n = r["beta"], r["ci_low"], r["ci_high"], f"{r['n']} rows"
        else:
            d = df[df["year"] == year]
            keep = d["group"] == "high"
            low = d["group"] == "low"
            if nearby_km is not None:
                low &= nearby_low(d, nearby_km)
            d = d[keep | low]
            est, lo, hi = bootstrap_diff(d[o], d["group"] == "high", d["block"])
            n = f"{int(keep.sum())} high / {int(low.sum())} low"
        holds = (lo > 0 or hi < 0) and np.sign(est) == sign if sign != 0 else (lo <= 0 <= hi)
        rows.append({"variant": variant, "test": test, "year": year, "outcome": o, "estimate": est,
                     "ci_low": lo, "ci_high": hi, "n": n, "holds": bool(holds)})
    return rows


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    e, a, rb = config["exposure"], config["analysis"], config["robustness"]
    raw, processed = Path(config["paths"]["data_raw"]), Path(config["paths"]["data_processed"])
    figs = Path(config["paths"]["reports_figures"])
    years = list(range(config["time"]["start_year"], config["time"]["end_year"] + 1))
    parts = season_parts(config)

    cells = gpd.read_file(Path(config["paths"]["data_interim"]) / "kharkiv_grid_5km_cropland.gpkg")
    cells = cells[cells["cropland_fraction"] >= config["grid"]["min_cropland_fraction"]].reset_index(drop=True)
    centre = cells.set_index("cell_id").geometry.centroid
    coords = pd.DataFrame({"x": centre.x / 1000, "y": centre.y / 1000})

    exp5 = pd.read_csv(processed / "exposure.csv")[["cell_id", "year", "events"]]
    lon0, lat0, lon1, lat1 = cells.to_crs("EPSG:4326").total_bounds
    acled = load_acled_events(next(raw.glob(e["source_glob"])), e["event_types"], e["max_geo_precision"],
                              (lon0 - 0.3, lat0 - 0.3, lon1 + 0.3, lat1 + 0.3))
    exp10 = season_exposure(acled, cells, e["robustness_buffer_km"] * 1000, years, a["war_start"], e["season_end"])

    ml = season_part_means(pd.read_csv(processed / "adjusted_anomalies.csv"), "adjusted_anomaly", parts)
    base = season_part_means(pd.read_csv(processed / "baseline_anomalies.csv"), "anomaly", parts)

    def frame(outcomes, exp):
        df = outcomes.merge(exp, on=["cell_id", "year"]).join(coords, on="cell_id")
        df["group"] = exposure_group(df["events"], e["low_max_events"], e["high_min_events"])
        df["block"] = spatial_blocks(df["x"], df["y"], e["cluster_block_km"])
        return df

    rows = []
    rows += run_tests(frame(ml, exp5), "main (5 km, ML-adjusted)", None)
    rows += run_tests(frame(ml, exp5), f"R1 nearby low cells (≤ {rb['nearby_km']} km)", rb["nearby_km"])
    rows += run_tests(frame(ml, exp10), f"R2 {e['robustness_buffer_km']} km exposure", None)
    rows += run_tests(frame(base, exp5), "R3 no weather adjustment", None)
    res = pd.DataFrame(rows)
    res.round(4).to_csv(figs.parent / "robustness_results.csv", index=False)
    print(res.round(3).to_string(index=False))
    print("\nHolds per variant:", res.groupby("variant", sort=False)["holds"].agg(lambda h: f"{h.sum()}/{len(h)}")
          .to_dict())

    labels = [f"({t}) {o} {y}" + (" [regression]" if y == "all" else "") for t, y, o, _ in TESTS]
    variants = list(dict.fromkeys(res["variant"]))
    colours = ["black", "#2e75b6", "#c0504d", "#8064a2"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6), gridspec_kw={"width_ratios": [5, 3]})
    for ax, which in zip(axes, ["groups", "regression"]):
        idx = [i for i, (_, y, _, _) in enumerate(TESTS) if (y == "all") == (which == "regression")]
        for k, (v, c) in enumerate(zip(variants, colours)):
            d = res[res["variant"] == v].iloc[idx]
            ys = np.arange(len(idx)) + (k - 1.5) * 0.18
            ax.errorbar(d["estimate"], ys, xerr=[d["estimate"] - d["ci_low"], d["ci_high"] - d["estimate"]],
                        fmt="o", color=c, capsize=2, ms=4, label=v)
        ax.axvline(0, color="grey", linewidth=0.8)
        ax.set_yticks(range(len(idx)), [labels[i] for i in idx], fontsize=8)
        ax.invert_yaxis()
        ax.grid(axis="x", alpha=0.3)
        ax.xaxis.set_major_locator(MaxNLocator(5))
        ax.set_xlabel("high − low (NDVI)" if which == "groups" else "per log(1 + events)")
    axes[0].legend(fontsize=7, loc="lower left")
    fig.suptitle("Robustness of the conflict–greenness results (95% intervals)", fontsize=10)
    fig.tight_layout()
    fig.savefig(figs / "robustness_forest.png", dpi=150)
    print(f"\nSaved {figs.parent / 'robustness_results.csv'} and {figs / 'robustness_forest.png'}")


if __name__ == "__main__":
    main()
