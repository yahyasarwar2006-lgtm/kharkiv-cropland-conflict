"""Stage 7 statistics: spatial blocks, cluster bootstrap, two-way fixed-effects regression with
clustered standard errors, and Moran's I. Kept small and dependency-free (numpy/pandas only)."""

import numpy as np
import pandas as pd


def spatial_blocks(x_km: pd.Series, y_km: pd.Series, block_km: float) -> pd.Series:
    """Label of the block_km x block_km square each point falls in (for clustering)."""
    return (np.floor(x_km / block_km).astype(int).astype(str) + "_"
            + np.floor(y_km / block_km).astype(int).astype(str))


def bootstrap_diff(values: pd.Series, is_high: pd.Series, blocks: pd.Series, reps: int = 1000,
                   seed: int = 0) -> tuple[float, float, float]:
    """Mean(high) - mean(low) and a 95% interval from resampling whole spatial blocks."""
    df = pd.DataFrame({"v": values.to_numpy(), "h": is_high.to_numpy(), "b": blocks.to_numpy()}).dropna()
    diff = df.loc[df["h"], "v"].mean() - df.loc[~df["h"], "v"].mean()
    by_block = {b: g for b, g in df.groupby("b")}
    names = np.array(list(by_block))
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(reps):
        sample = pd.concat([by_block[b] for b in rng.choice(names, len(names))])
        hi, lo = sample.loc[sample["h"], "v"], sample.loc[~sample["h"], "v"]
        if len(hi) and len(lo):
            draws.append(hi.mean() - lo.mean())
    lo95, hi95 = np.percentile(draws, [2.5, 97.5])
    return diff, lo95, hi95


def bootstrap_mean(values: pd.Series, blocks: pd.Series, reps: int = 1000, seed: int = 0) -> tuple:
    """Mean and a 95% interval from resampling whole spatial blocks."""
    df = pd.DataFrame({"v": values.to_numpy(), "b": blocks.to_numpy()}).dropna()
    sums = df.groupby("b")["v"].agg(["sum", "count"])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(sums), size=(reps, len(sums)))
    draws = sums["sum"].to_numpy()[idx].sum(axis=1) / sums["count"].to_numpy()[idx].sum(axis=1)
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return df["v"].mean(), lo, hi


def twfe(y: pd.Series, x: pd.Series, unit: pd.Series, time: pd.Series, cluster: pd.Series,
         tol: float = 1e-10, max_iter: int = 1000) -> dict:
    """y = unit effect + time effect + beta * x. Effects removed by alternating demeaning
    (Frisch-Waugh-Lovell, works for unbalanced panels); standard error clustered by `cluster`."""
    df = pd.DataFrame({"y": y.to_numpy(), "x": x.to_numpy(), "u": unit.to_numpy(), "t": time.to_numpy(),
                       "c": cluster.to_numpy()}).dropna()
    for col in ["y", "x"]:
        v = df[col].astype(float)
        for _ in range(max_iter):
            new = v - v.groupby(df["u"]).transform("mean")
            new = new - new.groupby(df["t"]).transform("mean")
            if np.abs(new - v).max() < tol:
                break
            v = new
        df[col + "_d"] = new
    sxx = (df["x_d"] ** 2).sum()
    beta = (df["x_d"] * df["y_d"]).sum() / sxx
    df["e"] = df["y_d"] - beta * df["x_d"]
    scores = (df["x_d"] * df["e"]).groupby(df["c"]).sum()
    g = len(scores)
    se = np.sqrt(g / (g - 1) * (scores ** 2).sum() / sxx ** 2)
    return {"beta": beta, "se": se, "ci_low": beta - 1.96 * se, "ci_high": beta + 1.96 * se,
            "n": len(df), "clusters": g, "residuals": df["e"].set_axis(df.index)}


def morans_i(values: np.ndarray, x: np.ndarray, y: np.ndarray, max_dist: float, perms: int = 199,
             seed: int = 0) -> tuple[float, float]:
    """Moran's I with neighbours = points within max_dist (row-standardised weights) and a
    one-sided permutation p-value for positive spatial autocorrelation."""
    z = values - values.mean()
    d = np.hypot(x[:, None] - x[None, :], y[:, None] - y[None, :])
    w = ((d > 0) & (d <= max_dist)).astype(float)
    rows = w.sum(axis=1, keepdims=True)
    w = np.divide(w, rows, out=np.zeros_like(w), where=rows > 0)
    stat = lambda v: len(v) * (v @ w @ v) / (w.sum() * (v @ v))
    observed = stat(z)
    rng = np.random.default_rng(seed)
    p = (1 + sum(stat(rng.permutation(z)) >= observed for _ in range(perms))) / (perms + 1)
    return observed, p
