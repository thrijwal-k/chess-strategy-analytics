"""Time-series methods checked on synthetic series where the right answer is known."""
import numpy as np
import pandas as pd
import pytest

from chessanalytics import timeseries as ts


def monthly(values, start="2013-01"):
    return pd.Series(values, index=pd.period_range(start, periods=len(values), freq="M"))


def synthetic(n=120, jump_at=None, jump=0.0, slope=0.0002, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    y = 0.05 + slope * t + 0.004 * np.sin(2 * np.pi * t / 12) + rng.normal(0, 0.001, n)
    if jump_at is not None:
        y[jump_at:] += jump
    return monthly(y)


def test_load_history_computes_share_and_score(tmp_path):
    rows = []
    for m in ["2020-10", "2020-11"]:
        rows.append(["Start position", "", "all", m, 500, 100, 400])
        rows.append(["Queen's Gambit", "d4 d5 c4", "all", m, 30, 10, 10])
    p = tmp_path / "h.csv"
    cols = ["position", "moves", "group", "month", "white", "draws", "black"]
    pd.DataFrame(rows, columns=cols).to_csv(p, index=False)
    d = ts.load_history(p)
    qg = ts.series(d, "Queen's Gambit")
    assert qg.iloc[0] == pytest.approx(50 / 1000)
    assert ts.series(d, "Queen's Gambit", value="white_score").iloc[0] == pytest.approx(35 / 50)


def test_metrics():
    assert ts.smape(np.array([1.0, 1.0]), np.array([1.0, 1.0])) == 0
    train = monthly(np.arange(36.0))  # seasonal naive in-sample error is 12 every month
    assert ts.mase(np.arange(12.0), np.arange(12.0), train) == 0
    assert ts.mase(np.arange(12.0), np.arange(12.0) + 6, train) == pytest.approx(0.5)


def test_seasonal_naive_repeats_last_year():
    s = monthly(np.arange(24.0))
    assert list(ts.seasonal_naive(s, 3)) == [12.0, 13.0, 14.0]


def test_ets_beats_seasonal_naive_on_trend_plus_season():
    s = synthetic(n=96, slope=0.001)
    bt = ts.backtest(s, horizon=12, min_train=48, step=12, models={"seasonal naive": ts.seasonal_naive, "ETS": ts.ets})
    means = bt.groupby("model").mase.mean()
    assert means["ETS"] < means["seasonal naive"]


def test_change_point_found_at_the_jump():
    s = synthetic(n=120, jump_at=94, jump=0.02, slope=0.0)
    cps = ts.change_points(s)
    assert any(abs((pd.Period(c, "M") - s.index[94]).n) <= 1 for c in cps)


def test_no_change_point_in_pure_noise():
    rng = np.random.default_rng(3)
    assert ts.change_points(monthly(0.05 + rng.normal(0, 0.001, 120))) == []


def test_interrupted_time_series_recovers_level_change():
    s = synthetic(n=120, jump_at=94, jump=0.01, slope=0.0001)
    r = ts.interrupted_time_series(s, str(s.index[94]))
    assert r.level_change == pytest.approx(0.01, abs=0.002)
    assert r.level_ci < 0.005 and abs(r.slope_change) < 0.0005


def test_interrupted_time_series_finds_nothing_when_nothing_happened():
    s = synthetic(n=120, slope=0.0001, seed=5)
    r = ts.interrupted_time_series(s, str(s.index[94]))
    assert abs(r.level_change) < r.level_ci + 0.001
