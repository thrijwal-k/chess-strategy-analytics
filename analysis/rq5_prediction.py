"""RQ5: predicting the result before the game and during it (material, engine evaluation, clock times).

Train on September and October 2020, test on November 2020. Clock times come from data/clocks (made by
scripts/extract_clocks.py); the clock models are skipped if that folder is missing.
"""
import gc

import numpy as np
import pandas as pd
from common import MONTHS, TABLES, TEST_MONTH, WORK, load_month, path, rps
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, log_loss

RNG = np.random.default_rng(0)


def score(name: str, P: np.ndarray, y: np.ndarray, **extra) -> dict:
    return {"model": name, **extra, "test_games": len(y), "log_loss": log_loss(y, P, labels=[0, 1, 2]),
            "rps": rps(P, y), "accuracy": accuracy_score(y, P.argmax(1))}


def hgb(cat: list[int]) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(max_iter=300, categorical_features=cat or None, random_state=0,
                                          early_stopping=True)


# ---- before the game --------------------------------------------------------------------------------------------
d = pd.read_parquet(WORK / "core.parquet", columns=["month", "speed", "band", "dbin", "rating_diff", "white_elo",
                                                    "black_elo", "result", "white_setup", "black_setup"])
d["y"] = d.result.map({0.0: 0, 0.5: 1, 1.0: 2}).astype("int8")
d["mean_elo"] = (d.white_elo.astype("float32") + d.black_elo.astype("float32")) / 2
train, test = d[d.month.astype(str) != TEST_MONTH], d[d.month.astype(str) == TEST_MONTH]
tr = train.iloc[RNG.choice(len(train), 1_500_000, replace=False)]
te = test.iloc[RNG.choice(len(test), 500_000, replace=False)]
y = te.y.values
rows = []
p0 = np.bincount(train.y, minlength=3) / len(train)
rows.append(score("No information (overall result rates)", np.tile(p0, (len(te), 1)), y))
keys = ["speed", "band", "dbin"]
tab = train.groupby(keys, observed=True).y.value_counts(normalize=True).unstack(fill_value=0)
tab = tab.reindex(columns=[0, 1, 2], fill_value=0).reset_index()
P = te[keys].merge(tab, on=keys, how="left")[[0, 1, 2]].fillna(pd.Series(p0, index=[0, 1, 2])).values
rows.append(score("Ratings only (rating-gap table)", P, y))


def pre_feats(x: pd.DataFrame, openings: bool) -> pd.DataFrame:
    f = pd.DataFrame({"diff": x.rating_diff.values, "mean": x.mean_elo.values, "speed": x.speed.cat.codes.values})
    if openings:
        f["ws"], f["bs"] = x.white_setup.cat.codes.values, x.black_setup.cat.codes.values
    return f


best = None
for openings, name in [(False, "Gradient boosting: ratings and speed"),
                       (True, "Gradient boosting: + White system and Black defence")]:
    m = hgb([2, 3, 4] if openings else [2]).fit(pre_feats(tr, openings), tr.y)
    best = m.predict_proba(pre_feats(te, openings))
    rows.append(score(name, best, y))
pre = pd.DataFrame(rows)
pre.to_csv(TABLES / "pregame.csv", index=False)
print(pre.round(4).to_string(index=False))
bins = np.linspace(0, 1, 11)
cal = pd.DataFrame({"p": best[:, 2], "w": y == 2}).groupby(pd.cut(best[:, 2], bins), observed=True)
cal.agg(pred=("p", "mean"), obs=("w", "mean"), n=("w", "size")).to_csv(TABLES / "calibration.csv")
del d, train, test, tr, te
gc.collect()

# ---- during the game ----------------------------------------------------------------------------------------------
SNAP = (15, 20, 25)
have_clocks = all(path("clocks", m).exists() for m in MONTHS)
parts = []
for month in MONTHS:
    cols = ["game_id", "speed", "result", "plies", "white_elo", "black_elo", "has_eval", "time_control"]
    cols += [f"eval_m{m}" for m in SNAP] + [f"{s}_material_m{m}" for s in "wb" for m in SNAP]
    x = load_month(month, cols)
    if have_clocks:
        x = x.merge(pd.read_parquet(path("clocks", month)), on="game_id", how="left")
    tc = x.time_control.astype(str).str.split("+", expand=True)
    base = pd.to_numeric(tc[0], errors="coerce").astype("float32")
    # keep only what the models use, as float32, to stay within memory on 10 million games
    c = pd.DataFrame({"month": month, "y": x.result.map({0.0: 0, 0.5: 1, 1.0: 2}).astype("int8").values,
                      "plies": x.plies.values, "has_eval": x.has_eval.values, "speed": x.speed.astype(str).values,
                      "diff": (x.white_elo.astype("float32") - x.black_elo.astype("float32")).values,
                      "mean": ((x.white_elo.astype("float32") + x.black_elo.astype("float32")) / 2).values,
                      "base": base.values, "inc": pd.to_numeric(tc[1], errors="coerce").astype("float32").values})
    for m in SNAP:
        c[f"mat{m}"] = (x[f"w_material_m{m}"].astype("float32") - x[f"b_material_m{m}"].astype("float32")).values
        c[f"ev{m}"] = x[f"eval_m{m}"].astype("float32").clip(-10, 10).values
        if have_clocks:
            c[f"wclk{m}"] = (x[f"w_clock_m{m}"].astype("float32") / base).values
            c[f"bclk{m}"] = (x[f"b_clock_m{m}"].astype("float32") / base).values
    parts.append(c)
    del x, tc
    gc.collect()
d = pd.concat(parts, ignore_index=True)
del parts
d["speed"] = d.speed.astype("category")
d["spd"] = d.speed.cat.codes
print(f"games: {len(d):,}; with engine analysis: {int(d.has_eval.sum()):,}; clock data: {have_clocks}")


def snapshot(m: int) -> pd.DataFrame:
    x = d.loc[d.plies >= 2 * m + 1, ["month", "y", "has_eval", "speed", "spd", "diff", "mean", "base", "inc"]].copy()
    x["mat"], x["ev"] = d.loc[x.index, f"mat{m}"], d.loc[x.index, f"ev{m}"]
    if have_clocks:
        x["wclk"], x["bclk"] = d.loc[x.index, f"wclk{m}"], d.loc[x.index, f"bclk{m}"]
        x["clk_diff"] = x.wclk - x.bclk
    return x


rows = []
for m in SNAP:
    x = snapshot(m)
    base = ["diff", "mean", "spd"]
    sets = [("ratings and speed", base), ("+ material", base + ["mat"])]
    if have_clocks:
        sets.append(("+ material + clocks", base + ["mat", "wclk", "bclk", "clk_diff", "base", "inc"]))
    # all games (most have no engine analysis)
    allg = x.dropna(subset=["mat"])
    tr_all = allg[allg.month != TEST_MONTH]
    tr_all = tr_all.iloc[RNG.choice(len(tr_all), min(1_500_000, len(tr_all)), replace=False)]
    te_all = allg[allg.month == TEST_MONTH]
    te_all = te_all.iloc[RNG.choice(len(te_all), min(500_000, len(te_all)), replace=False)]
    for name, f in sets:
        P = hgb([2]).fit(tr_all[f], tr_all.y).predict_proba(te_all[f])
        rows.append(score(name, P, te_all.y.values, games="all games", after_move=m))
    # games with engine analysis
    ev = x[x.has_eval].dropna(subset=["ev"])
    tr_ev, te_ev = ev[ev.month != TEST_MONTH], ev[ev.month == TEST_MONTH]
    ev_sets = sets + [("+ material + engine evaluation", base + ["mat", "ev"])]
    if have_clocks:
        ev_sets.append(("+ material + engine evaluation + clocks",
                        base + ["mat", "ev", "wclk", "bclk", "clk_diff", "base", "inc"]))
    for name, f in ev_sets:
        P = hgb([2]).fit(tr_ev[f], tr_ev.y).predict_proba(te_ev[f])
        rows.append(score(name, P, te_ev.y.values, games="engine-analysed games", after_move=m))
    print(f"move {m} done", flush=True)
    del x, allg, ev
    gc.collect()
ing = pd.DataFrame(rows)
ing.to_csv(TABLES / "ingame.csv", index=False)
print(ing.round(4).to_string(index=False))

# clocks matter most in fast games: accuracy by speed at move 20 (all games)
if have_clocks:
    x = snapshot(20).dropna(subset=["mat"])
    tr = x[x.month != TEST_MONTH]
    tr = tr.iloc[RNG.choice(len(tr), min(1_500_000, len(tr)), replace=False)]
    te = x[x.month == TEST_MONTH]
    rows = []
    for name, f in [("+ material", ["diff", "mean", "spd", "mat"]),
                    ("+ material + clocks", ["diff", "mean", "spd", "mat", "wclk", "bclk", "clk_diff", "base", "inc"])]:
        mdl = hgb([2]).fit(tr[f], tr.y)
        for sp, g in te.groupby("speed", observed=True):
            rows.append(score(name, mdl.predict_proba(g[f]), g.y.values, speed=sp, after_move=20))
    by_speed = pd.DataFrame(rows)
    by_speed.to_csv(TABLES / "ingame_clocks_by_speed.csv", index=False)
    print(by_speed.round(4).to_string(index=False))
