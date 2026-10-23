"""Stage 5: compare models of "normal" NDVI on held-out pre-war years (forward in time only).
A = seasonal baseline (predicted anomaly 0), B = ridge regression, C = gradient boosting.
Plus an ablation: which input groups (rain, temperature, soil moisture) improve the main fold?

Run after scripts/build_panel.py:
    python scripts/run_models.py
Output: reports/model_comparison.csv, reports/model_ablation.csv, reports/figures/model_mae_by_period.png
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from agridisrupt.config import load_config
from agridisrupt.models.ml import (FEATURE_GROUPS, ALL_FEATURES, fit_gbm, fit_ridge, load_model_data,
                                   ridge_design, scores, split_frames)


def run_fold(df, train_years, test_year, cols, config, n_periods):
    """Fit B and C on one fold; return test rows with each model's predicted anomaly, and ridge alpha."""
    m = config["models"]
    train, test = split_frames(df, train_years, test_year, config["analysis"]["baseline_min_years"])
    ridge, alpha = fit_ridge(train, cols, n_periods, m["ridge_alphas"])
    gbm = fit_gbm(train, cols, m["gbm"])
    test = test.copy()
    test["A baseline"] = 0.0
    test["B ridge"] = ridge.predict(ridge_design(test, cols, n_periods))
    test["C boosting"] = gbm.predict(test[cols])
    return test, alpha, len(train)


def main():
    config = load_config("configs/kharkiv_v1.yaml")
    reports = Path(config["paths"]["reports_figures"]).parent
    df = load_model_data(config)
    n_periods = int(df["period"].max()) + 1
    models = ["A baseline", "B ridge", "C boosting"]

    # 1) Model comparison on every fold (last fold = main)
    rows, main_test = [], None
    for train_years, test_year in config["models"]["folds"]:
        test, alpha, n_train = run_fold(df, train_years, test_year, ALL_FEATURES, config, n_periods)
        print(f"Fold train {train_years} -> test {test_year}: {n_train} training rows, {len(test)} test rows, "
              f"ridge alpha {alpha}")
        for name in models:
            rows.append({"test year": test_year, "model": name,
                         **scores(test["anomaly"], test[name].to_numpy(), test["ndvi"])})
        main_test = test
    comparison = pd.DataFrame(rows)
    comparison.round(4).to_csv(reports / "model_comparison.csv", index=False)
    print("\nModel comparison (errors of predicted NDVI on the held-out year):")
    print(comparison.round(4).to_string(index=False))

    # 2) Ablation on the main fold: add input groups one at a time
    train_years, test_year = config["models"]["folds"][-1]
    ablation, cols = [], []
    for group, group_cols in FEATURE_GROUPS.items():
        cols = cols + group_cols
        test, _, _ = run_fold(df, train_years, test_year, cols, config, n_periods)
        for name in models[1:]:
            ablation.append({"inputs": "+ " + group if ablation else group, "model": name,
                             **scores(test["anomaly"], test[name].to_numpy(), test["ndvi"])})
    ablation = pd.DataFrame(ablation)
    ablation.round(4).to_csv(reports / "model_ablation.csv", index=False)
    print(f"\nAblation on test year {test_year} (inputs added cumulatively):")
    print(ablation[["inputs", "model", "MAE", "RMSE", "R2 anomaly"]].round(4).to_string(index=False))

    # 3) Where in the season do the models help? MAE per period, main fold
    by_period = main_test.groupby("period").apply(
        lambda g: pd.Series({m: np.abs(g[m] - g["anomaly"]).mean() for m in models}))
    starts = df.groupby("period")["period_start"].first().str[5:]
    fig, ax = plt.subplots(figsize=(8, 4))
    for name in models:
        ax.plot(by_period.index, by_period[name], marker="o", ms=3, label=name)
    ax.set_xticks(by_period.index, starts.values, rotation=60, fontsize=8)
    ax.set_ylabel("MAE of predicted NDVI")
    ax.set_title(f"Error per 14-day period, test year {test_year} (trained on {train_years[0]}–{train_years[-1]})",
                 fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(Path(config["paths"]["reports_figures"]) / "model_mae_by_period.png", dpi=150)
    print("\nMAE per period, main fold:")
    print(by_period.round(3).set_axis(starts.values).to_string())
    print(f"\nSaved {reports}/model_comparison.csv, model_ablation.csv, figures/model_mae_by_period.png")


if __name__ == "__main__":
    main()
