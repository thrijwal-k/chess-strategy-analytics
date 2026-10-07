"""Endgame detection and classification, plus the per-game feature pass over a stored games table."""
import random

import chess
import pandas as pd
import pytest

from chessanalytics import endgame as eg
from chessanalytics.features import SNAPSHOT_FIELDS, game_features


@pytest.mark.parametrize("fen,expected", [
    ("8/5kp1/8/8/8/8/5PK1/8 w - - 0 1", "Pawn endgame"),
    ("8/5kp1/8/8/8/8/r4PK1/R7 w - - 0 1", "Rook endgame"),
    ("r7/5kp1/r7/8/8/8/R4PK1/R7 w - - 0 1", "Double rook endgame"),
    ("2b2k2/8/8/8/8/8/8/2B2K2 w - - 0 1", "Opposite-coloured bishops"),
    ("5b1k/8/8/8/8/8/8/2B2K2 w - - 0 1", "Same-coloured bishops"),
    ("5n1k/8/8/8/8/8/8/2N2K2 w - - 0 1", "Knight endgame"),
    ("5n1k/8/8/8/8/8/8/2B2K2 w - - 0 1", "Bishop vs knight"),
    ("5q1k/8/8/8/8/8/8/2Q2K2 w - - 0 1", "Queen endgame"),
    ("5n1k/8/8/8/8/8/8/2R2K2 w - - 0 1", "Rook vs minor piece"),
    ("4rn1k/8/8/8/8/8/8/2RB1K2 w - - 0 1", "Rook and minor endgame"),
    ("5r1k/8/8/8/8/8/8/2Q2K2 w - - 0 1", "Queen vs other pieces"),
    ("7k/6pp/8/8/8/8/8/2N2K2 w - - 0 1", "Pieces vs pawns"),
    ("5bnk/8/8/8/8/8/8/1NB2K2 w - - 0 1", "Minor pieces (two or more)"),
])
def test_endgame_types(fen, expected):
    assert eg.classify(chess.Board(fen)) == expected


def test_every_type_is_in_the_category_list():
    assert {"Mixed", "Pawn endgame", "Opposite-coloured bishops"} <= set(eg.CATEGORIES)


def test_threshold():
    assert not eg.is_endgame(chess.Board())
    assert eg.piece_points(chess.Board(), chess.WHITE) == 31
    two_rooks_and_minor_each = chess.Board("r1b1k2r/8/8/8/8/8/8/R1B1K2R w - - 0 1")
    assert eg.is_endgame(two_rooks_and_minor_each)  # 13 + 13 = 26
    queen_and_rook_each = chess.Board("r2qk3/8/8/8/8/8/8/R2QK3 w - - 0 1")
    assert not eg.is_endgame(queen_and_rook_each)  # 14 + 14 = 28


def test_entry_balances():
    e = eg.entry_for(chess.Board("8/5kp1/8/8/8/8/r3PPK1/R7 w - - 0 1"), ply=60)
    assert (e.category, e.pawn_balance, e.material_balance, e.pieces_total) == ("Rook endgame", 1, 1, 7)


def _random_game(seed: int, plies: int = 200) -> list[str]:
    """A legal random game: captures are preferred so it reaches an endgame."""
    rng = random.Random(seed)
    b, out = chess.Board(), []
    while not b.is_game_over() and len(out) < plies:
        moves = list(b.legal_moves)
        captures = [m for m in moves if b.is_capture(m)]
        m = rng.choice(captures or moves)
        out.append(b.san(m))
        b.push(m)
    return out


@pytest.mark.parametrize("seed", range(5))
def test_game_features_agree_with_an_independent_replay(seed):
    moves = _random_game(seed)
    f = game_features(" ".join(moves))
    assert f["feature_error"] == ""
    b, first = chess.Board(), None
    for ply, san in enumerate(moves, start=1):
        b.push_san(san)
        if first is None and eg.is_endgame(b):
            first = ply
            assert f["endgame_type"] == eg.classify(b)
    assert f["endgame_ply"] == first
    names = {n for n, _ in SNAPSHOT_FIELDS}
    assert names <= set(f)


def test_features_pipeline_over_a_games_table(tmp_path):
    from chessanalytics.extract import main as extract_main
    from chessanalytics.features import main as features_main

    pgn = tmp_path / "g.pgn"
    games = [" ".join(_random_game(s)) for s in range(30)]
    pgn.write_text("\n\n".join(
        f'[Event "Rated Blitz game"]\n[Site "https://lichess.org/x{i}"]\n[Result "*"]\n[WhiteElo "1500"]\n'
        f'[BlackElo "1500"]\n[TimeControl "180+0"]\n\n{g} *' for i, g in enumerate(games)) + "\n")
    extract_main([str(pgn), "--out", str(tmp_path / "games.parquet"), "--progress", "0"])
    assert features_main([str(tmp_path / "games.parquet"), "--out", str(tmp_path / "f.parquet")]) == 0
    df = pd.read_parquet(tmp_path / "f.parquet")
    assert len(df) == 30 and (df["feature_error"] == "").all()
    assert "moves" not in df.columns and "w_iqp_m15" in df.columns
    assert df["endgame_type"].isin([*eg.CATEGORIES, ""]).all()  # "" = the game never reached an endgame
    assert (df["endgame_type"] != "").any()
