"""The monthly forecast check: forecasts, the comparison with real months, and the report (no network needed)."""
import importlib.util
from pathlib import Path

import pandas as pd

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "forecast_check.py"
spec = importlib.util.spec_from_file_location("forecast_check", SCRIPT)
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)


def test_saved_forecasts_are_sensible():
    f = pd.read_csv(fc.FORECASTS)
    assert set(f.position) == set(fc.OPENINGS) and len(f) == 12 * fc.HORIZON
    assert ((f.lo95 <= f.forecast) & (f.forecast <= f.hi95)).all()
    width = (f.hi95 - f.lo95).groupby([f.position, f.h]).mean().unstack()
    assert (width[12] > width[1]).all()  # further ahead, less certain
    assert (f.origin == f.origin.iloc[0]).all()


def test_make_reproduces_the_saved_forecasts(tmp_path):
    out = tmp_path / "forecasts.csv"
    new = fc.make(out=out)
    old = pd.read_csv(fc.FORECASTS)
    # the ARIMA optimiser lands on slightly different values across library versions (about 0.002 points seen)
    assert (new.forecast - old.forecast).abs().max() < 0.02


def _forecasts():
    return pd.DataFrame({"position": ["1.e4", "1.e4"], "origin": "2026-05", "month": ["2026-06", "2026-07"],
                         "h": [1, 2], "last_share": 58.0, "forecast": [58.2, 58.2], "lo95": [57.7, 57.5],
                         "hi95": [58.7, 58.9]})


def test_compare_and_report():
    actual = pd.DataFrame({"position": ["1.e4", "1.e4"], "month": ["2026-06", "2026-07"], "share": [58.5, 59.5]})
    c = fc.compare(_forecasts(), actual)
    assert c.inside.tolist() == [True, False]
    assert c.error.round(2).tolist() == [0.3, 1.3] and c.naive_error.round(2).tolist() == [0.5, 1.5]
    text = fc.report(c)
    assert "Inside the 95% interval: 50%" in text and "| 1.e4 | 2026-07 |" in text and "**no**" in text
    assert "No months" in fc.report(fc.compare(_forecasts(), actual.iloc[:0]))


class FakeExplorer:
    def history(self, play, ratings, since, until):
        games = {"": 1000, "e2e4": 580}.get(play, 10)
        return [{"month": m, "white": games, "draws": 0, "black": 0} for m in ("2026-06", "2026-07")]


def test_fetch_actual_turns_counts_into_shares():
    a = fc.fetch_actual(FakeExplorer(), "2026-06", "2026-07")
    e4 = a[a.position == "1.e4"]
    assert e4.share.round(6).tolist() == [58.0, 58.0] and "Start position" not in set(a.position)
