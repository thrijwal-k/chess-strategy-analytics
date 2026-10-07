"""RQ1: opening effects against the rating baseline. Needs results/core.parquet (build_core.py)."""
import numpy as np
import pandas as pd
from common import TABLES, WORK, summarise

d = pd.read_parquet(WORK / "core.parquet", columns=["white_setup", "black_setup", "opening", "eco", "family", "result",
                                                    "expected", "excess", "band", "dbin", "speed"])
print(f"named lines seen {d.opening.nunique():,}, ECO codes {d.eco.nunique()}, families {d.family.nunique()}")
summarise(d, "white_setup", 2000).sort_values("excess").to_csv(TABLES / "white_setups.csv")
summarise(d, "black_setup", 2000).sort_values("excess").to_csv(TABLES / "black_defences.csv")
summarise(d, ["white_setup", "black_setup"], 2000).to_csv(TABLES / "matchups.csv")
summarise(d, "family", 2000).sort_values("excess").to_csv(TABLES / "families.csv")
summarise(d[d.white_setup == "London System"], "band", 500).to_csv(TABLES / "london_by_band.csv")

ld = d[(d.white_setup == "London System") & d.black_setup.astype(str).str.startswith("Dutch")]
print(f"London vs Dutch: {len(ld):,} games, edge {ld.excess.mean() * 100:+.2f} "
      f"± {1.96 * ld.excess.std() / np.sqrt(len(ld)) * 100:.2f} pp")

# Elo formula against observed scores by rating gap
elo = 1 / (1 + 10 ** (-(d.dbin.astype(float) * 25) / 400))
cal = pd.DataFrame({"observed": d.result, "elo_formula": elo, "dbin": d.dbin}).groupby("dbin").mean()
cal.index = cal.index.astype(int) * 25  # the top and bottom bins hold all gaps of 600 or more
cal.to_csv(TABLES / "elo_calibration.csv")
print(cal.loc[[-600, -300, 0, 300, 600]].round(3))
