"""Stage 6: when can the model of normal NDVI be trusted, and the weather-adjusted anomalies.

1. Main fold (train 2018-20, test 2021): errors by part of season, by satellite tile, per cell (map),
   and calibration (does a predicted deviation of +0.05 come true on average?)
2. Permutation importance per input group (a group's columns shuffled together) on 2021
3. Final model: gradient boosting trained on 2018-2021 -> normal NDVI and weather-adjusted anomaly for
   2022-2024; each pre-war year gets a leave-one-year-out version (honest ordinary-year reference)

Run after scripts/build_panel.py:
    python scripts/evaluate_models.py
Output: data/processed/adjusted_anomalies.csv, reports/model_importance.csv, reports/figures/
        model_error_map_2021.png, model_importance.png, adjusted_anomaly_by_year.png, adjusted_anomaly_map_2022.png
"""

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from agridisrupt.config import load_config
from agridisrupt.features import season_part_means, season_parts
from agridisrupt.models.ml import (ALL_FEATURES, FEATURE_GROUPS, fit_gbm, load_model_data, predict_normal,
                                   split_frames)


def error_table(test: pd.DataFrame, by: str) -> pd.DataFrame:
    g = test.groupby(by)
    return pd.DataFrame({"MAE A": g["err A"].apply(lambda e: e.abs().mean()),
                         "MAE C": g["err C"].apply(lambda e: e.abs().mean()),
                         "bias A": g["err A"].mean(), "bias C": g["err C"].mean(), "n": g.size()})


def group_importance(model, test: pd.DataFrame, cols: list[str], repeats: int = 5) -> pd.DataFrame:
    """MAE increase when one input group is shuffled (columns of a group together, so correlated
    inputs such as the three rain sums cannot stand in for each other)."""
    rng = np.random.default_rng(0)
    base = np.abs(model.predict(test[cols]) - test["anomaly"]).mean()
    rows = []
    for group, group_cols in FEATURE_GROUPS.items():
        for name in [group] + (group_cols if len(group_cols) > 1 else []):
            shuffle = group_cols if name == group else [name]
            increases = []
            for _ in range(repeats):
                X = test[cols].copy()
                X[shuffle] = X[shuffle].to_numpy()[rng.permutation(len(X))]
                increases.append(np.abs(model.predict(X) - test["anomaly"]).mean() - base)
            rows.append({"inputs": name if name == group else f"  {name}", "group": name == group,
                         "MAE increase": np.mean(increases)})
    return pd.DataFrame(rows)


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    a, m = config["analysis"], config["models"]
    figs = Path(config["paths"]["reports_figures"])
    reports = figs.parent
    first, last = a["baseline_years"]
    baseline_years = list(range(first, last + 1))
    parts = season_parts(config)
    df = load_model_data(config)
    cells = gpd.read_file(Path(config["paths"]["data_interim"]) / "kharkiv_grid_5km_cropland.gpkg")

    # 1) Main fold diagnostics
    train_years, test_year = m["folds"][-1]
    train, test = split_frames(df, train_years, test_year, a["baseline_min_years"])
    model = fit_gbm(train, ALL_FEATURES, m["gbm"])
    test = test.copy()
    test["err A"] = -test["anomaly"]                                   # baseline predicts anomaly 0
    test["err C"] = model.predict(test[ALL_FEATURES]) - test["anomaly"]
    test["part"] = test["period"].map({p: name for name, ps in parts.items() for p in ps})
    print(f"Main fold: train {train_years} -> test {test_year}\n\nErrors by part of season:")
    print(error_table(test, "part").loc[list(parts)].round(3).to_string())
    print("\nErrors by satellite tile:")
    print(error_table(test, "tile").round(3).to_string())

    per_cell = test.groupby("cell_id")[["err A", "err C"]].mean()
    print(f"\nPer-cell mean error in {test_year}: spread (std) A {per_cell['err A'].std():.3f}, "
          f"C {per_cell['err C'].std():.3f}; cells with |mean error| > 0.05: "
          f"A {(per_cell['err A'].abs() > 0.05).mean():.1%}, C {(per_cell['err C'].abs() > 0.05).mean():.1%}")

    pred = test["err C"] + test["anomaly"]
    bins = pd.qcut(pred, 10)
    calib = test.groupby(bins, observed=True).agg(predicted=("anomaly", lambda s: pred[s.index].mean()),
                                                  observed=("anomaly", "mean"))
    print("\nCalibration (deciles of predicted deviation from normal):")
    print(calib.round(3).to_string(index=False))

    mapped = cells.merge(per_cell.reset_index(), on="cell_id")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    for ax, col, title in zip(axes, ["err A", "err C"], ["A seasonal baseline", "C gradient boosting"]):
        mapped.plot(column=col, cmap="RdBu", vmin=-0.15, vmax=0.15, ax=ax, legend=True,
                    legend_kwds={"shrink": 0.7, "label": "mean error (predicted − observed)"})
        ax.set_title(f"{title}: mean error per cell, {test_year}", fontsize=10)
        ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(figs / "model_error_map_2021.png", dpi=150)

    # 2) Permutation importance on the main fold
    imp = group_importance(model, test, ALL_FEATURES)
    imp.round(4).to_csv(reports / "model_importance.csv", index=False)
    print(f"\nPermutation importance ({test_year}; MAE increase when shuffled):")
    print(imp[["inputs", "MAE increase"]].round(4).to_string(index=False))
    groups = imp[imp["group"]]
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.barh(groups["inputs"], groups["MAE increase"], color="#4a7c59")
    ax.invert_yaxis()
    ax.set_xlabel("MAE increase when shuffled")
    ax.set_title(f"Which inputs the model relies on (test year {test_year})", fontsize=10)
    fig.tight_layout()
    fig.savefig(figs / "model_importance.png", dpi=150)

    # 3) Final model -> weather-adjusted anomalies (pre-war: leave-one-year-out reference)
    out = []
    for year in sorted(df["year"].unique()):
        years = [y for y in baseline_years if y != year]
        out.append(predict_normal(df, years, year, ALL_FEATURES, m["gbm"], a["baseline_min_years"]))
    adj = pd.concat(out, ignore_index=True)
    cols = ["cell_id", "year", "period", "ndvi", "expected", "predicted", "anomaly", "adjusted_anomaly"]
    path = Path(config["paths"]["data_processed"]) / "adjusted_anomalies.csv"
    adj[cols].round(4).to_csv(path, index=False)
    print(f"\nSaved {path}: {len(adj)} rows")

    raw = season_part_means(adj, "anomaly", parts)
    adjusted = season_part_means(adj, "adjusted_anomaly", parts)
    print("\nMedian over cells per part of the season — seasonal baseline anomaly | weather-adjusted:")
    print(pd.concat([raw.groupby("year")[list(parts)].median().add_suffix(" raw"),
                     adjusted.groupby("year")[list(parts)].median().add_suffix(" adj")], axis=1).round(3).to_string())
    pre = adjusted[adjusted["year"] <= last]
    hi = pre[list(parts)].quantile(0.95)
    lo = pre[list(parts)].quantile(0.05)
    print("\nPre-war 5th / 95th percentile of the adjusted part means:")
    print(pd.DataFrame({"p5": lo, "p95": hi}).round(3).T.to_string())
    share = adjusted.groupby("year").apply(lambda g: pd.Series(
        {f"{p} >p95": (g[p].dropna() > hi[p]).mean() * 100 for p in parts}
        | {f"{p} <p5": (g[p].dropna() < lo[p]).mean() * 100 for p in parts}))
    print("\nShare of cells beyond the pre-war range (%), weather-adjusted:")
    print(share.round(1).to_string())

    years = sorted(adjusted["year"].unique())
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=True)
    for ax, p in zip(axes, parts):
        box = ax.boxplot([adjusted.loc[adjusted["year"] == y, p].dropna() for y in years],
                         tick_labels=[str(y) for y in years], showfliers=False, patch_artist=True)
        for patch, y in zip(box["boxes"], years):
            patch.set_facecolor("#cfe3cf" if y <= last else "#f3d3c8")
        ax.axhline(0, color="grey", linewidth=0.8)
        ax.set_title(f"Weather-adjusted anomaly, {p}", fontsize=10)
        ax.grid(axis="y", alpha=0.3)
    axes[0].set_ylabel("observed − predicted normal NDVI")
    fig.suptitle(f"Weather-adjusted anomaly per cell (green: {first}–{last}, model trained on the other pre-war "
                 f"years; red: model trained on {first}–{last})", fontsize=10)
    fig.tight_layout()
    fig.savefig(figs / "adjusted_anomaly_by_year.png", dpi=150)

    m22 = cells.merge(adjusted[adjusted["year"] == 2022], on="cell_id")
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    for ax, p in zip(axes, parts):
        m22.plot(column=p, cmap="RdYlGn", vmin=-0.25, vmax=0.25, ax=ax, legend=True,
                 legend_kwds={"shrink": 0.7, "label": "adjusted anomaly"}, missing_kwds={"color": "lightgrey"})
        ax.set_title(f"2022, {p}", fontsize=10)
        ax.set_axis_off()
    fig.suptitle("2022: NDVI vs weather-adjusted normal (model trained on 2018–2021). "
                 "Red = browner than expected, green = greener.", fontsize=10)
    fig.tight_layout()
    fig.savefig(figs / "adjusted_anomaly_map_2022.png", dpi=150)
    print(f"\nSaved figures in {figs}/")


if __name__ == "__main__":
    main()
