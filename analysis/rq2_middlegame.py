"""RQ2: middlegame features at move 20, and draw rates by castling pattern and queen-trade timing."""
import gc

import numpy as np
import pandas as pd
import statsmodels.api as sm
from common import MONTHS, TABLES, WORK, add_baseline, load_month

K = ["material", "isolated", "doubled", "backward", "passed", "islands", "iqp", "hanging", "bishop_pair", "outposts",
     "rooks_open", "rooks_half_open", "rooks_7th", "pawn_shield", "open_files_near_king", "centre", "space",
     "developed_minors"]
FEATS = [f"d_{k}" for k in K if k != "material"] + ["unc_diff"]


def load(m: int = 20) -> pd.DataFrame:
    parts = []
    for month in MONTHS:
        cols = ["speed", "result", "plies", "white_elo", "black_elo", "has_eval", f"eval_m{m}", f"eval_change_m{m}"]
        cols += [f"{s}_{k}_m{m}" for s in "wb" for k in K + ["king_side"]]
        d = load_month(month, cols)
        d = d[d.plies >= 2 * m + 2]
        out = pd.DataFrame({"speed": d.speed.values, "result": d.result.values, "white_elo": d.white_elo.values,
                            "black_elo": d.black_elo.values, "has_eval": d.has_eval.values,
                            "ev0": d[f"eval_m{m}"].values, "eval_change": d[f"eval_change_m{m}"].values})
        for k in K:
            out[f"d_{k}"] = (d[f"w_{k}_m{m}"].astype("float32") - d[f"b_{k}_m{m}"].astype("float32")).values
        out["unc_diff"] = ((d[f"w_king_side_m{m}"] == "centre").astype("int8")
                           - (d[f"b_king_side_m{m}"] == "centre").astype("int8")).values
        parts.append(out)
        del d
        gc.collect()
    d = pd.concat(parts, ignore_index=True)
    d["speed"] = d.speed.astype("category")
    return add_baseline(d)


def fit(df: pd.DataFrame, y: str, extra: tuple = ()) -> pd.DataFrame:
    X = sm.add_constant(df[FEATS + list(extra)].astype("float64"))
    r = sm.OLS(df[y].astype("float64"), X).fit(cov_type="HC1")
    return pd.DataFrame({"coef": r.params, "ci95": 1.96 * r.bse, "p": r.pvalues}).drop("const")


d = load(20)
bal = d[d.d_material == 0]
print(f"games lasting past move 20: {len(d):,}; with equal material: {len(bal):,}")
a = fit(bal, "excess")
a["coef_pp"], a["ci_pp"], a["per_sd_pp"] = a.coef * 100, a.ci95 * 100, a.coef * bal[FEATS].std() * 100
a.to_csv(TABLES / "mg_score.csv")
print(a[["coef_pp", "ci_pp", "per_sd_pp"]].round(2))

ev = bal[bal.has_eval & bal.ev0.abs().lt(5) & bal.eval_change.notna()].copy()
ev["eval_change"] = ev.eval_change.clip(-10, 10)
fit(ev, "eval_change", extra=("ev0",)).to_csv(TABLES / "mg_eval.csv")

s = d.sample(1_500_000, random_state=1)
dm = pd.get_dummies(s.d_material.clip(-9, 9).astype(int), prefix="m", drop_first=True, dtype="float64")
r = sm.OLS(s.excess.astype("float64"), sm.add_constant(pd.concat([s[FEATS].astype("float64"), dm], axis=1))).fit(
    cov_type="HC1")
pd.DataFrame({"coef_pp": r.params * 100, "ci_pp": 1.96 * r.bse * 100}).loc[FEATS].to_csv(TABLES / "mg_score_all.csv")
del d, bal, s
gc.collect()

# draw rates
c = pd.read_parquet(WORK / "core.parquet", columns=["speed", "band", "dbin", "result", "white_castled",
                                                    "black_castled", "opposite_side_castling", "queens_off_ply"])
c["draw"] = (c.result == 0.5).astype("float32")
c["xdraw"] = c.draw - c.groupby(["speed", "band", "dbin"], observed=True).draw.transform("mean")
both = (c.white_castled.astype(str) != "") & (c.black_castled.astype(str) != "")
c["castling"] = np.where(~both, "not both castled", np.where(c.opposite_side_castling, "opposite sides", "same side"))
c["qtrade"] = pd.cut(c.queens_off_ply.fillna(9999), [0, 20, 40, 60, 9998, 10000],
                     labels=["by move 10", "moves 11-20", "moves 21-30", "after move 30", "queens stay on"])
out = []
for slow in (False, True):
    x = c[c.speed.isin(["rapid", "classical"])] if slow else c
    for col in ("castling", "qtrade"):
        g = x.groupby(col, observed=True)
        t = pd.DataFrame({"games": g.size(), "draw_rate": g.draw.mean() * 100, "excess_draw_pp": g.xdraw.mean() * 100,
                          "ci_pp": 1.96 * g.xdraw.std() / np.sqrt(g.size()) * 100})
        t["speeds"], t["factor"] = ("rapid+classical" if slow else "all"), col
        out.append(t.reset_index().rename(columns={col: "level"}))
r = pd.concat(out)
r.to_csv(TABLES / "draws.csv", index=False)
print(r.round(2).to_string(index=False))
