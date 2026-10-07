# Chess Strategy Analytics: project plan

**Working title of the report:** *Does the opening decide the game? Openings, middlegame structure and endgame
outcomes in 13 years of online chess, with a time-series study of opening popularity.*

## 1. Aim

Measure how much each phase of a chess game (opening, middlegame, endgame) tells us about the result, once player
strength is accounted for. Then model how the use and success of openings change over time.

The project has to be honest about one thing from the start: **in most games, the rating gap between the players
predicts the result far better than the opening does.** So every opening, middlegame and endgame result is
reported as an effect *on top of* a rating-based baseline, not as a raw win rate.

## 2. Research questions

| # | Question | Main output |
|---|---|---|
| RQ1 | How do results differ across **every named opening**, and across **White system vs Black defence** matchups (e.g. London vs Dutch), after controlling for rating gap, rating level and time control? | Opening table (all 3,865 named lines rolled up to 150 families and 500 ECO codes); matchup matrix with confidence intervals |
| RQ2 | Which **middlegame structures and strategic features** (isolated queen pawn, bishop pair, opposite-side castling and others) are linked to winning, drawing or losing, after controlling for rating and material? | Feature effect table; comparison with standard chess teaching |
| RQ3 | How often is each **endgame type** won, drawn or lost, and do textbook claims hold in practice (e.g. "opposite-coloured bishop endings are drawish", "all rook endings are drawn")? | Endgame outcome table by type, material balance and rating band |
| RQ4 | How has the **popularity and success of openings changed month by month** from 2013 to 2026? Can it be forecast, and do known events show up as structural breaks (the 2020 pandemic, Netflix's *The Queen's Gambit* in October 2020)? | Monthly time series, forecast backtests, change-point results |
| RQ5 | How well can the result be **predicted** before the game (ratings plus opening) and during it (engine evaluation and clock time at move N)? | Calibrated win/draw/loss models compared with an Elo baseline |

**Corrections to the original idea, built into RQ1.** A matchup has to be a White opening against a Black
defence. "London vs Caro-Kann" cannot happen (the London starts 1.d4; the Caro-Kann is a reply to 1.e4), and
"Queen's Gambit vs King's Gambit" cannot happen (both are White openings). The matchup matrix therefore only
contains pairs that can meet on the board, and it reports how many games support each cell.

## 3. Coverage: "every opening, middlegame and endgame"

### 3.1 Openings (all of them)

Two complementary classifications are applied to every game:

1. **Named line (complete coverage).** The Lichess opening catalogue (CC0): 3,865 named lines, 500 ECO codes,
   150 families. A game is classified by replaying it and recording the **deepest catalogue position reached**,
   matched by position (EPD) rather than by move order, so transpositions are classified correctly. This is the
   method the catalogue's maintainers recommend. The Lichess `[Opening]` and `[ECO]` headers are kept as a check.
2. **Setup (for matchups).** Many systems are defined by where the pieces go, not by a fixed move order. The
   London can be reached in dozens of move orders, and the catalogue splits it across several names. So each side
   is also labelled with a **setup** from rule-based detectors that look at the first 10 moves of that side only:

| White systems | Black defences vs 1.e4 | Black defences vs 1.d4 / flank openings |
|---|---|---|
| London System, Jobava London | Sicilian (White's reply, such as Open or Alapin, is labelled on White's side) | Queen's Gambit Declined |
| Colle / Zukertort | French | Queen's Gambit Accepted |
| Queen's Gambit, Catalan | Caro-Kann | Slav / Semi-Slav |
| Trompowsky, Torre, Veresov | Scandinavian | King's Indian Defence |
| Ruy Lopez, Italian, Scotch; vs the Sicilian: Open, Alapin, Closed, Grand Prix, Smith-Morra, Rossolimo/Moscow | Pirc / Modern | Grünfeld |
| King's Gambit, Vienna | Alekhine | Nimzo-Indian, Queen's Indian, Bogo-Indian |
| English, Réti, King's Indian Attack | Open games (1...e5): Petrov, Philidor, Two Knights, Berlin and others | Dutch (Leningrad, Stonewall, Classical) |
| Bird, Larsen, other flank | Owen, St George, other irregular | Benoni, Benko, Budapest, Old Indian, Englund, other |

Anything not caught by a detector falls back to its catalogue family, so no game is left unlabelled.

### 3.2 Middlegame strategy features

Measured from the position at fixed points (move 15, move 20, move 25) and at the move where the queens come
off, using python-chess:

| Theme | Feature |
|---|---|
| Pawn structure | Isolated queen pawn (IQP), isolated, doubled, backward and passed pawns, hanging pawns, pawn islands, Carlsbad and Maróczy structures |
| Pieces | Bishop pair, good vs bad bishop (own pawns on the bishop's colour), knight outposts, rooks on open and half-open files, rook on the 7th rank |
| King safety | Castled or not by move 12, **opposite-side castling**, pawn shield intact, open files next to the king |
| Space and centre | Central pawn control, space (squares controlled in the opponent's half), development lead at move 10 |
| Dynamics | Material imbalance (e.g. exchange down, minor piece vs three pawns), timing of the queen trade, gambit (material down after the opening but with compensation) |

Each feature's link to the result is estimated with the rating gap, rating level, time control and material
balance as controls. Where the game has engine analysis, the change in evaluation over the next 10 moves is
also used, which is a better measure than the final result because it is less affected by later mistakes.

### 3.3 Endgames

A game enters the endgame at the first position meeting a standard material threshold (no queens, or at most one
minor piece each with queens). Each endgame is classified by remaining material:

- King and pawn
- Rook (R vs R, R vs R with pawn up, R+minor vs R and others)
- Minor piece: same-coloured bishops, **opposite-coloured bishops**, knight vs knight, **bishop vs knight**
- Queen (Q vs Q, Q vs R, Q vs minor pieces)
- Rook vs minor piece (the exchange)
- Mixed (two or more pieces each)

Outputs: draw rate and conversion rate (how often the side with an extra pawn wins) for each type, by rating
band and time control. Textbook claims are tested as explicit hypotheses, and where possible checked against
exact tablebase results for positions with seven pieces or fewer.

## 4. Data

| Source | Use | Notes |
|---|---|---|
| **Lichess open database** (database.lichess.org), standard rated games, monthly files from Jan 2013 | All game-level analysis (RQ1 to RQ3, RQ5) | CC0. Each recent month is around 30 GB compressed (zstd PGN). Headers include ratings, time control, `[Opening]` and `[ECO]`; a minority of games include `[%eval]` engine evaluations and most games since 2017 include `[%clk]` clock times |
| **Lichess opening explorer** (explorer.lichess.ovh) | Monthly time series (RQ4) | Exact White/draw/Black counts for any position, filterable by month, rating band and speed, so 13 years of monthly series need no bulk download. Rate-limited, so requests are cached |
| **Lichess opening catalogue** (GitHub, CC0) | Named-line classification | Already in `data/openings/` |
| **Syzygy tablebases** via the Lichess API | Exact results for small endgames (RQ3) | Optional |

**How the data gets in.** Lichess servers are not reachable from the build environment (the same situation as
PaySim in the AML project), so the download scripts run on the laptop:

- **Game sample.** The parser streams `.pgn.zst` without decompressing to disk. It reads the first few million
  games of chosen months via an HTTP range request, then a stratified sample is kept (by time control and
  rating band). Target: about 5 million games for RQ1 to RQ3 and RQ5, plus every game with engine analysis from
  those months.
- **Time series.** One explorer request per month per position of interest, cached to `data/explorer/` as JSON,
  so reruns cost nothing.
- **Bias check.** The first games of a month are all played in its first hours. A month streamed in full is used
  to check that the opening mix of the first games matches the whole month.

## 5. Methods

### 5.1 Baseline that everything is compared against

The Elo expected score from the rating gap, extended to three outcomes (win, draw, loss) with a draw model
(Davidson's extension of Bradley-Terry). Any opening, middlegame or endgame effect is reported as the change in
expected score compared with this baseline, with 95% confidence intervals.

### 5.2 Openings (RQ1)

- Multinomial logistic regression: outcome ~ rating gap + mean rating + time control + opening.
- Openings with few games are partially pooled towards their family (empirical Bayes / random effects), so a
  line with 40 games does not appear in the top 10 by luck.
- Matchup matrix: White system × Black defence, with score vs baseline in each cell and the number of games.
- Interaction: does the London's effect change with rating level? (The usual claim is that it is "good for club
  players". This tests it.)

### 5.3 Middlegame and endgame (RQ2, RQ3)

- Same regression framework with the features from section 3.
- Stated plainly in the report: these are **associations, not causes**. Stronger players choose different
  structures, and a bishop pair often reflects a better position earlier on. The controls reduce this problem;
  they cannot remove it.

### 5.4 Time series (RQ4)

- Monthly series 2013 to 2026 for the top openings by share and by score, split by rating band and speed.
- Seasonality and trend decomposition (STL).
- Forecasting with **rolling-origin backtests** (train to month t, forecast t+1 to t+12, repeat): seasonal naive
  baseline, exponential smoothing (ETS), ARIMA, and a gradient-boosted model with lagged features. Scored by
  MASE and sMAPE.
- Change-point detection (PELT) and an interrupted time series model around **March 2020** (pandemic) and
  **October 2020** (*The Queen's Gambit*), to test whether the Queen's Gambit really became more popular after
  the series, and whether that lasted.

### 5.5 Prediction (RQ5)

- **Before the game:** gradient-boosted classifier (win/draw/loss) on ratings, time control and opening,
  compared with the Elo baseline. Scored by log loss, Brier score, ranked probability score and calibration
  plots. Split by time, not at random (train on older months, test on newer ones), to avoid leakage.
- **During the game:** probability of each result at move 10, 20, 30 and 40 from evaluation, material, clock
  times and rating gap. This shows how quickly the result becomes predictable, and how clock time matters in
  blitz.

## 6. Engineering

```
chess-strategy-analytics/
  data/openings/            Lichess catalogue (CC0)
  src/chessanalytics/
    openings.py             catalogue loader and deepest-position classifier
    setups.py               White system and Black defence detectors
    pgn_stream.py           fast streaming parser for .pgn and .pgn.zst (headers, moves, eval, clock)
    middlegame.py           structure and strategy features             (phase 2)
    endgame.py              endgame detection and classification        (phase 2)
    explorer.py             cached opening-explorer client              (phase 3)
    timeseries.py           decomposition, backtests, change points     (phase 3)
    models.py               baseline, regressions, predictive models    (phase 4)
    figures.py              every chart in the report                   (phase 4)
  scripts/                  download and sampling scripts (run on the laptop)
  app.py                    Streamlit dashboard: pick two openings, see the matchup and its history
  report/                   LaTeX dissertation; figures come straight from the pipeline
  tests/                    unit tests with hand-checked positions and games
  .github/workflows/ci.yml  lint, tests, and a small end-to-end run on a fixture PGN
```

Tests are written against positions where the right answer is known: specific move orders that must be
classified as the London, an IQP position, a known opposite-coloured bishop ending, a PGN with eval and clock
comments.

## 7. Report (dissertation style)

About 12,000 words, LaTeX, with every figure and table produced by the code.

1. Abstract
2. Introduction: motivation, research questions, contributions
3. Literature review: Elo and Glicko rating systems and draw models; opening theory and opening statistics;
   studies of online chess data; time-series forecasting and change-point detection
4. Data: sources, sampling, cleaning, descriptive statistics, ethics and licensing (CC0, no personal data used
   beyond public usernames, which are dropped)
5. Methodology: classification, features, baseline, models, evaluation design
6. Results: openings (6.1), middlegame (6.2), endgames (6.3), time series (6.4), prediction (6.5)
7. Discussion: what the results mean for players; how they compare with chess teaching
8. Limitations: online vs over-the-board chess, selection effects, missing engine analysis
9. Conclusion and future work
10. References and appendices (full opening tables, detector rules, extra figures)

## 8. Timeline

Applications come first (Deloitte deadlines 16 and 19 October, Capgemini 30 October), so the heavy work starts
in November. Phase 1 is done now because it needs no data download.

| Phase | Work | When |
|---|---|---|
| 1 | Repository, opening catalogue classifier, setup detectors, streaming PGN parser, tests, CI | Now |
| 2 | Download sample on the laptop; middlegame and endgame features | Week 1 of November |
| 3 | Explorer time series, forecasting backtests, change points | Week 2 |
| 4 | Baseline and models, figures, dashboard | Week 3 |
| 5 | Report writing and checking | Week 4 |

## 9. Risks

| Risk | Mitigation |
|---|---|
| Data volume (30 GB a month) | Stream and sample; never decompress whole files to disk |
| Sampling bias from taking the first games of a month | Compare against one fully streamed month |
| Transpositions mislabel openings | Classify by position, not move order; setup detectors are move-order independent |
| Engine evaluations only in a minority of games | Use them only for RQ2's eval-change measure and RQ5's in-game model; report how representative they are |
| Explorer rate limits | Cache every response; request only the positions the time series needs |
| Results read as causal ("play the London to win more") | Every result reported against the rating baseline, with confidence intervals and a stated causal caveat |
| Small effects | Expected. Reporting a small, precise effect honestly is a valid result |
