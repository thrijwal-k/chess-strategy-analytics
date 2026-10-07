"""Shared paths, loading, filters, the rating baseline and plot style for the analysis scripts.

Inputs live under the data directory (default ./data, or the CHESS_DATA environment variable):
features/features_<m>.parquet, setups/setups_<m>.parquet, endgames/endgames_<m>.parquet, clocks/clocks_<m>.parquet,
explorer/history.csv. Tables are written to docs/tables and figures to docs/figures.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(os.environ.get("CHESS_DATA", "data"))
WORK = Path(os.environ.get("CHESS_WORK", "results"))  # intermediate tables (not committed)
TABLES = Path("docs/tables")
FIGURES = Path("docs/figures")
MONTHS = ["2020-09", "2020-10", "2020-11"]
TEST_MONTH = "2020-11"
SPEEDS = ["bullet", "blitz", "rapid", "classical"]
BAND_EDGES = [0, 1200, 1400, 1600, 1800, 2000, 2200, 3500]
BAND_LABELS = ["<1200", "1200-1399", "1400-1599", "1600-1799", "1800-1999", "2000-2199", "2200+"]
FILTER_COLS = ["rated", "speed", "result", "termination", "plies", "white_elo", "black_elo"]

for p in (WORK, TABLES, FIGURES):
    p.mkdir(parents=True, exist_ok=True)


def path(kind: str, month: str) -> Path:
    return DATA / kind / f"{kind}_{month}.parquet"


def keep(d: pd.DataFrame) -> pd.Series:
    """Rated bullet/blitz/rapid/classical games that finished normally or on time, at least 5 moves, both rated."""
    return (d.rated & d.speed.isin(SPEEDS) & d.result.notna() & d.termination.isin(["Normal", "Time forfeit"])
            & (d.plies >= 10) & d.white_elo.notna() & d.black_elo.notna())


def compact(d: pd.DataFrame) -> pd.DataFrame:
    for c in d.columns:
        if d[c].dtype == object:
            d[c] = d[c].astype("category")
        elif d[c].dtype == "float64":
            d[c] = d[c].astype("float32")
        elif d[c].dtype == "int64":
            d[c] = d[c].astype("int32")
    return d


def load_month(month: str, cols: list[str]) -> pd.DataFrame:
    """Selected feature columns for one month, filtered, with compact dtypes."""
    need = list(dict.fromkeys(cols + FILTER_COLS))
    d = pd.read_parquet(path("features", month), columns=need)
    d = d[keep(d)].drop(columns=[c for c in FILTER_COLS if c not in cols])
    return compact(d.reset_index(drop=True))


def add_rating_cells(d: pd.DataFrame) -> pd.DataFrame:
    diff = d.white_elo.astype("float32") - d.black_elo.astype("float32")
    mean = (d.white_elo.astype("float32") + d.black_elo.astype("float32")) / 2
    d["rating_diff"] = diff
    d["band"] = pd.cut(mean, BAND_EDGES, labels=BAND_LABELS, right=False)
    d["dbin"] = np.clip((diff / 25).round(), -24, 24).astype("int8")
    return d


def add_baseline(d: pd.DataFrame) -> pd.DataFrame:
    """Expected White score = mean result in the same speed, 200-point rating band and 25-point rating-gap bin."""
    d = add_rating_cells(d)
    d["expected"] = d.groupby(["speed", "band", "dbin"], observed=True).result.transform("mean").astype("float32")
    d["excess"] = (d.result - d.expected).astype("float32")
    return d


def summarise(d: pd.DataFrame, by, min_n: int = 1000) -> pd.DataFrame:
    """Games, share, White score, expected score, edge (excess) with 95% CI, and draw rate per group."""
    g = d.groupby(by, observed=True)
    t = pd.DataFrame({"games": g.size(), "white_score": g.result.mean(), "expected": g.expected.mean(),
                      "excess": g.excess.mean(), "sd": g.excess.std(),
                      "draw_rate": g.result.agg(lambda s: (s == 0.5).mean())})
    t["ci95"] = 1.96 * t.sd / np.sqrt(t.games)
    t["share"] = t.games / len(d)
    return t[t.games >= min_n].drop(columns="sd")


def rps(P: np.ndarray, y: np.ndarray) -> float:
    """Ranked probability score for ordered outcomes (Black win < draw < White win)."""
    Y = np.eye(3)[y]
    return float(np.mean(np.sum((np.cumsum(P, 1) - np.cumsum(Y, 1))[:, :2] ** 2, 1) / 2))


# plot style: categorical slots from the validated reference palette, in fixed order (lines use direct labels)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def plot_style() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                         "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
                         "axes.spines.right": False, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                         "savefig.dpi": 200})
