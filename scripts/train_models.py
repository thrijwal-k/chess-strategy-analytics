"""Train the two result models tested in tests/test_models.py and save them, with a held-out test sample, in models/.

Train on September and October 2020, test on November 2020 (same split as analysis/rq5_prediction.py).

    python scripts/train_models.py --data data --train 600000 --test 50000
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from chessanalytics.models import INGAME20, MODELS_DIR, PREGAME, OrdinalResultModel, save, speed_code  # noqa: E402

MONTHS, TEST_MONTH = ["2020-09", "2020-10", "2020-11"], "2020-11"
COLS = ["game_id", "rated", "speed", "result", "termination", "plies", "white_elo", "black_elo", "time_control",
        "w_material_m20", "b_material_m20"]


def month_table(data: Path, month: str) -> pd.DataFrame:
    x = pd.read_parquet(data / "features" / f"features_{month}.parquet", columns=COLS)
    x = x[x.rated & x.speed.isin(["bullet", "blitz", "rapid", "classical"]) & x.result.notna()
          & x.termination.isin(["Normal", "Time forfeit"]) & (x.plies >= 10)
          & x.white_elo.notna() & x.black_elo.notna()]
    clocks = data / "clocks" / f"clocks_{month}.parquet"
    x = x.merge(pd.read_parquet(clocks, columns=["game_id", "w_clock_m20", "b_clock_m20"]), on="game_id", how="left")
    tc = x.time_control.astype(str).str.split("+", expand=True)
    base = pd.to_numeric(tc[0], errors="coerce").astype("float32")
    w, b = x.white_elo.astype("float32"), x.black_elo.astype("float32")
    return pd.DataFrame({
        "month": month, "speed": x.speed.astype(str).values, "plies": x.plies.values,
        "y": x.result.map({0.0: 0, 0.5: 1, 1.0: 2}).astype("int8").values,
        "diff": (w - b).values, "mean": ((w + b) / 2).values, "spd": speed_code(x.speed),
        "mat": (x.w_material_m20.astype("float32") - x.b_material_m20.astype("float32")).values,
        "wclk": (x.w_clock_m20.astype("float32") / base).values,
        "bclk": (x.b_clock_m20.astype("float32") / base).values,
        "base": base.values, "inc": pd.to_numeric(tc[1], errors="coerce").astype("float32").values})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--out", type=Path, default=MODELS_DIR)
    ap.add_argument("--train", type=int, default=600_000)
    ap.add_argument("--test", type=int, default=50_000)
    a = ap.parse_args()
    rng = np.random.default_rng(0)
    d = pd.concat([month_table(a.data, m) for m in MONTHS], ignore_index=True)
    train, test = d[d.month != TEST_MONTH], d[d.month == TEST_MONTH]

    def sample(x: pd.DataFrame, n: int) -> pd.DataFrame:
        return x.iloc[rng.choice(len(x), min(n, len(x)), replace=False)].reset_index(drop=True)

    meta = {}
    for name, feats, rows in [("pregame", PREGAME, None),
                              ("ingame20", INGAME20, lambda x: (x.plies >= 41) & x.mat.notna()
                               & x.wclk.notna() & x.bclk.notna() & x.base.gt(0))]:
        tr, te = (train, test) if rows is None else (train[rows(train)], test[rows(test)])
        tr, te = sample(tr, a.train), sample(te, a.test)
        model = OrdinalResultModel(feats).fit(tr, tr.y.values)
        save(model, name, a.out)
        te[["speed", "y", *feats]].to_parquet(a.out / f"{name}_test.parquet", index=False)
        P = model.predict_proba(te)
        meta[name] = {"train_games": len(tr), "test_games": len(te), "accuracy": float((P.argmax(1) == te.y).mean()),
                      "log_loss": float(-np.mean(np.log(np.clip(P[np.arange(len(te)), te.y], 1e-15, 1))))}
        print(name, meta[name], flush=True)
    (a.out / "metrics.json").write_text(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
