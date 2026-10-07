"""Tests for the saved result models (models/, made by scripts/train_models.py).

Three kinds of check on 50,000 held-out November 2020 games per model:
- behaviour: valid probabilities, monotonic in rating gap, material and clocks, colour-swap symmetry,
  common-sense scenarios;
- quality gates: accuracy and log loss no worse than the levels reported in docs/RESULTS.md, and clearly better
  than knowing nothing;
- calibration: predicted win chances match how often White actually won.
"""
import json

import numpy as np
import pandas as pd
import pytest

from chessanalytics.models import MODELS_DIR, OrdinalResultModel, load, mirror

NAMES = ["pregame", "ingame20"]


@pytest.fixture(scope="module", params=NAMES)
def saved(request):
    name = request.param
    return name, load(name), pd.read_parquet(MODELS_DIR / f"{name}_test.parquet")


def accuracy(P, y):
    return float((P.argmax(1) == y).mean())


def log_loss(P, y):
    return float(-np.mean(np.log(np.clip(P[np.arange(len(y)), y], 1e-15, 1))))


def sweep(model, rows: pd.DataFrame, feature: str, values) -> np.ndarray:
    """Predictions for each row with `feature` set to each value: shape (rows, values, 3)."""
    out = []
    for v in values:
        x = rows.copy()
        x[feature] = v
        out.append(model.predict_proba(x))
    return np.stack(out, axis=1)


# ---- behaviour ---------------------------------------------------------------------------------------------------

def test_probabilities_are_valid(saved):
    _, model, t = saved
    P = model.predict_proba(t)
    assert P.shape == (len(t), 3)
    assert np.all(P >= -1e-9) and np.all(P <= 1 + 1e-9)
    assert np.allclose(P.sum(1), 1)


@pytest.mark.parametrize("feature,values,direction", [
    ("diff", np.arange(-800, 801, 50), 1),
    ("mat", np.arange(-9, 10, 1), 1),
    ("wclk", np.linspace(0, 1, 11), 1),
    ("bclk", np.linspace(0, 1, 11), -1),
])
def test_monotonic(saved, feature, values, direction):
    """More rating, material or clock for White never lowers White's win chance or raises the loss chance."""
    _, model, t = saved
    if feature not in model.features:
        pytest.skip(f"{feature} is not in this model")
    S = sweep(model, t.sample(300, random_state=0), feature, values)
    win, loss = np.diff(S[..., 2], axis=1) * direction, np.diff(S[..., 0], axis=1) * direction
    assert win.min() >= -1e-9 and loss.max() <= 1e-9
    assert (S[:, -1, 2] - S[:, 0, 2]).mean() * direction > 0.2  # and the feature matters


def test_colour_swap_symmetry(saved):
    """Swapping colours turns White's win chance into Black's, apart from White's small first-move edge."""
    _, model, t = saved
    P, Q = model.predict_proba(t), model.predict_proba(mirror(t))
    first_move_edge = (P[:, 2] - Q[:, 0]).mean()
    assert 0 < first_move_edge < 0.08
    assert np.abs(P[:, 2] - Q[:, 0]).mean() < 0.07
    assert np.abs(P[:, 1] - Q[:, 1]).mean() < 0.03


def test_common_sense_scenarios():
    pre, ing = load("pregame"), load("ingame20")
    even = pd.DataFrame({"diff": [0.0], "mean": [1500.0], "spd": [1]})  # blitz, equal ratings
    p = pre.predict_proba(even)[0]
    assert abs(p[2] - p[0]) < 0.1 and p[1] < 0.1  # close to a coin flip, few draws
    assert pre.predict_proba(even.assign(diff=400.0))[0, 2] > 0.75
    assert pre.predict_proba(even.assign(diff=-400.0))[0, 0] > 0.75
    pos = even.assign(mat=0.0, wclk=0.5, bclk=0.5, base=180.0, inc=0.0)
    assert ing.predict_proba(pos.assign(mat=9.0))[0, 2] > 0.7  # a queen up
    assert ing.predict_proba(pos.assign(mat=-9.0))[0, 0] > 0.7  # a queen down
    # on real held-out games a queen or more up / down
    t = pd.read_parquet(MODELS_DIR / "ingame20_test.parquet")
    assert ing.predict_proba(t[t.mat >= 8])[:, 2].mean() > 0.8
    assert ing.predict_proba(t[t.mat <= -8])[:, 0].mean() > 0.75
    # in bullet, being far behind on the clock is costly even with equal material
    bullet = pos.assign(spd=0, base=60.0, wclk=0.05, bclk=0.6)
    assert ing.predict_proba(bullet)[0, 2] < ing.predict_proba(pos.assign(spd=0, base=60.0))[0, 2] - 0.15


def test_constraints_survive_retraining():
    """Monotonicity comes from the model design, not luck: a model trained on pure noise still respects it."""
    rng = np.random.default_rng(1)
    X = pd.DataFrame({"diff": rng.normal(0, 200, 4000), "mean": rng.normal(1500, 300, 4000),
                      "spd": rng.integers(0, 4, 4000)})
    m = OrdinalResultModel({"diff": 1, "mean": 0, "spd": 0}).fit(X, rng.integers(0, 3, 4000))
    S = sweep(m, X.head(50), "diff", np.arange(-600, 601, 50))
    assert np.diff(S[..., 2], axis=1).min() >= -1e-9 and np.diff(S[..., 0], axis=1).max() <= 1e-9


# ---- quality gates -------------------------------------------------------------------------------------------------

GATES = {  # docs/RESULTS.md: 55.0% before the game, 65.1% after move 20 with material and clocks
    "pregame": {"accuracy": 0.54, "log_loss": 0.815},
    "ingame20": {"accuracy": 0.64, "log_loss": 0.76},
}


def test_quality_gates(saved):
    name, model, t = saved
    P, y = model.predict_proba(t), t.y.values
    assert accuracy(P, y) >= GATES[name]["accuracy"]
    assert log_loss(P, y) <= GATES[name]["log_loss"]
    no_info = np.bincount(y, minlength=3) / len(y)
    assert log_loss(P, y) < log_loss(np.tile(no_info, (len(y), 1)), y) - 0.02


def test_saved_metrics_match(saved):
    """The saved model and test sample still give the numbers recorded when they were trained."""
    name, model, t = saved
    m = json.loads((MODELS_DIR / "metrics.json").read_text())[name]
    P = model.predict_proba(t)
    assert accuracy(P, t.y.values) == pytest.approx(m["accuracy"], abs=1e-6)
    assert log_loss(P, t.y.values) == pytest.approx(m["log_loss"], abs=1e-6)


def test_position_beats_ratings_alone():
    pre, ing = load("pregame"), load("ingame20")
    t = pd.read_parquet(MODELS_DIR / "ingame20_test.parquet")
    assert accuracy(ing.predict_proba(t), t.y.values) > accuracy(pre.predict_proba(t), t.y.values) + 0.05


# ---- calibration --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("outcome", [0, 1, 2])
def test_calibrated(saved, outcome):
    _, model, t = saved
    p = model.predict_proba(t)[:, outcome]
    g = pd.DataFrame({"p": p, "o": t.y.values == outcome}).groupby(pd.cut(p, np.linspace(0, 1, 11)), observed=True)
    c = g.agg(p=("p", "mean"), o=("o", "mean"), n=("o", "size"))
    c = c[c.n >= 1000]
    assert len(c) >= 1
    assert (c.p - c.o).abs().max() < 0.03, c
