# Analysis scripts

Reproduce every table in `docs/tables` and figure in `docs/figures` from the project root:

```bash
set CHESS_DATA=data            # Windows (or export CHESS_DATA=data); folder holding features/, setups/, endgames/,
                               # clocks/ and explorer/
python analysis/build_core.py      # one table of 9.8 million filtered games with the rating baseline (results/)
python analysis/rq1_openings.py    # opening effects, matchups, London by rating, Elo calibration
python analysis/rq2_middlegame.py  # middlegame features at move 20, draw rates by castling and queen trades
python analysis/rq3_endgames.py    # settled endgames: draw and conversion rates
python analysis/rq4_trends.py      # opening trends 2013-2026, Queen's Gambit check, forecasting backtests
python analysis/rq5_prediction.py  # result prediction before and during the game (material, engine, clocks)
python analysis/figures.py         # figures 1 to 9
```

Inputs come from the pipeline in `scripts/`: `sample_months.py` and `chessanalytics.features` (features),
`relabel_setups.py` (setups), `endgame_pass.py` (endgames), `extract_clocks.py` (clocks) and `fetch_explorer.py`
(explorer). Memory peaks at about 4 GB (build_core and rq5).
