"""Named-opening classification using the Lichess opening catalogue (CC0).

A game is replayed and labelled with the *deepest* catalogue position it reaches. Positions are matched by EPD
(the board without move counters), not by move order, so transpositions get the same name. This follows the
catalogue's own advice: "play moves backwards until a named position is found".
"""
from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import chess

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "openings"


@dataclass(frozen=True)
class Opening:
    eco: str
    name: str
    pgn: str
    ply: int

    @property
    def family(self) -> str:
        """'Sicilian Defense: Najdorf Variation' -> 'Sicilian Defense'."""
        return self.name.split(":")[0].strip()

    @property
    def volume(self) -> str:
        """ECO volume letter A to E."""
        return self.eco[0]


def _san_moves(pgn: str) -> list[str]:
    return [tok for tok in pgn.split() if not tok[0].isdigit()]


def load_catalogue(directory: Path | str = DEFAULT_DIR) -> list[Opening]:
    out: list[Opening] = []
    for f in sorted(Path(directory).glob("[a-e].tsv")):
        with f.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                out.append(Opening(row["eco"], row["name"], row["pgn"], len(_san_moves(row["pgn"]))))
    if not out:
        raise FileNotFoundError(f"no catalogue files (a.tsv to e.tsv) in {directory}")
    return out


def _key(board: chess.Board) -> tuple:
    """Position identity (pieces, side to move, castling rights, legal en passant): the same information as an
    EPD, but much faster than building an EPD string for every ply of millions of games."""
    return board._transposition_key()


class OpeningClassifier:
    def __init__(self, catalogue: Iterable[Opening] | None = None):
        cat = list(catalogue) if catalogue is not None else load_catalogue()
        self.by_epd: dict[str, Opening] = {}
        self.by_key: dict[tuple, Opening] = {}
        for op in cat:
            board = chess.Board()
            for san in _san_moves(op.pgn):
                board.push_san(san)
            epd = board.epd()
            # several lines can reach one position; keep the shortest (the name's defining line)
            if epd not in self.by_epd or op.ply < self.by_epd[epd].ply:
                self.by_epd[epd] = op
                self.by_key[_key(board)] = op
        self.max_ply = max(op.ply for op in cat)
        self.size = len(cat)

    def classify(self, san_moves: Iterable[str]) -> Opening | None:
        """Deepest named position reached within the catalogue's longest line. None if not even move 1 is named."""
        board = chess.Board()
        found = None
        for i, san in enumerate(san_moves):
            if i >= self.max_ply:
                break
            board.push_san(san)
            found = self.by_key.get(_key(board), found)
        return found


@lru_cache(maxsize=1)
def default_classifier() -> OpeningClassifier:
    return OpeningClassifier()
