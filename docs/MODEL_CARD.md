# Model card: chess result models

Two models that give the chances of a White win, a draw and a Black win in an online chess game. They are used by
the "What are my chances?" calculator in the dashboard and tested in `tests/test_models.py`. Code:
`src/chessanalytics/models.py`; training: `scripts/train_models.py`; saved models: `models/`.

## What they predict

| Model | Inputs | When |
|---|---|---|
| `pregame` | rating difference (White minus Black), average rating, speed (bullet, blitz, rapid, classical) | before the first move |
| `ingame20` | the same, plus after move 20: material balance (pawn 1, knight and bishop 3, rook 5, queen 9), each player's clock as a share of the starting time, starting time and increment | after move 20 |

Output: three probabilities that sum to 1.

## How they work

Each model is two gradient-boosted tree classifiers (scikit-learn `HistGradientBoostingClassifier`) on the ordered
result: one for "White does not lose", one for "White wins". The draw chance is the gap between them. Both have
**monotonic constraints**: a higher rating difference, more material or more time on White's clock can only raise
White's chances, and more time on Black's clock can only lower them. This is part of the model, not something
that happened to come out of training, and a test checks that it holds even for a model trained on random noise.

## Data

- Lichess rated games (CC0), the first 1 GB of the September, October and November 2020 monthly files, which
  covers roughly the first one to two days of each month.
- Kept: rated bullet, blitz, rapid and classical games that ended normally or on time, at least 5 moves, both
  players rated. The in-game model also needs the game to reach move 20 with clock times recorded.
- Training: 600,000 games sampled from September and October 2020. Test: 50,000 games sampled from November 2020,
  so the models are always judged on games played after their training data. The test games are saved with the
  models.
- Test mix: about 51% blitz, 33 to 35% bullet, 13 to 14% rapid, 1% classical.
- Player names are not used or stored.

## Performance on the November 2020 test games

| Model | Accuracy | Log loss | Knowing nothing: accuracy / log loss |
|---|---|---|---|
| `pregame` | 54.8% | 0.808 | 49.9% / 0.835 |
| `ingame20` | 65.2% | 0.750 | 48.7% / 0.852 |

Accuracy is the share of games where the most likely result was the actual one. "Knowing nothing" always predicts
the overall share of White wins, draws and Black wins.

**Calibration.** In every group of at least 1,000 games with similar predicted chances, the predicted chance of each
result is within 1.6 percentage points (pre-game) and 1.9 points (after move 20) of how often it happened. The
average predicted draw chance is 4.2% (actual 4.1%) before the game and 5.0% (actual 4.8%) after move 20.

**Colour symmetry.** Swapping the colours turns White's win chance into Black's, apart from White's first-move
edge, which the models put at 3.4 points before the game and 4.6 points after move 20.

These numbers are close to the larger models in `docs/RESULTS.md` (55.0% before the game and 65.1% after move 20,
trained on 1.5 million games), so the smaller saved models lose almost nothing.

## Tests

`tests/test_models.py` fails the build if any of these break: valid probabilities; the monotonic constraints;
colour symmetry; common-sense cases (400 points stronger wins over 75%; a queen up on real games wins over 80%;
in bullet, being far behind on the clock costs at least 15 points); accuracy and log loss no worse than the levels
above; the saved models still reproduce their recorded metrics; and calibration within 3 points.

## Limits

- **2020 online games only.** Ratings are Lichess ratings, which are not comparable with FIDE or chess.com
  ratings, and the player pool has changed since the 2020 chess boom. The models have not been checked on later
  years.
- **A few days per month.** The sample covers the start of each month, not the whole month.
- **Draws are rare (about 4 to 5% of games),** so neither model named a draw as the most likely result for any test game;
  accuracy therefore says little about draws. Use the draw probability instead. Because the two halves of each
  model are trained separately, the draw chance can be squeezed close to zero for some inputs (under 1% for 8% of
  the in-game test games).
- **Not symmetric everywhere.** At individual inputs the models can treat the two colours unevenly: with equal
  ratings and clocks, a queen up gives White an 85% win chance, but a queen down gives a 73% chance of losing.
  On real games a queen or more down, the average predicted chance of losing is accurate (78% against 79%).
- **The in-game model sees only material and clocks**, not the position itself, so it cannot see a mating attack
  or a trapped piece.
- **Associations, not advice.** The models describe what happened in past games. They are not a chess engine and
  should not be used to judge a position, to decide anything about a player, or for betting.

## Retraining

The saved models need scikit-learn 1.8. After an upgrade, or with new data:

```bash
python scripts/train_models.py --data data
python -m pytest tests/test_models.py
```
