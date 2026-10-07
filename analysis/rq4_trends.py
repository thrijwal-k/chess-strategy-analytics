"""RQ4: opening trends 2013-2026 from data/explorer/history.csv (scripts/fetch_explorer.py)."""
import sys
import warnings

import numpy as np
import pandas as pd
import ruptures as rpt
from common import DATA, TABLES

sys.path.insert(0, "src")
from chessanalytics import timeseries as ts  # noqa: E402

warnings.filterwarnings("ignore")
d = ts.load_history(DATA / "explorer" / "history.csv")
QG = "Queen's Gambit"

# compact monthly table for the dashboard
trends = d[["position", "group", "month", "games", "white", "draws", "black", "share", "white_score"]].copy()
trends["month"] = trends.month.astype(str)
trends.to_csv(TABLES / "trends.csv", index=False, float_format="%.6g")

# one-month change around the Netflix release, with the same change in every other year as a placebo
rows = []
for g in ["all", "under_1600", "1600_1999", "2000_plus"]:
    s = ts.series(d, QG, g) * 100
    sd = s["2016":].diff().std()
    for y in range(2016, 2026):
        ch = s[f"{y}-11"] - s[f"{y}-10"]
        rows.append({"group": g, "year": y, "oct": s[f"{y}-10"], "nov": s[f"{y}-11"], "change_pp": ch,
                     "change_in_sd": ch / sd})
oct_nov = pd.DataFrame(rows)
oct_nov.to_csv(TABLES / "qg_oct_nov.csv", index=False)
print(oct_nov[oct_nov.year == 2020].round(3).to_string(index=False))

# interrupted time series: Netflix and placebo Novembers on the QG share, lockdown on log games per month
rows = []
qg = ts.series(d, QG) * 100
for event, excl in [("2020-11", ("2020-10",))] + [(f"{y}-11", ()) for y in (2017, 2018, 2019, 2021, 2022, 2023)]:
    r = ts.interrupted_time_series(qg, event, window=24, exclude=excl)
    rows.append(("QG share", event, r.level_change, r.level_ci, r.slope_change, r.slope_ci))
for g in ["under_1600", "1600_1999", "2000_plus"]:
    r = ts.interrupted_time_series(ts.series(d, QG, g) * 100, "2020-11", window=24, exclude=("2020-10",))
    rows.append((f"QG share ({g})", "2020-11", r.level_change, r.level_ci, r.slope_change, r.slope_ci))
r = ts.interrupted_time_series(np.log(ts.series(d, "Start position", value="games")), "2020-03", window=24)
rows.append(("log games per month", "2020-03", r.level_change, r.level_ci, r.slope_change, r.slope_ci))
its = pd.DataFrame(rows, columns=["series", "event", "level", "level_ci", "slope", "slope_ci"])
its.to_csv(TABLES / "its.csv", index=False)
print(its.round(3).to_string(index=False))

# long-run shares and the two largest breaks per opening (2016 onwards)
rows = []
for p in [QG, "London vs 1...d5", "London vs 1...Nf6", "Caro-Kann", "Sicilian", "King's Gambit", "Scandinavian",
          "Italian", "French", "1.e4", "1.d4"]:
    s = (ts.series(d, p) * 100)["2016-01":]
    b = rpt.Binseg(model="l2", min_size=6).fit(s.values.reshape(-1, 1)).predict(n_bkps=2)
    rows.append({"position": p, "share_2016_01": s.iloc[0], "share_last": s.iloc[-1], "last_month": str(s.index[-1]),
                 "break1": str(s.index[b[0]]), "break2": str(s.index[b[1]])})
pd.DataFrame(rows).to_csv(TABLES / "breaks_top2.csv", index=False)
print(pd.DataFrame(rows).round(2).to_string(index=False))

# forecasting backtests
positions = ["1.e4", "1.d4", "Sicilian", "French", "Caro-Kann", "Scandinavian", "Italian", "Ruy Lopez", QG,
             "London vs 1...d5", "King's Indian", "King's Gambit"]
bt = pd.concat([ts.backtest((ts.series(d, p) * 100)["2016-01":]).assign(position=p) for p in positions])
bt.to_csv(TABLES / "backtests.csv", index=False)
print(bt.groupby("model")[["mase", "smape"]].agg(["mean", "median"]).round(3))
w = bt.groupby(["position", "model"]).mase.mean().unstack()
print("best model per opening:", w.idxmin(axis=1).value_counts().to_dict())
