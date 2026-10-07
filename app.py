"""Chess Strategy Analytics dashboard.

Run with:  streamlit run app.py
Reads only the summary tables in docs/tables, so it starts instantly and needs none of the large data files.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

TABLES = Path(__file__).parent / "docs" / "tables"
sys.path.insert(0, str(Path(__file__).parent / "src"))
from chessanalytics.boards import diagrams, matchup  # noqa: E402
from chessanalytics.explainer import Explainer, Ollama  # noqa: E402

BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
DIVERGING = ["#e34948", "#f0efec", "#2a78d6"]  # good for Black, neutral, good for White
CATCH_ALL = ("other", "Other", "King's Pawn (1.e4)", "Queen's Pawn (other)", "Irregular")

st.set_page_config(page_title="Chess Strategy Analytics", page_icon="♞", layout="wide")


@st.cache_data
def load(name: str, **kw) -> pd.DataFrame:
    return pd.read_csv(TABLES / name, **kw)


def show(chart, legend_bottom: bool = False) -> None:
    """Full axis labels (no skipping or truncation) and readable legends on every chart."""
    chart = chart.configure_axis(labelLimit=280, labelOverlap=False, labelFontSize=12, titleFontSize=12)
    chart = chart.configure_legend(labelLimit=360, labelFontSize=12, orient="bottom" if legend_bottom else "right")
    st.altair_chart(chart, width="stretch")


def pp(x: float) -> str:
    return f"{x * 100:+.1f} pp"


def show_boards(boards) -> None:
    """Chessboards side by side, each with its caption."""
    if not boards:
        return
    for col, d in zip(st.columns(3), boards[:3], strict=False):
        col.markdown(d.svg, unsafe_allow_html=True)
        col.caption(d.caption)


def is_specific(name: str) -> bool:
    return not any(c in name for c in CATCH_ALL)


st.title("Does the opening decide the game?")
st.caption("9.8 million rated Lichess games (Sept to Nov 2020) and monthly opening statistics from 2013 to 2026. "
           "Every score is compared with what the players' ratings predict: the **edge** is how far the result is "
           "above (+) or below (−) that prediction, in percentage points of score for White.")

tabs = st.tabs(["Ask", "Matchups", "Openings", "Trends", "Middlegame", "Endgames", "Prediction"])


@st.cache_resource
def explainer() -> tuple[Explainer, str]:
    """Use a local Ollama model when one is running; otherwise answer with the retrieved sources."""
    model = Ollama(model=os.environ.get("OLLAMA_MODEL", "llama3.2:3b"))
    if os.environ.get("EXPLAINER_NO_LLM") != "1" and model.available():
        return Explainer(generator=model), f"Answers written by {model.model} running locally with Ollama"
    return Explainer(), "No local model running: answers show the most relevant explanations and figures"


# ---------------------------------------------------------------------------------------------------- ask
with tabs[0]:
    ex, mode_note = explainer()
    st.subheader("Ask anything about chess or these results")
    st.caption(mode_note + ". Every answer is built only from this project's explanations and tables, and any "
               "number in a written answer is checked against them.")
    examples = ["What is the London System?", "Is the London good against the Dutch?",
                "Why are opposite-coloured bishops drawish?", "What does +1.0 pp mean?",
                "Did the Netflix series change anything?", "What is a bishop pair?"]
    cols = st.columns(3)
    for i, q in enumerate(examples):
        if cols[i % 3].button(q, key=f"ex{i}", width="stretch"):
            st.session_state["question"] = q
    question = st.text_input("Your question", key="question", placeholder="e.g. How does a knight move?")
    if question:
        with st.spinner("Looking it up..."):
            ans = ex.ask(question)
        if ans.mode == "out of scope":
            st.warning(ans.text)
        else:
            st.markdown(ans.text)
            if ans.note:
                st.info(ans.note)
            show_boards(diagrams(question, ex.facts.entities(question), set(ex.facts.white.index)))
            with st.expander(f"Sources ({len(ans.passages)})"):
                for i, p in enumerate(ans.passages, 1):
                    st.markdown(f"**[{i}] {p.title}** ({'exact figures from' if p.kind == 'fact' else 'from'} "
                                f"`{p.source}`)")

# ---------------------------------------------------------------------------------------------------- matchups
with tabs[1]:
    m = load("matchups.csv")
    w_all, b_all = load("white_setups.csv", index_col=0), load("black_defences.csv", index_col=0)
    whites = sorted(m.white_setup.unique())
    c1, c2 = st.columns(2)
    white = c1.selectbox("White system", whites, index=whites.index("London System"))
    blacks = sorted(m[m.white_setup == white].black_setup.unique())
    default_black = "Dutch: Classical / other" if "Dutch: Classical / other" in blacks else blacks[0]
    black = c2.selectbox("Black defence", blacks, index=blacks.index(default_black))
    row = m[(m.white_setup == white) & (m.black_setup == black)].iloc[0]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Games", f"{int(row.games):,}")
    k2.metric("White's score", f"{row.white_score * 100:.1f}%", help="Wins plus half the draws")
    k3.metric("Ratings predicted", f"{row.expected * 100:.1f}%")
    k4.metric("Edge for White", pp(row.excess), help=f"95% interval ± {row.ci95 * 100:.1f} pp")
    significant = abs(row.excess) > row.ci95
    st.write(f"95% interval: {pp(row.excess - row.ci95)} to {pp(row.excess + row.ci95)}. "
             + ((f"**A real advantage for {'White' if row.excess > 0 else 'Black'}** beyond what the ratings "
                 "predict (the whole interval is on one side of zero).") if significant else
                "**Too small to tell apart from chance**: the matchup is effectively even once ratings are "
                "accounted for."))
    st.write(f"For comparison, **{white}** against all defences: {pp(w_all.loc[white, 'excess'])}; "
             f"**{black}** against all systems: {pp(b_all.loc[black, 'excess'])} for White.")
    board = matchup(white, black)
    if board:
        show_boards([board])

    st.subheader("Main systems against main defences")
    big_w = w_all[(w_all.games >= 40_000) & w_all.index.map(is_specific)].index
    big_b = b_all[(b_all.games >= 40_000) & b_all.index.map(is_specific)].index
    h = m[m.white_setup.isin(big_w) & m.black_setup.isin(big_b)].copy()
    h["edge_pp"] = h.excess * 100
    h["ci_pp"] = h.ci95 * 100
    heat = alt.Chart(h).mark_rect(stroke="#fcfcfb", strokeWidth=2).encode(
        x=alt.X("black_setup:N", title="Black defence", sort=list(big_b),
                axis=alt.Axis(labelAngle=-40, labelOverlap=False, labelLimit=220)),
        y=alt.Y("white_setup:N", title="White system", sort=list(big_w),
                axis=alt.Axis(labelOverlap=False, labelLimit=220)),
        color=alt.Color("edge_pp:Q", title="Edge for White (pp)",
                        scale=alt.Scale(domain=[-4, 0, 4], range=DIVERGING, clamp=True, interpolate="rgb")),
        tooltip=[alt.Tooltip("white_setup:N", title="White"), alt.Tooltip("black_setup:N", title="Black"),
                 alt.Tooltip("games:Q", format=","), alt.Tooltip("edge_pp:Q", title="Edge (pp)", format="+.2f"),
                 alt.Tooltip("ci_pp:Q", title="± 95% (pp)", format=".2f")],
    ).properties(height=30 * len(big_w) + 40)
    show(heat)
    st.caption("Systems and defences with at least 40,000 games; cells with at least 2,000 games. Blue: White scores "
               "more than the ratings predict. Red: Black does. Grey: about even. Hover for numbers and intervals.")

# ---------------------------------------------------------------------------------------------------- openings
with tabs[2]:
    which = st.radio("Group openings by", ["White system", "Black defence", "Catalogue family"], horizontal=True)
    t = {"White system": "white_setups.csv", "Black defence": "black_defences.csv",
         "Catalogue family": "families.csv"}[which]
    df = load(t, index_col=0)
    min_games = st.slider("Minimum games", 2000, 100_000, 10_000, step=2000)
    df = df[df.games >= min_games].sort_values("excess")
    df = df.assign(edge_pp=df.excess * 100, ci_pp=df.ci95 * 100).reset_index(names="opening")
    base = alt.Chart(df).encode(y=alt.Y("opening:N", sort=df.opening.tolist(), title=None))
    bars = base.mark_rule(color=BLUE, strokeWidth=2).encode(
        x=alt.X("lo:Q", title="Edge for White (pp)"), x2="hi:Q").transform_calculate(
        lo="datum.edge_pp - datum.ci_pp", hi="datum.edge_pp + datum.ci_pp")
    dots = base.mark_circle(color=BLUE, size=60).encode(
        x="edge_pp:Q", tooltip=["opening", alt.Tooltip("games:Q", format=","),
                                alt.Tooltip("edge_pp:Q", title="Edge (pp)", format="+.2f"),
                                alt.Tooltip("ci_pp:Q", title="± 95% (pp)", format=".2f")])
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color="#52514e").encode(x="x:Q")
    show((zero + bars + dots).properties(height=max(300, 22 * len(df))))
    st.dataframe(df[["opening", "games", "share", "white_score", "expected", "edge_pp", "ci_pp", "draw_rate"]],
                 hide_index=True, width="stretch",
                 column_config={"games": st.column_config.NumberColumn(format="localized"),
                                "share": st.column_config.NumberColumn(format="percent"),
                                "white_score": st.column_config.NumberColumn(format="percent"),
                                "expected": st.column_config.NumberColumn(format="percent"),
                                "draw_rate": st.column_config.NumberColumn(format="percent"),
                                "edge_pp": st.column_config.NumberColumn("edge (pp)", format="%+.2f"),
                                "ci_pp": st.column_config.NumberColumn("± 95% (pp)", format="%.2f")})
    lb = load("london_by_band.csv", index_col=0)
    st.subheader("The London System's edge by rating")
    lb = lb.assign(edge_pp=lb.excess * 100, lo=(lb.excess - lb.ci95) * 100, hi=(lb.excess + lb.ci95) * 100)
    lb = lb.reset_index(names="band")
    chart = alt.Chart(lb).encode(x=alt.X("band:N", sort=None, title="Average rating of the two players",
                                                axis=alt.Axis(labelAngle=0)))
    rule = chart.mark_rule(color=BLUE, strokeWidth=2).encode(y=alt.Y("lo:Q", title="Edge for White (pp)"), y2="hi:Q")
    line = chart.mark_line(color=BLUE, point=True).encode(
        y="edge_pp:Q", tooltip=["band", alt.Tooltip("edge_pp:Q", format="+.2f"), alt.Tooltip("games:Q", format=",")])
    show((rule + line).properties(height=280))

# ---------------------------------------------------------------------------------------------------- trends
with tabs[3]:
    tr = load("trends.csv")
    tr["month"] = pd.to_datetime(tr.month)
    positions = [p for p in tr.position.unique() if p != "Start position"]
    c1, c2 = st.columns([3, 1])
    picked = c1.multiselect("Openings (up to 4)", positions, max_selections=4,
                            default=["Queen's Gambit", "London vs 1...d5", "Caro-Kann"])
    groups = {"All players": "all", "Under 1600": "under_1600", "1600 to 1999": "1600_1999", "2000+": "2000_plus"}
    group = groups[c2.selectbox("Players", list(groups))]
    measure = st.radio("Show", ["Share of all games", "White's score"], horizontal=True)
    col = "share" if measure == "Share of all games" else "white_score"
    x = tr[tr.position.isin(picked) & (tr.group == group) & (tr.month >= "2016-01-01")].copy()
    x["value"] = x[col] * 100
    lines = alt.Chart(x).mark_line(strokeWidth=2).encode(
        x=alt.X("month:T", title=None, axis=alt.Axis(format="%Y", tickCount="year", labelAngle=0)),
        y=alt.Y("value:Q", title=f"{measure} (%)", scale=alt.Scale(zero=False)),
        color=alt.Color("position:N", title=None, scale=alt.Scale(domain=picked,
                                                                  range=[BLUE, ORANGE, AQUA, YELLOW][:len(picked)])),
        tooltip=[alt.Tooltip("month:T", format="%b %Y"), "position", alt.Tooltip("value:Q", format=".2f"),
                 alt.Tooltip("games:Q", format=",")])
    events = pd.DataFrame({"month": pd.to_datetime(["2020-03-15", "2020-10-23"]),
                           "event": ["Lockdown", "The Queen's Gambit (Netflix)"]})
    rules = alt.Chart(events).mark_rule(strokeDash=[4, 4], color="#52514e").encode(x="month:T", tooltip=["event"])
    show((lines + rules).properties(height=380), legend_bottom=True)
    st.caption("Share = games reaching the opening's position ÷ all rated games that month in the same rating group. "
               "Dashed lines: lockdown (March 2020) and the Netflix release (23 October 2020). Source: Lichess opening "
               "explorer, to May 2026.")
    q = load("qg_oct_nov.csv")
    q20 = q[q.year == 2020].set_index("group")
    st.info(f"The Queen's Gambit share rose {q20.loc['all', 'change_pp']:+.2f} pp from October to November 2020, "
            f"{q20.loc['all', 'change_in_sd']:.1f} times the typical monthly change, and "
            f"{q20.loc['under_1600', 'change_pp']:+.2f} pp among players under 1600. The bump faded by spring 2021.")

# ---------------------------------------------------------------------------------------------------- middlegame
with tabs[4]:
    names = {"d_isolated": "Isolated pawns", "d_doubled": "Doubled pawns", "d_backward": "Backward pawns",
             "d_passed": "Passed pawns", "d_islands": "Pawn islands", "d_iqp": "Isolated queen pawn",
             "d_hanging": "Hanging pawns", "d_bishop_pair": "Bishop pair", "d_outposts": "Knight outposts",
             "d_rooks_open": "Rooks on open files", "d_rooks_half_open": "Rooks on half-open files",
             "d_rooks_7th": "Rooks on the 7th rank", "d_pawn_shield": "Pawn shield (per pawn)",
             "d_open_files_near_king": "Open files near king", "d_centre": "Centre control (per unit)",
             "d_space": "Space (per square)", "d_developed_minors": "Developed minor pieces",
             "unc_diff": "King still in the centre"}
    mg = load("mg_score.csv", index_col=0).rename(index=names).reset_index(names="feature")
    mg["lo"], mg["hi"] = mg.coef_pp - mg.ci_pp, mg.coef_pp + mg.ci_pp
    order = mg.sort_values("coef_pp").feature.tolist()
    base = alt.Chart(mg).encode(y=alt.Y("feature:N", sort=order, title=None))
    show((alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color="#52514e").encode(x="x:Q")
                     + base.mark_rule(color=BLUE, strokeWidth=2).encode(
                         x=alt.X("lo:Q", title="Change in White's score per one more than the opponent (pp)"),
                         x2="hi:Q")
                     + base.mark_circle(color=BLUE, size=60).encode(
                         x="coef_pp:Q", tooltip=["feature", alt.Tooltip("coef_pp:Q", title="pp", format="+.2f"),
                                                 alt.Tooltip("ci_pp:Q", title="± 95%", format=".2f")]))
         .properties(height=480))
    st.caption("Position after move 20 in 2.2 million games with equal material, ratings accounted for. "
               "These are associations, not causes.")
    dr = load("draws.csv")
    st.subheader("Draw rates")
    speeds = st.radio("Games", ["all", "rapid+classical"], horizontal=True, key="draw_speeds")
    tbl = dr[dr.speeds == speeds].assign(factor=lambda t: t.factor.map({"castling": "Castling",
                                                                        "qtrade": "Queens come off"}))
    st.dataframe(tbl[["factor", "level", "games", "draw_rate", "excess_draw_pp"]], hide_index=True,
                 width="stretch",
                 column_config={"games": st.column_config.NumberColumn(format="localized"),
                                "draw_rate": st.column_config.NumberColumn("draw rate (%)", format="%.1f"),
                                "excess_draw_pp": st.column_config.NumberColumn("vs rating prediction (pp)",
                                                                                format="%+.2f")})

# ---------------------------------------------------------------------------------------------------- endgames
with tabs[5]:
    a = load("eg_agg.csv")
    a = a[a.type != "ALL"]
    slow = st.radio("Time controls", ["Rapid and classical", "Bullet and blitz"], horizontal=True)
    cond = st.radio("Material", ["one pawn up", "two pawns up", "equal"], horizontal=True)
    sel = a[(a.cond == cond) & (a.slow.astype(str) == str(slow == "Rapid and classical"))]
    g = sel.groupby("type")[["n", "wins", "draws"]].sum()
    g = g[g.n > 0]
    who = "Side with the extra material wins" if cond != "equal" else "White wins"
    g[who], g["Draw"] = g.wins / g.n * 100, g.draws / g.n * 100
    long = g.reset_index().melt(id_vars=["type", "n"], value_vars=[who, "Draw"], var_name="outcome", value_name="pct")
    order = g.sort_values(who).index.tolist()[::-1]
    show(alt.Chart(long).mark_bar(cornerRadiusEnd=4).encode(
        y=alt.Y("type:N", sort=order, title=None), x=alt.X("pct:Q", title="% of games", stack=True),
        color=alt.Color("outcome:N", title=None, scale=alt.Scale(domain=[who, "Draw"], range=[BLUE, ORANGE])),
        tooltip=["type", "outcome", alt.Tooltip("pct:Q", format=".1f"), alt.Tooltip("n:Q", title="games", format=",")])
        .properties(height=360), legend_bottom=True)
    st.caption("Endgame type once the material has stayed the same for four moves. 4.55 million games reached one.")

# ---------------------------------------------------------------------------------------------------- prediction
@st.cache_resource
def result_models():
    from chessanalytics.models import load as load_model

    return load_model("pregame"), load_model("ingame20")


TIME_CONTROLS = {"1+0 (bullet)": (60, 0, 0), "2+1 (bullet)": (120, 1, 0), "3+0 (blitz)": (180, 0, 1),
                 "3+2 (blitz)": (180, 2, 1), "5+0 (blitz)": (300, 0, 1), "5+3 (blitz)": (300, 3, 1),
                 "10+0 (rapid)": (600, 0, 2), "15+10 (rapid)": (900, 10, 2), "30+0 (classical)": (1800, 0, 3)}

with tabs[6]:
    st.subheader("What are my chances?")
    st.caption("The tested models from `models/`: trained on September and October 2020, checked on November 2020. "
               "A higher rating, more material or more time on your clock can never lower your chances in these "
               "models (that is built in and tested).")
    try:
        pre_model, in_model = result_models()
    except Exception as exc:  # noqa: BLE001 - show the reason rather than breaking the whole tab
        st.warning(f"The saved models could not be loaded: {exc}")
        pre_model = in_model = None
    if pre_model is not None:
        c1, c2, c3 = st.columns(3)
        w_elo = c1.number_input("White's rating", 600, 3000, 1500, step=50, key="calc_white")
        b_elo = c2.number_input("Black's rating", 600, 3000, 1500, step=50, key="calc_black")
        tc = c3.selectbox("Time control (minutes + seconds per move)", list(TIME_CONTROLS), index=3)
        base, inc, spd = TIME_CONTROLS[tc]
        x = pd.DataFrame({"diff": [float(w_elo - b_elo)], "mean": [(w_elo + b_elo) / 2], "spd": [spd]})
        during = st.toggle("The game is under way: after move 20", key="calc_during")
        if during:
            d1, d2, d3 = st.columns(3)
            mat = d1.slider("Material for White (pawn = 1, knight/bishop = 3, rook = 5, queen = 9)", -9, 9, 0,
                            key="calc_mat")
            w_clk = d2.slider("White's clock left (seconds)", 0, base + 20 * inc, base // 2, key="calc_wclk")
            b_clk = d3.slider("Black's clock left (seconds)", 0, base + 20 * inc, base // 2, key="calc_bclk")
            x = x.assign(mat=float(mat), wclk=w_clk / base, bclk=b_clk / base, base=float(base), inc=float(inc))
            p = in_model.predict_proba(x)[0]
        else:
            p = pre_model.predict_proba(x)[0]
        k1, k2, k3 = st.columns(3)
        k1.metric("White wins", f"{p[2] * 100:.0f}%")
        k2.metric("Draw", f"{p[1] * 100:.0f}%")
        k3.metric("Black wins", f"{p[0] * 100:.0f}%")
        bar = pd.DataFrame({"result": ["White wins", "Draw", "Black wins"], "chance": p[::-1] * 100,
                            "order": [0, 1, 2]})
        show(alt.Chart(bar).mark_bar(height=28).encode(
            x=alt.X("sum(chance):Q", title="Chance (%)", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("result:N", title=None, sort=["White wins", "Draw", "Black wins"],
                            scale=alt.Scale(domain=["White wins", "Draw", "Black wins"],
                                            range=["#e8e8e8", "#9a9a9a", "#4a4a4a"])),
            order="order:O", tooltip=["result", alt.Tooltip("chance:Q", format=".1f")]).properties(height=70),
            legend_bottom=True)
        st.caption("Accuracy on held-out games: 54.8% before the game, 65.2% after move 20 (most likely result "
                   "correct). The models were trained on online Lichess games from 2020, so treat these as rough "
                   "odds, not certainties.")

    st.subheader("Before the game")
    st.dataframe(load("pregame.csv"), hide_index=True, width="stretch",
                 column_config={"test_games": st.column_config.NumberColumn("test games", format="localized"),
                                "log_loss": st.column_config.NumberColumn("log loss", format="%.4f"),
                                "rps": st.column_config.NumberColumn("ranked probability score", format="%.4f"),
                                "accuracy": st.column_config.NumberColumn(format="percent")})
    st.subheader("During the game")
    ig = load("ingame.csv")
    games = st.radio("Test games", ["engine-analysed games", "all games"], horizontal=True)
    x = ig[ig.games == games].assign(acc=lambda d: d.accuracy * 100)
    models = x.model.unique().tolist()
    show(alt.Chart(x).mark_line(point=True, strokeWidth=2).encode(
        x=alt.X("after_move:O", title="After move", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("acc:Q", title="Results predicted correctly (%)", scale=alt.Scale(zero=False)),
        color=alt.Color("model:N", title=None, sort=models,
                        scale=alt.Scale(domain=models, range=[BLUE, ORANGE, AQUA, YELLOW, "#e87ba4"][:len(models)])),
        tooltip=["model", "after_move", alt.Tooltip("acc:Q", format=".1f"), alt.Tooltip("log_loss:Q", format=".3f")])
        .properties(height=360), legend_bottom=True)
    st.caption("Trained on September and October 2020, tested on November 2020.")
