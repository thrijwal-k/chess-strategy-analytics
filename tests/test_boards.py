"""Chessboard diagrams: every opening line is legal, and every idea position shows what its caption says."""
import chess
import pandas as pd
import pytest

from chessanalytics.boards import IDEAS, OPENINGS, diagrams, ideas, matchup, opening
from chessanalytics.explainer import ALIASES, TABLES


@pytest.mark.parametrize("label", sorted(OPENINGS))
def test_every_opening_line_is_legal(label):
    d = opening(label)
    assert d is not None and d.svg.startswith("<svg") and d.caption.startswith(label)


def test_every_named_opening_has_a_board():
    labels = set(pd.read_csv(TABLES / "white_setups.csv", index_col=0).index) | set(
        pd.read_csv(TABLES / "black_defences.csv", index_col=0).index)
    catch_all = ("Other", "other", "Irregular", "Flank", "Symmetrical", "Reversed", "King's Pawn", "Queen's Pawn",
                 "Open Game", "Indian Defence (other)")
    missing = [x for x in labels if x not in OPENINGS and not any(c in x for c in catch_all)]
    assert not missing
    assert all(v in OPENINGS for v in ALIASES.values())  # every name the explainer recognises can be drawn


def test_lines_reach_the_opening_they_name():
    board = chess.Board()
    for san in OPENINGS["London System"].split():
        board.push_san(san)
    assert board.piece_at(chess.F4) == chess.Piece(chess.BISHOP, chess.WHITE)
    board = chess.Board()
    for san in OPENINGS["Dutch: Leningrad"].split():
        board.push_san(san)
    assert board.piece_at(chess.F5).symbol() == "p" and board.piece_at(chess.G7).symbol() == "b"


def _idea(word):
    _, fen, squares, _ = next(i for i in IDEAS if word in i[0])
    return chess.Board(fen), squares


def test_idea_positions_are_valid():
    for _, fen, squares, _ in IDEAS:
        board = chess.Board(fen)
        assert board.is_valid(), fen
        assert all(board.piece_at(chess.parse_square(s)) for s in squares)  # highlights point at pieces


def test_outpost_cannot_be_attacked_by_a_pawn():
    b, _ = _idea("outpost")
    assert b.piece_at(chess.D5).symbol() == "N"
    assert chess.E4 in b.attackers(chess.WHITE, chess.D5) and b.piece_at(chess.E4).symbol() == "P"
    black_pawns = b.pieces(chess.PAWN, chess.BLACK)
    # a black pawn could only ever attack d5 from c6 or e6, i.e. from the c- or e-file above rank 5
    assert not [s for s in black_pawns if chess.square_file(s) in (2, 4) and chess.square_rank(s) > 4]


def test_isolated_doubled_passed_and_bishops():
    b, _ = _idea("isolated")
    files = {chess.square_file(s) for s in b.pieces(chess.PAWN, chess.WHITE)}
    assert 3 in files and 2 not in files and 4 not in files
    b, _ = _idea("doubled")
    assert len([s for s in b.pieces(chess.PAWN, chess.WHITE) if chess.square_file(s) == 2]) == 2
    b, _ = _idea("passed")
    assert not [s for s in b.pieces(chess.PAWN, chess.BLACK) if chess.square_file(s) in (0, 1, 2)]
    b, _ = _idea("opposite-coloured")
    (wb,), (bb,) = b.pieces(chess.BISHOP, chess.WHITE), b.pieces(chess.BISHOP, chess.BLACK)
    assert (wb in chess.SquareSet(chess.BB_LIGHT_SQUARES)) != (bb in chess.SquareSet(chess.BB_LIGHT_SQUARES))
    b, _ = _idea("bishop pair")
    assert len(b.pieces(chess.BISHOP, chess.WHITE)) == 2 and len(b.pieces(chess.BISHOP, chess.BLACK)) == 0


def test_matchup_board_and_selection():
    d = matchup("London System", "Dutch")
    assert d.caption.endswith("1.d4 f5 2.Bf4 Nf6 3.e3 e6")
    boards = diagrams("Is the London good against the Dutch?", ["London System", "Dutch"], {"London System"})
    assert [b.caption.split(":")[0] for b in boards] == ["London System against Dutch", "London System", "Dutch"]
    assert diagrams("What is the weather?", [], set()) == []
    assert [d.caption.split(":")[0] for d in ideas("Why do rooks like open files? What is a fianchetto?")] == [
        "Fianchetto"]
