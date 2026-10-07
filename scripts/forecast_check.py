"""Check the opening-share forecasts against what actually happened, month by month.

    python scripts/forecast_check.py make     # forecast the next 12 months from docs/tables/trends.csv
    python scripts/forecast_check.py check    # fetch the newest months from Lichess and compare (needs LICHESS_TOKEN)

`make` fits the same ARIMA model as the backtests in analysis/rq4_trends.py to each of the 12 openings (share of
all rated games, 2016 onwards) and writes docs/tables/forecasts.csv with 95% intervals. `check` downloads the
months after the forecast origin from the Lichess opening explorer, and reports for every month and opening
whether the real share fell inside the interval, the forecast error, and the error of a naive forecast (the last
known share repeated) for comparison. The scheduled GitHub workflow .github/workflows/forecast-check.yml runs
`check` every month.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chessanalytics.explorer import POSITIONS, RATING_GROUPS, Explorer, to_uci, token_from_env  # noqa: E402

TRENDS = ROOT / "docs" / "tables" / "trends.csv"
FORECASTS = ROOT / "docs" / "tables" / "forecasts.csv"
OPENINGS = ["1.e4", "1.d4", "Sicilian", "French", "Caro-Kann", "Scandinavian", "Italian", "Ruy Lopez",
            "Queen's Gambit", "London vs 1...d5", "King's Indian", "King's Gambit"]
HORIZON = 12


def arima_interval(y: np.ndarray, h: int, m: int = 12) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    from statsmodels.tsa.arima.model import ARIMA

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = ARIMA(y, order=(1, 1, 1), seasonal_order=(1, 0, 0, m)).fit()
    f = fit.get_forecast(h)
    ci = np.asarray(f.conf_int(alpha=0.05))
    return np.asarray(f.predicted_mean), ci[:, 0], ci[:, 1]


def make(trends: Path = TRENDS, out: Path = FORECASTS) -> pd.DataFrame:
    d = pd.read_csv(trends)
    d = d[(d.group == "all") & (d.month >= "2016-01")]
    rows = []
    for p in OPENINGS:
        s = d[d.position == p].sort_values("month")
        origin = pd.Period(s.month.iloc[-1], freq="M")
        mean, lo, hi = arima_interval(s.share.values * 100, HORIZON)
        for h in range(HORIZON):
            rows.append({"position": p, "origin": str(origin), "month": str(origin + h + 1), "h": h + 1,
                         "last_share": s.share.iloc[-1] * 100, "forecast": mean[h], "lo95": lo[h], "hi95": hi[h]})
    f = pd.DataFrame(rows)
    f.to_csv(out, index=False, float_format="%.4f")
    print(f"{len(f)} forecasts from {f.origin.iloc[0]} -> {out}")
    return f


def compare(forecasts: pd.DataFrame, actual: pd.DataFrame) -> pd.DataFrame:
    """actual: position, month, share (%). One row per forecast that now has a real value."""
    c = forecasts.merge(actual, on=["position", "month"], how="inner")
    c["error"] = c.share - c.forecast
    c["naive_error"] = c.share - c.last_share
    c["inside"] = (c.share >= c.lo95) & (c.share <= c.hi95)
    return c


def report(c: pd.DataFrame) -> str:
    if c.empty:
        return ("### Forecast check\n\nNo months after the forecast origin are available from the Lichess opening "
                "explorer yet (it runs a few months behind). The check will run again next month.")
    months = sorted(c.month.unique())
    lines = ["### Forecast check", "",
             f"Forecasts made from data up to {c.origin.iloc[0]}; real values now available for "
             f"{months[0]} to {months[-1]} ({len(months)} months, {len(c)} opening-months).", "",
             f"- Inside the 95% interval: {c.inside.mean():.0%} (about 95% expected).",
             f"- Mean absolute error: {c.error.abs().mean():.3f} percentage points of share; repeating the last "
             f"known share: {c.naive_error.abs().mean():.3f}.", "",
             "| Opening | Month | Forecast (%) | 95% interval | Actual (%) | Inside |", "|---|---|---|---|---|---|"]
    latest = c[c.month == months[-1]]
    lines += [f"| {r.position} | {r.month} | {r.forecast:.2f} | {r.lo95:.2f} to {r.hi95:.2f} | {r.share:.2f} | "
              f"{'yes' if r.inside else '**no**'} |" for r in latest.itertuples()]
    return "\n".join(lines)


def fetch_actual(ex: Explorer, since: str, until: str) -> pd.DataFrame:
    sans = dict(POSITIONS)
    rows = []
    for label in ["Start position", *OPENINGS]:
        for r in ex.history(to_uci(sans[label]), RATING_GROUPS["all"], since, until):
            rows.append({"position": label, "month": r["month"], "games": r["white"] + r["draws"] + r["black"]})
    a = pd.DataFrame(rows, columns=["position", "month", "games"])
    if a.empty:  # the explorer runs a few months behind, so there may be nothing after the forecast origin yet
        return pd.DataFrame(columns=["position", "month", "share"])
    total = a[a.position == "Start position"].set_index("month").games
    a = a[(a.position != "Start position") & a.month.isin(total[total > 0].index)]
    return a.assign(share=lambda x: x.games / x.month.map(total) * 100)[["position", "month", "share"]]


def check(out: Path, summary: Path | None) -> int:
    f = pd.read_csv(FORECASTS)
    since = str(pd.Period(f.origin.iloc[0], freq="M") + 1)
    until = str(pd.Timestamp.today().to_period("M"))
    with tempfile.TemporaryDirectory() as cache:
        ex = Explorer(token=token_from_env(), cache_dir=Path(cache))
        actual = fetch_actual(ex, since, until)
    c = compare(f, actual)
    c.to_csv(out, index=False, float_format="%.4f")
    text = report(c)
    print(text)
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["make", "check"])
    ap.add_argument("--out", type=Path, default=Path("forecast_check.csv"))
    ap.add_argument("--summary", type=Path, help="append the Markdown report here (e.g. $GITHUB_STEP_SUMMARY)")
    a = ap.parse_args()
    if a.command == "make":
        make()
        return 0
    return check(a.out, a.summary)


if __name__ == "__main__":
    raise SystemExit(main())
