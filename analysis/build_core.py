"""Step 1: one analysis table of all filtered games with corrected setup labels and the rating baseline.

Writes results/core.parquet (about 9.8 million rows). Run from the project root:  python analysis/build_core.py
"""
import gc

import pandas as pd
from common import MONTHS, WORK, add_baseline, load_month, path

COLS = ["game_id", "month", "speed", "white_elo", "black_elo", "result", "plies", "eco", "family", "opening",
        "white_castled", "black_castled", "opposite_side_castling", "queens_off_ply"]

parts = []
for m in MONTHS:
    d = load_month(m, COLS)
    s = pd.read_parquet(path("setups", m))  # labels recomputed with the corrected detector rules
    d = d.merge(s, on="game_id", how="left", validate="one_to_one").drop(columns="game_id")
    parts.append(d)
    gc.collect()
d = pd.concat(parts, ignore_index=True)
for c in ["month", "speed", "eco", "family", "opening", "white_castled", "black_castled", "white_setup", "black_setup"]:
    d[c] = d[c].astype("category")
d = add_baseline(d)
d.to_parquet(WORK / "core.parquet")
print(f"{len(d):,} games -> {WORK / 'core.parquet'}; White scores {d.result.mean():.4f}, "
      f"draw rate {(d.result == 0.5).mean():.4f}")
