"""Phase 4: results against a rating baseline.

Every opening, middlegame and endgame effect is reported as **score above expectation**: White's actual score
minus the score the rating gap predicts. The baseline is the Elo expected score with a fitted White advantage
(in rating points) per time control, so an opening only looks good if it beats what the ratings already say.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize

ANALYSIS_SPEEDS = ["bullet", "blitz", "rapid", "classical"]
RATING_BANDS = [0, 1200, 1500, 1800, 2100, 4000]
BAND_LABELS = ["<1200", "1200-1499", "1500-1799", "1800-2099", "2100+"]


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Rated standard games at normal speeds that actually started and finished."""
    keep = (
        df["speed"].isin(ANALYSIS_SPEEDS)
        & df["result"].notna()
        & (df["plies"] >= 2)
        & ~df["termination"].isin(["Abandoned", "Unterminated", "Rules infraction"])
        & df["rated"]
    )
    out = df.loc[keep].copy()
    out["band"] = pd.cut(out["mean_elo"], RATING_BANDS, labels=BAND_LABELS, right=False)
    return out


def elo_expected(diff: np.ndarray, white_adv: float, scale: float = 400.0) -> np.ndarray:
    return 1.0 / (1.0 + 10.0 ** (-(diff + white_adv) / scale))


def fit_elo(diff: np.ndarray, score: np.ndarray) -> tuple[float, float]:
    """(White advantage in rating points, scale) minimising squared error between the Elo curve and the score.

    Classical Elo uses a scale of 400. On Lichess (Glicko-2 ratings) a fixed 400 is overconfident: big rating
    gaps win less often than it predicts, so the scale is fitted rather than assumed.
    """
    def loss(p: np.ndarray) -> float:
        return float(np.mean((score - elo_expected(diff, p[0], p[1])) ** 2))

    res = minimize(loss, x0=np.array([10.0, 400.0]), method="Nelder-Mead", options={"xatol": 0.01, "fatol": 1e-10})
    return float(res.x[0]), float(res.x[1])


@dataclass
class Baseline:
    params: dict[str, tuple[float, float]]  # speed -> (white advantage, scale)

    def expected(self, df: pd.DataFrame) -> np.ndarray:
        h = df["speed"].map({k: v[0] for k, v in self.params.items()}).to_numpy(dtype=float)
        s = df["speed"].map({k: v[1] for k, v in self.params.items()}).to_numpy(dtype=float)
        return elo_expected(df["rating_diff"].to_numpy(dtype=float), h, s)


def fit_baseline(df: pd.DataFrame) -> Baseline:
    return Baseline({str(s): fit_elo(g["rating_diff"].to_numpy(float), g["result"].to_numpy(float))
                     for s, g in df.groupby("speed", observed=True)})


def excess_table(df: pd.DataFrame, by: str | list[str], min_games: int = 1000) -> pd.DataFrame:
    """Per group: games, White score, expected score, excess (actual - expected) with a 95% interval,
    draw rate. df needs columns result and expected."""
    d = df.assign(excess=df["result"] - df["expected"], draw=(df["result"] == 0.5).astype(float))
    g = d.groupby(by, observed=True)
    t = pd.DataFrame({
        "games": g.size(),
        "score": g["result"].mean(),
        "expected": g["expected"].mean(),
        "excess": g["excess"].mean(),
        "se": g["excess"].std() / np.sqrt(g.size()),
        "draw_rate": g["draw"].mean(),
        "mean_elo": g["mean_elo"].mean(),
    })
    t = t[t["games"] >= min_games]
    t["ci_low"], t["ci_high"] = t["excess"] - 1.96 * t["se"], t["excess"] + 1.96 * t["se"]
    t["share"] = t["games"] / len(df)
    return t.sort_values("games", ascending=False)
