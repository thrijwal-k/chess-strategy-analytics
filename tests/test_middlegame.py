"""Middlegame features checked against hand-built positions with a known answer."""
import chess
import pytest

from chessanalytics import middlegame as mg

W, B = chess.WHITE, chess.BLACK


def board(fen: str) -> chess.Board:
    return chess.Board(fen)


IQP = "4k3/pp3ppp/4p3/8/3P4/8/PP3PPP/4K3 w - - 0 1"


def test_isolated_queen_pawn_structure():
    b = board(IQP)
    assert mg.isolated_queen_pawn(b, W) and not mg.isolated_queen_pawn(b, B)
    assert mg.isolated_pawns(b, W) == 1 and mg.isolated_pawns(b, B) == 0
    assert mg.pawn_islands(b, W) == 3 and mg.pawn_islands(b, B) == 2
    assert mg.passed_pawns(b, W) == 0  # the e6 pawn can still stop d4


def test_doubled_and_passed_pawns():
    b = board("4k3/8/8/8/8/2P5/2P5/4K3 w - - 0 1")
    assert mg.doubled_pawns(b, W) == 1 and mg.isolated_pawns(b, W) == 2 and mg.passed_pawns(b, W) == 2
    assert mg.passed_pawns(board("4k3/8/8/3P4/8/8/8/4K3 w - - 0 1"), W) == 1
    assert mg.passed_pawns(board("4k3/4p3/8/3P4/8/8/8/4K3 w - - 0 1"), W) == 0


def test_backward_pawn():
    # d3 is behind both neighbours (c4, e4) and d4 is covered by Black's c5 pawn
    b = board("4k3/8/8/2p5/2P1P3/3P4/8/4K3 w - - 0 1")
    assert mg.backward_pawns(b, W) == 1


def test_hanging_pawns():
    b = board("4k3/8/8/8/2PP4/8/P4PPP/4K3 w - - 0 1")
    assert mg.hanging_pawns(b, W) and not mg.isolated_queen_pawn(b, W)


def test_bishop_pair_and_bad_bishop():
    start = chess.Board()
    assert mg.bishop_pair(start, W) and mg.bishop_pair(start, B)
    # one dark-squared bishop (c1) with pawns on d4 and c3 (dark squares) and e4 (light)
    b = board("4k3/8/8/8/3PP3/2P5/8/2B1K3 w - - 0 1")
    assert not mg.bishop_pair(b, W)
    assert mg.bad_bishop_share(b, W) == pytest.approx(2 / 3)


def test_knight_outpost():
    b = board("4k3/5p2/3p4/3N4/4P3/8/8/4K3 w - - 0 1")
    assert mg.knight_outposts(b, W) == 1
    b = board("4k3/2p2p2/3p4/3N4/4P3/8/8/4K3 w - - 0 1")  # ...c6 can still kick the knight
    assert mg.knight_outposts(b, W) == 0


def test_rooks_on_files_and_seventh():
    b = board("4k3/1p6/8/8/8/8/P7/RR2K2R w - - 0 1")
    assert mg.rooks_on_open_files(b, W) == (1, 1)  # h1 open, b1 half-open, a1 behind its own pawn
    assert mg.rooks_on_seventh(board("4k3/R7/8/8/8/8/8/4K3 w - - 0 1"), W) == 1


def test_king_safety():
    castled = board("6k1/5ppp/8/8/8/8/5PPP/6K1 w - - 0 1")
    assert mg.king_side(castled, W) == "kingside" and mg.pawn_shield(castled, W) == 3
    assert mg.open_files_near_king(castled, W) == 0
    holed = board("6k1/5ppp/8/8/8/8/5P1P/6K1 w - - 0 1")
    assert mg.pawn_shield(holed, W) == 2 and mg.open_files_near_king(holed, W) == 1
    assert mg.king_side(chess.Board(), W) == "centre"


def test_centre_space_and_development():
    b = chess.Board()
    assert mg.centre_control(b, W) == 0 and mg.developed_minors(b, W) == 0
    b.push_san("e4")
    assert mg.centre_control(b, W) == 2  # occupies e4 and attacks d5
    b.push_san("e5")
    b.push_san("Nf3")
    assert mg.developed_minors(b, W) == 1
    assert mg.space(b, W) > mg.space(chess.Board(), W)


def test_castling_and_queen_trade_timing():
    t = mg.game_timing("e4 e5 Nf3 Nc6 Bc4 Bc5 O-O Nf6 d3 d6 Nc3 Bg4 h3 Bh5 Qe2 Qd7 Be3 O-O-O".split())
    assert t["white_castled"] == "kingside" and t["white_castle_ply"] == 7
    assert t["black_castled"] == "queenside" and t["black_castle_ply"] == 18
    assert t["opposite_side_castling"]
    assert mg.game_timing("e4 e5 d4 exd4 Qxd4 Qf6 Qxf6 Nxf6".split())["queens_off_ply"] == 8
