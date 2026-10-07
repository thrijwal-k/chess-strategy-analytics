# How to read this project's numbers

## What this project is
This project measures how much the opening, the middlegame and the endgame affect the result of a chess game, using
about 10 million rated Lichess games from September to November 2020, plus monthly opening statistics from 2013 to
2026. The main finding is that the opening matters far less than the players' ratings.

## Edge and the rating prediction
The edge is how far a result is above or below what the players' ratings predict. The prediction comes from all games
with the same rating gap, rating level and time control. An edge of +1.0 pp for White means White scored one percentage
point more than the ratings predicted, for example 52.2% instead of 51.2%. A negative edge means Black did better than
expected.

## Percentage points (pp)
A percentage point is the plain difference between two percentages. Going from 51% to 52% is a rise of 1 percentage
point. The edges in this project are small: the largest opening edges are about 4 pp, while a 100-point rating gap is
worth about 10 pp.

## Confidence interval
The plus-or-minus number after an edge (for example +0.8 ± 0.8 pp) is a 95% confidence interval: the range in which
the true value probably lies. If the range includes zero, the edge cannot be told apart from zero, and the matchup is
effectively even once ratings are accounted for.

## Statistically distinguishable from zero
An effect is distinguishable from zero when its whole confidence interval is above zero or below zero. London against
the Dutch Defence (+0.8 ± 0.8 pp) is not; London against the King's Indian (−2.2 ± 0.5 pp) is.

## Association is not causation
These results show what tends to go together, not what causes what. Stronger play produces both good positions and
wins, so a feature linked to winning is not proof that aiming for it will make someone win.

## Monthly share of an opening
The share of an opening in a month is the number of games that reached its position divided by all rated games that
month. Using shares rather than counts keeps months comparable while Lichess grew from about 0.1 million to 90 million
games a month.

## The Queen's Gambit effect
After the Netflix series The Queen's Gambit was released on 23 October 2020, the share of games reaching the Queen's
Gambit rose from 4.07% in October to 4.30% in November 2020, a jump about five times the usual month-to-month change,
mostly among players rated under 1600. It faded by spring 2021.

## Forecasting and backtesting
Forecasting predicts future monthly shares. Backtesting checks a forecasting method fairly: train it only on months up
to a point, predict the next 12 months, compare with what happened, and repeat. MASE below 1 means the method beats the
simple guess "same as the same month last year".

## Change points and interrupted time series
A change point is a month where a series suddenly shifts. An interrupted time series compares a series before and
after a known event, such as the Netflix release, to see whether its level or trend changed.

## Prediction accuracy and log loss
Accuracy is the share of games where the most likely predicted result was the actual one. Log loss scores the
predicted probabilities themselves and is lower when a model is both right and confident; lower is better. Ratings
alone predict 55% of results before the game; material, engine evaluation and clock times at move 25 predict 74.7%.

## Engine evaluation
An engine evaluation is a chess computer's judgement of a position in pawns: +1.0 means White is about a pawn better.
Lichess stores evaluations only for games someone asked it to analyse, about 6% of games.

## Clock times
Clock times are how much time each player has left. In bullet chess they matter almost as much as material: adding
them to a model at move 20 raises bullet prediction accuracy by 8 percentage points.
