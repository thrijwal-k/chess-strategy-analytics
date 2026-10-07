"""RQ3: settled endgames. Aggregates outcome counts month by month (keeps memory low) into docs/tables/eg_agg.csv."""
import gc

import numpy as np
import pandas as pd
from common import BAND_EDGES, BAND_LABELS, MONTHS, TABLES, WORK, load_month, path

KEY = {"pawn": "Pawn endgame", "rook": "Rook endgame", "rook2": "Double rook endgame",
       "ocb": "Opposite-coloured bishops", "scb": "Same-coloured bishops", "knight": "Knight endgame",
       "bvn": "Bishop vs knight", "queen": "Queen endgame", "rvm": "Rook vs minor piece",
       "rm": "Rook and minor endgame"}

look = pd.read_parquet(WORK / "core.parquet", columns=["speed", "band", "dbin", "result"])
look = look.groupby(["speed", "band", "dbin"], observed=True).result.mean().rename("expected").reset_index()
look["speed"], look["band"] = look.speed.astype(str), look.band.astype(str)
rows = []
for m in MONTHS:
    d = load_month(m, ["game_id", "speed", "result", "white_elo", "black_elo"])
    diff = d.white_elo.astype("float32") - d.black_elo.astype("float32")
    mean = (d.white_elo.astype("float32") + d.black_elo.astype("float32")) / 2
    d = pd.DataFrame({"game_id": d.game_id.astype(str).values, "speed": d.speed.astype(str).values,
                      "result": d.result.values,
                      "band": pd.cut(mean, BAND_EDGES, labels=BAND_LABELS, right=False).astype(str).values,
                      "dbin": np.clip((diff / 25).round(), -24, 24).astype("int8").values})
    d = d.merge(look, on=["speed", "band", "dbin"], how="left")
    d = d.merge(pd.read_parquet(path("endgames", m)), on="game_id", how="inner").drop(columns="game_id")
    d["slow"] = d.speed.isin(["rapid", "classical"])
    for short, name in KEY.items():
        x = d[d[f"{short}_ply"].notna()]
        mat, pw = x[f"{short}_material"], x[f"{short}_pawns"]
        conds = [("equal", (mat == 0) & (pw == 0)), ("one pawn up", (mat.abs() == 1) & (pw.abs() == 1)),
                 ("two pawns up", (mat.abs() == 2) & (pw.abs() == 2))]
        for cond, mask in conds:
            if short == "rvm" and cond != "equal":
                continue  # rook vs minor: the side "up" in material is the rook side, which may be pawns down
            y = x[mask]
            if cond == "equal":
                s, ex = y.result.values, y.expected.values
            else:
                up = np.sign(mat[mask].values) > 0
                s = np.where(up, y.result.values, 1 - y.result.values)
                ex = np.where(up, y.expected.values, 1 - y.expected.values)
            for slow in (False, True):
                k = y.slow.values == slow
                rows.append({"month": m, "type": name, "cond": cond, "slow": slow, "n": int(k.sum()),
                             "wins": float((s[k] == 1).sum()), "draws": float((s[k] == 0.5).sum()),
                             "score": float(s[k].sum()), "expected": float(np.nansum(ex[k])),
                             "sq": float(((s[k] - ex[k]) ** 2).sum())})
    rows.append({"month": m, "type": "ALL", "cond": "settled", "slow": None, "n": int((d.settled_type != "").sum()),
                 "wins": 0, "draws": 0, "score": 0, "expected": 0, "sq": 0})
    del d
    gc.collect()
a = pd.DataFrame(rows)
a.to_csv(TABLES / "eg_agg.csv", index=False)
print("games with a settled endgame:", a[a.type == "ALL"].n.sum())
g = a[(a.cond == "one pawn up") & (a.slow == True)].groupby("type")[["n", "wins", "draws"]].sum()  # noqa: E712
print((g.assign(win=g.wins / g.n * 100, draw=g.draws / g.n * 100)[["n", "win", "draw"]]).round(1))
