"""All report figures, drawn from docs/tables (and the explorer history for the trend charts)."""
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from common import DATA, FIGURES, GRID, INK, MUTED, SERIES, TABLES, plot_style

sys.path.insert(0, "src")
from chessanalytics import timeseries as ts  # noqa: E402

plot_style()
BLUE, ORANGE = SERIES[0], SERIES[1]


def finish(fig, ax, title: str, name: str, grid_axis: str = "x") -> None:
    ax.grid(axis=grid_axis, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.set_title(title, loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(FIGURES / name)
    plt.close(fig)


def forest(csv: str, title: str, name: str) -> None:
    t = pd.read_csv(TABLES / csv, index_col=0)
    t = t[t.games >= 10000]
    t = t[~t.index.str.contains(r"other|Other|King's Pawn \(1|Queen's Pawn \(|Irregular")].sort_values("excess")
    fig, ax = plt.subplots(figsize=(7.5, 0.26 * len(t) + 1.2))
    ax.axvline(0, color=MUTED, lw=1)
    ax.errorbar(t.excess * 100, np.arange(len(t)), xerr=t.ci95 * 100, fmt="o", color=BLUE, ms=4, elinewidth=1.5)
    ax.set_yticks(np.arange(len(t)), t.index)
    ax.set_xlabel("Edge for White vs rating prediction (percentage points)")
    finish(fig, ax, title, name)


forest("white_setups.csv", "White systems: score above or below what the ratings predict", "fig1_white_systems.png")
forest("black_defences.csv", "Black defences (negative = good for Black)", "fig2_black_defences.png")

t = pd.read_csv(TABLES / "london_by_band.csv", index_col=0)
fig, ax = plt.subplots(figsize=(6.5, 3.4))
ax.axhline(0, color=MUTED, lw=1)
ax.errorbar(np.arange(len(t)), t.excess * 100, yerr=t.ci95 * 100, fmt="o-", color=BLUE, lw=2, ms=5)
ax.set_xticks(np.arange(len(t)), t.index, fontsize=8.5)
ax.set_ylabel("Edge for White (pp)")
ax.set_xlabel("Average rating of the two players")
finish(fig, ax, "The London System helps lower-rated players most", "fig3_london_by_rating.png", "y")

a = pd.read_csv(TABLES / "eg_agg.csv")
a = a[(a.cond == "one pawn up") & (a.slow.astype(str) == "True")]
g = a.groupby("type")[["n", "wins", "draws"]].sum()
g["win"], g["draw"] = g.wins / g.n * 100, g.draws / g.n * 100
g = g.sort_values("win")
fig, ax = plt.subplots(figsize=(7.5, 4.4))
yy = np.arange(len(g))
ax.barh(yy, g.win, color=BLUE, height=0.62, label="Side with the extra pawn wins")
ax.barh(yy, g.draw, left=g.win + 0.6, color=ORANGE, height=0.62, label="Draw")
for i, (w, dr, n) in enumerate(zip(g.win, g.draw, g.n, strict=True)):
    ax.text(w / 2, i, f"{w:.0f}%", va="center", ha="center", color="white", fontsize=8.5)
    ax.text(w + dr + 2, i, f"{dr:.0f}% draw  (n={int(n):,})", va="center", color=MUTED, fontsize=8)
ax.set_yticks(yy, g.index)
ax.set_xlim(0, 118)
ax.set_xticks([0, 20, 40, 60, 80, 100])
ax.set_xlabel("% of games")
ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.13), ncol=2, frameon=False, fontsize=8.5)
finish(fig, ax, "One pawn up: how often it wins (rapid and classical games)", "fig4_endgame_conversion.png")

names = {"d_isolated": "Isolated pawns", "d_doubled": "Doubled pawns", "d_backward": "Backward pawns",
         "d_passed": "Passed pawns", "d_islands": "Pawn islands", "d_iqp": "Isolated queen pawn",
         "d_hanging": "Hanging pawns", "d_bishop_pair": "Bishop pair", "d_outposts": "Knight outposts",
         "d_rooks_open": "Rooks on open files", "d_rooks_half_open": "Rooks on half-open files",
         "d_rooks_7th": "Rooks on the 7th rank", "d_pawn_shield": "Pawn shield (per pawn)",
         "d_open_files_near_king": "Open files near king", "d_centre": "Centre control (per unit)",
         "d_space": "Space (per square)", "d_developed_minors": "Developed minor pieces",
         "unc_diff": "King still in the centre"}
m = pd.read_csv(TABLES / "mg_score.csv", index_col=0).rename(index=names).sort_values("coef_pp")
fig, ax = plt.subplots(figsize=(7.5, 5.6))
ax.axvline(0, color=MUTED, lw=1)
ax.errorbar(m.coef_pp, np.arange(len(m)), xerr=m.ci_pp, fmt="o", color=BLUE, ms=4, elinewidth=1.5)
ax.set_yticks(np.arange(len(m)), m.index)
ax.set_xlabel("Change in White's score per one more than the opponent (pp)")
finish(fig, ax, "Middlegame features at move 20 (equal material, ratings accounted for)", "fig5_middlegame.png")

# trends
d = ts.load_history(DATA / "explorer" / "history.csv")


def series(p: str, g: str = "all", start: str = "2016-01"):
    s = ts.series(d, p, g)[start:] * 100
    return s.index.to_timestamp(), s.values


def events(ax) -> None:
    marks = [("2020-03", "Lockdown ", "right"), ("2020-10-23", " The Queen's Gambit\n (Netflix)", "left")]
    for month, label, ha in marks:
        x = pd.Timestamp(month)
        ax.axvline(x, color=MUTED, lw=1, ls="--")
        ax.text(x, ax.get_ylim()[1], label, va="top", ha=ha, fontsize=8, color=MUTED)


fig, ax = plt.subplots(figsize=(8, 3.8))
for (g, lab), c in zip([("under_1600", "Under 1600"), ("all", "All players"), ("2000_plus", "2000+")], SERIES,
                       strict=False):
    x, yv = series("Queen's Gambit", g)
    ax.plot(x, yv, color=c, lw=2, label=lab)
ax.set_ylabel("% of games reaching 1.d4 d5 2.c4")
ax.legend(frameon=False, fontsize=8.5, loc="lower left", ncol=3)
events(ax)
finish(fig, ax, "Queen's Gambit share: a one-month bump among newer players, then back to trend",
       "fig6_queens_gambit.png", "y")

s = ts.series(d, "Start position", value="games")
fig, ax = plt.subplots(figsize=(8, 3.4))
ax.plot(s.index.to_timestamp(), s.values / 1e6, color=BLUE, lw=2)
ax.set_yscale("log")
ax.set_yticks([0.1, 1, 10, 100], ["0.1", "1", "10", "100"])
ax.set_ylabel("Rated games per month (millions)")
events(ax)
finish(fig, ax, "Lichess growth: lockdown added about 36% more games almost overnight", "fig7_games_per_month.png", "y")

fig, ax = plt.subplots(figsize=(8, 4))
for (p, lab), c in zip([("Caro-Kann", "Caro-Kann"), ("Queen's Gambit", "Queen's Gambit"),
                        ("London vs 1...d5", "London (1.d4 d5 2.Bf4)"), ("King's Gambit", "King's Gambit")], SERIES[:4],
                       strict=True):
    x, yv = series(p, "all", "2013-06")
    ax.plot(x, yv, color=c, lw=2)
    ax.text(x[-1], yv[-1], "  " + lab, va="center", fontsize=8.5, color=INK)
ax.set_xlim(x[0], x[-1] + pd.Timedelta(days=620))
ax.set_ylabel("% of all games")
finish(fig, ax, "Long-run trends: the Caro-Kann and London rise, the gambits fade", "fig8_long_run.png", "y")

# in-game prediction
r = pd.read_csv(TABLES / "ingame.csv")
r = r[r.games == "engine-analysed games"]
fig, ax = plt.subplots(figsize=(7.5, 3.8))
for (name, g), c in zip(r.groupby("model", sort=False), SERIES, strict=True):
    ax.plot(g.after_move, g.accuracy * 100, "o-", color=c, lw=2, ms=6)
    ax.text(25.4, g.accuracy.iloc[-1] * 100, name, va="center", fontsize=8, color=INK)
ax.set_xticks([15, 20, 25], ["Move 15", "Move 20", "Move 25"])
ax.set_xlim(14, 33)
ax.set_ylabel("Results predicted correctly (%)")
finish(fig, ax, "Predicting the result during the game (engine-analysed test games)", "fig9_ingame.png", "y")
print("figures written to", FIGURES)
