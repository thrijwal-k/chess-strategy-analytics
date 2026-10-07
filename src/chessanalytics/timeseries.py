"""RQ4: monthly opening popularity and results, 2013-2026.

- share: games reaching the position / all games that month (same rating group), so it is comparable over time
  even though Lichess grew from thousands to tens of millions of games a month;
- White score: (White wins + half the draws) / games;
- STL decomposition (trend + yearly seasonality + remainder);
- forecasting with rolling-origin backtests (train up to month t, forecast the next 1-12 months, move t forward):
  seasonal naive, exponential smoothing (ETS) and ARIMA, scored with MASE and sMAPE;
- structural breaks: PELT change-point detection, and an interrupted time series (segmented regression) for a
  named event, such as Netflix's The Queen's Gambit (released 23 October 2020).
"""
from __future__ import annotations

import warnings
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd


def load_history(path) -> pd.DataFrame:
    """history.csv from scripts/fetch_explorer.py -> one row per position, group and month with share and score."""
    d = pd.read_csv(path, keep_default_na=False)
    d["games"] = d.white + d.draws + d.black
    d["month"] = pd.PeriodIndex(d.month, freq="M")
    start = d[d.position == "Start position"][["group", "month", "games"]].rename(columns={"games": "all_games"})
    d = d.merge(start, on=["group", "month"], how="left")
    d["share"] = np.where(d.all_games > 0, d.games / d.all_games, np.nan)
    d["white_score"] = np.where(d.games > 0, (d.white + 0.5 * d.draws) / d.games, np.nan)
    return d


def series(d: pd.DataFrame, position: str, group: str = "all", value: str = "share",
           min_games: int = 1) -> pd.Series:
    s = d[(d.position == position) & (d.group == group) & (d.games >= min_games)].set_index("month")[value]
    return s.sort_index().astype(float)


# --- forecasting ------------------------------------------------------------------------------------------------

def seasonal_naive(train: pd.Series, h: int, m: int = 12) -> np.ndarray:
    last = train.values[-m:]
    return np.array([last[i % m] for i in range(h)])


def ets(train: pd.Series, h: int, m: int = 12) -> np.ndarray:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        seasonal = "add" if len(train) >= 2 * m else None
        fit = ExponentialSmoothing(train.values, trend="add", damped_trend=True, seasonal=seasonal,
                                   seasonal_periods=m if seasonal else None).fit()
    return np.asarray(fit.forecast(h))


def arima(train: pd.Series, h: int, m: int = 12) -> np.ndarray:
    from statsmodels.tsa.arima.model import ARIMA

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        order = (1, 1, 1)
        seasonal = (1, 0, 0, m) if len(train) >= 2 * m else (0, 0, 0, 0)
        fit = ARIMA(train.values, order=order, seasonal_order=seasonal).fit()
    return np.asarray(fit.forecast(h))


MODELS: dict[str, Callable] = {"seasonal naive": seasonal_naive, "ETS": ets, "ARIMA": arima}


def mase(actual: np.ndarray, forecast: np.ndarray, train: pd.Series, m: int = 12) -> float:
    """Mean absolute scaled error: forecast error relative to the in-sample seasonal naive error."""
    t = train.values
    scale = np.mean(np.abs(t[m:] - t[:-m])) if len(t) > m else np.mean(np.abs(np.diff(t)))
    return float(np.mean(np.abs(actual - forecast)) / scale) if scale > 0 else np.nan


def smape(actual: np.ndarray, forecast: np.ndarray) -> float:
    denom = (np.abs(actual) + np.abs(forecast)) / 2
    ok = denom > 0
    return float(np.mean(np.abs(actual - forecast)[ok] / denom[ok]) * 100)


def backtest(s: pd.Series, horizon: int = 12, min_train: int = 36, step: int = 6,
             models: dict[str, Callable] | None = None) -> pd.DataFrame:
    """Rolling-origin evaluation. Returns one row per model and origin with MASE and sMAPE."""
    models = models or MODELS
    s = s.dropna()
    rows = []
    for end in range(min_train, len(s) - horizon + 1, step):
        train, test = s.iloc[:end], s.iloc[end:end + horizon].values
        for name, fn in models.items():
            try:
                f = fn(train, horizon)
                score = {"mase": mase(test, f, train), "smape": smape(test, f), "failed": False}
            except Exception:  # noqa: BLE001 - a model failing at one origin is recorded as failed, not fatal
                score = {"mase": np.nan, "smape": np.nan, "failed": True}
            rows.append({"model": name, "origin": str(s.index[end - 1]), **score})
    return pd.DataFrame(rows)


# --- structural breaks ------------------------------------------------------------------------------------------

def change_points(s: pd.Series, penalty: float | None = None, min_size: int = 6) -> list[str]:
    """PELT change points in the mean (as the first month of each new segment)."""
    import ruptures as rpt

    x = s.dropna().values.reshape(-1, 1)
    if penalty is None:  # BIC-style penalty scaled by the noise level
        sigma = np.median(np.abs(np.diff(x[:, 0]))) / 0.6745 / np.sqrt(2) or np.std(x)
        penalty = 3 * np.log(len(x)) * sigma ** 2
    bkps = rpt.Pelt(model="l2", min_size=min_size).fit(x).predict(pen=penalty)
    idx = s.dropna().index
    return [str(idx[b]) for b in bkps[:-1]]


@dataclass
class ITSResult:
    event: str
    level_change: float
    level_ci: float
    slope_change: float
    slope_ci: float
    pre_mean: float
    n_pre: int
    n_post: int


def interrupted_time_series(s: pd.Series, event: str, window: int = 24, exclude: tuple[str, ...] = (),
                            seasonal: bool = True) -> ITSResult:
    """Segmented regression: y = a + b*t + c*post + d*(t - t0)*post (+ month-of-year effects), with HAC standard
    errors. `level_change` is c (the jump at the event), `slope_change` is d (per month)."""
    import statsmodels.api as sm

    s = s.dropna()
    t0 = pd.Period(event, freq="M")
    s = s[(s.index >= t0 - window) & (s.index < t0 + window)]
    s = s[~s.index.astype(str).isin(exclude)]
    t = np.array([(p - t0).n for p in s.index], dtype=float)
    post = (t >= 0).astype(float)
    X = pd.DataFrame({"const": 1.0, "t": t, "post": post, "t_post": t * post}, index=s.index)
    if seasonal:
        moy = pd.get_dummies(s.index.month, prefix="m", drop_first=True, dtype=float)
        moy.index = s.index
        X = pd.concat([X, moy], axis=1)
    fit = sm.OLS(s.values, X).fit(cov_type="HAC", cov_kwds={"maxlags": 3})
    ci = 1.96 * fit.bse
    return ITSResult(event, float(fit.params["post"]), float(ci["post"]), float(fit.params["t_post"]),
                     float(ci["t_post"]), float(s[post == 0].mean()), int((post == 0).sum()), int(post.sum()))
