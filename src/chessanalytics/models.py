"""Result models that can be tested for chess sense, not only for accuracy.

`OrdinalResultModel` predicts loss / draw / win for White with two gradient-boosted binary models on the ordered
result: P(White does not lose) and P(White wins). Each binary model takes monotonic constraints, so "a higher
rating gap never lowers White's chances" is built in rather than hoped for, and the three probabilities always
sum to 1 with P(win) <= P(not lose).

Two models are trained by scripts/train_models.py and saved in models/:

- pregame: rating difference, mean rating, speed;
- ingame20: the same plus, after move 20, the material balance and each player's clock as a share of the
  starting time.

tests/test_models.py checks them on held-out November 2020 games.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
SPEEDS = ["bullet", "blitz", "rapid", "classical"]

# feature -> monotonic direction for White's result (+1 increasing, -1 decreasing, 0 free)
PREGAME = {"diff": 1, "mean": 0, "spd": 0}
INGAME20 = {"diff": 1, "mean": 0, "spd": 0, "mat": 1, "wclk": 1, "bclk": -1, "base": 0, "inc": 0}
# features that change sign / swap places when the colours are swapped
MIRROR = {"diff": "neg", "mat": "neg", "wclk": "bclk", "bclk": "wclk"}


def _hgb(features: dict[str, int], seed: int) -> HistGradientBoostingClassifier:
    names = list(features)
    return HistGradientBoostingClassifier(
        max_iter=200, learning_rate=0.1, max_leaf_nodes=31, early_stopping=True, random_state=seed,
        monotonic_cst=[features[f] for f in names],
        categorical_features=[i for i, f in enumerate(names) if f == "spd"] or None)


@dataclass
class OrdinalResultModel:
    features: dict[str, int]
    seed: int = 0
    not_lose: HistGradientBoostingClassifier | None = field(default=None, repr=False)
    win: HistGradientBoostingClassifier | None = field(default=None, repr=False)

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> OrdinalResultModel:
        """y: 0 White loses, 1 draw, 2 White wins."""
        X = X[list(self.features)]
        self.not_lose = _hgb(self.features, self.seed).fit(X, (y >= 1).astype(int))
        self.win = _hgb(self.features, self.seed).fit(X, (y == 2).astype(int))
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Columns: P(White loses), P(draw), P(White wins)."""
        X = X[list(self.features)]
        nl = self.not_lose.predict_proba(X)[:, 1]
        w = np.minimum(self.win.predict_proba(X)[:, 1], nl)
        return np.column_stack([1 - nl, nl - w, w])


def mirror(X: pd.DataFrame) -> pd.DataFrame:
    """The same positions with the colours swapped (ratings, material and clocks)."""
    m = X.copy()
    for f, how in MIRROR.items():
        if f in X:
            m[f] = -X[f] if how == "neg" else X[how]
    return m


def speed_code(speed: pd.Series) -> np.ndarray:
    return pd.Categorical(speed.astype(str), categories=SPEEDS).codes.astype("int8")


def save(model: OrdinalResultModel, name: str, directory: Path = MODELS_DIR) -> None:
    import joblib
    import sklearn

    directory.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, directory / f"{name}.joblib", compress=3)
    (directory / f"{name}.json").write_text(json.dumps(
        {"features": model.features, "sklearn": sklearn.__version__}, indent=2))


def load(name: str, directory: Path = MODELS_DIR) -> OrdinalResultModel:
    import joblib
    import sklearn

    meta = json.loads((directory / f"{name}.json").read_text())
    if meta["sklearn"].split(".")[:2] != sklearn.__version__.split(".")[:2]:
        raise RuntimeError(f"{name} was saved with scikit-learn {meta['sklearn']} but {sklearn.__version__} is "
                           "installed; retrain with scripts/train_models.py or install the saved version")
    return joblib.load(directory / f"{name}.joblib")
