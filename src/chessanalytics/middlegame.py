"""Middlegame strategy features measured on a single position, plus game-level timing features.

Every feature is computed for one side (`color`) so the analysis can compare White and Black. All functions
take a python-chess Board and are checked in tests/test_middlegame.py against positions with a known answer.
"""
from __future__ import annotations

from collections.abc import Iterable

import chess

from .endgame import material

CENTRE = [chess.D4, chess.E4, chess.D5, chess.E5]


def _files_with_pawns(board: chess.Board, color: chess.Color) -> dict[int, list[int]]:
    """file index -> list of squares holding a pawn of `color`."""
    out: dict[int, list[int]] = {}
    for sq in board.pieces(chess.PAWN, color):
        out.setdefault(chess.square_file(sq), []).append(sq)
    return out


def isolated_pawns(board: chess.Board, color: chess.Color) -> int:
    files = _files_with_pawns(board, color)
    return sum(len(sqs) for f, sqs in files.items() if f - 1 not in files and f + 1 not in files)


def doubled_pawns(board: chess.Board, color: chess.Color) -> int:
    """Extra pawns on files that hold two or more (a tripled file counts 2)."""
    return sum(len(sqs) - 1 for sqs in _files_with_pawns(board, color).values() if len(sqs) > 1)


def pawn_islands(board: chess.Board, color: chess.Color) -> int:
    files = sorted(_files_with_pawns(board, color))
    return sum(1 for i, f in enumerate(files) if i == 0 or f != files[i - 1] + 1)


def is_passed(board: chess.Board, sq: int, color: chess.Color) -> bool:
    """No enemy pawn ahead on the same or an adjacent file."""
    f, r = chess.square_file(sq), chess.square_rank(sq)
    for esq in board.pieces(chess.PAWN, not color):
        ef, er = chess.square_file(esq), chess.square_rank(esq)
        if abs(ef - f) <= 1 and (er > r if color == chess.WHITE else er < r):
            return False
    return True


def passed_pawns(board: chess.Board, color: chess.Color) -> int:
    return sum(is_passed(board, sq, color) for sq in board.pieces(chess.PAWN, color))


def backward_pawns(board: chess.Board, color: chess.Color) -> int:
    """A pawn whose neighbours on adjacent files are all further advanced, and whose stop square is attacked by
    an enemy pawn, so it cannot advance safely or be defended by a pawn."""
    count = 0
    step = 8 if color == chess.WHITE else -8
    for sq in board.pieces(chess.PAWN, color):
        f, r = chess.square_file(sq), chess.square_rank(sq)
        stop = sq + step
        if not 0 <= stop < 64:
            continue
        neighbours = [s for s in board.pieces(chess.PAWN, color) if abs(chess.square_file(s) - f) == 1]
        if not neighbours:
            continue  # isolated, counted separately
        behind_or_level = [s for s in neighbours
                           if (chess.square_rank(s) <= r if color == chess.WHITE else chess.square_rank(s) >= r)]
        if behind_or_level:
            continue
        enemy_pawn_attacks = board.attackers(not color, stop) & board.pieces(chess.PAWN, not color)
        if enemy_pawn_attacks:
            count += 1
    return count


def isolated_queen_pawn(board: chess.Board, color: chess.Color) -> bool:
    """IQP: a d-pawn with no friendly pawns on the c- or e-file."""
    files = _files_with_pawns(board, color)
    return 3 in files and 2 not in files and 4 not in files


def hanging_pawns(board: chess.Board, color: chess.Color) -> bool:
    """c- and d-pawns side by side with no friendly pawns on the b- or e-file."""
    files = _files_with_pawns(board, color)
    if not (2 in files and 3 in files) or 1 in files or 4 in files:
        return False
    return any(chess.square_rank(c) == chess.square_rank(d) for c in files[2] for d in files[3])


def bishop_pair(board: chess.Board, color: chess.Color) -> bool:
    bishops = board.pieces(chess.BISHOP, color)
    light = any(chess.BB_SQUARES[s] & chess.BB_LIGHT_SQUARES for s in bishops)
    dark = any(chess.BB_SQUARES[s] & chess.BB_DARK_SQUARES for s in bishops)
    return light and dark


def bad_bishop_share(board: chess.Board, color: chess.Color) -> float | None:
    """For a side with exactly one bishop: share of its own pawns standing on the bishop's colour (high = bad)."""
    bishops = list(board.pieces(chess.BISHOP, color))
    pawns = list(board.pieces(chess.PAWN, color))
    if len(bishops) != 1 or not pawns:
        return None
    light = chess.BB_SQUARES[bishops[0]] & chess.BB_LIGHT_SQUARES
    colour_mask = chess.BB_LIGHT_SQUARES if light else chess.BB_DARK_SQUARES
    return sum(1 for p in pawns if chess.BB_SQUARES[p] & colour_mask) / len(pawns)


def knight_outposts(board: chess.Board, color: chess.Color) -> int:
    """Knights on the opponent's side of the board (ranks 4-6 for White, 3-5 for Black), protected by a pawn and
    impossible for an enemy pawn to attack now or later."""
    count = 0
    for sq in board.pieces(chess.KNIGHT, color):
        f, r = chess.square_file(sq), chess.square_rank(sq)
        if not (3 <= r <= 5 if color == chess.WHITE else 2 <= r <= 4):
            continue
        if not board.attackers(color, sq) & board.pieces(chess.PAWN, color):
            continue
        can_be_hit = False
        for esq in board.pieces(chess.PAWN, not color):
            ef, er = chess.square_file(esq), chess.square_rank(esq)
            if abs(ef - f) == 1 and (er > r if color == chess.WHITE else er < r):
                can_be_hit = True
                break
        count += not can_be_hit
    return count


def rooks_on_open_files(board: chess.Board, color: chess.Color) -> tuple[int, int]:
    """(rooks on fully open files, rooks on half-open files: no own pawn but an enemy pawn)."""
    own, enemy = _files_with_pawns(board, color), _files_with_pawns(board, not color)
    open_, half = 0, 0
    for sq in board.pieces(chess.ROOK, color):
        f = chess.square_file(sq)
        if f not in own:
            if f in enemy:
                half += 1
            else:
                open_ += 1
    return open_, half


def rooks_on_seventh(board: chess.Board, color: chess.Color) -> int:
    rank = 6 if color == chess.WHITE else 1
    return sum(1 for sq in board.pieces(chess.ROOK, color) if chess.square_rank(sq) == rank)


def king_side(board: chess.Board, color: chess.Color) -> str:
    """'kingside', 'queenside' or 'centre' from the king's file."""
    f = chess.square_file(board.king(color))
    return "kingside" if f >= 5 else "queenside" if f <= 2 else "centre"


def pawn_shield(board: chess.Board, color: chess.Color) -> int:
    """Own pawns on the king's file and the two next to it, one or two ranks in front of the king (0-6)."""
    k = board.king(color)
    kf, kr = chess.square_file(k), chess.square_rank(k)
    direction = 1 if color == chess.WHITE else -1
    count = 0
    for f in (kf - 1, kf, kf + 1):
        if not 0 <= f <= 7:
            continue
        for d in (1, 2):
            r = kr + d * direction
            if 0 <= r <= 7 and board.piece_at(chess.square(f, r)) == chess.Piece(chess.PAWN, color):
                count += 1
    return count


def open_files_near_king(board: chess.Board, color: chess.Color) -> int:
    """Files next to or under the king with no pawn of the king's own side."""
    kf = chess.square_file(board.king(color))
    own = _files_with_pawns(board, color)
    return sum(1 for f in (kf - 1, kf, kf + 1) if 0 <= f <= 7 and f not in own)


def centre_control(board: chess.Board, color: chess.Color) -> int:
    """Attacks on d4, e4, d5, e5 plus occupation of them by own pawns."""
    attacks = sum(len(board.attackers(color, sq)) for sq in CENTRE)
    occupied = sum(1 for sq in CENTRE if board.piece_at(sq) == chess.Piece(chess.PAWN, color))
    return attacks + occupied


def space(board: chess.Board, color: chess.Color) -> int:
    """Squares in the opponent's half of the board attacked by this side."""
    half = chess.BB_RANK_5 | chess.BB_RANK_6 | chess.BB_RANK_7 | chess.BB_RANK_8 if color == chess.WHITE else \
        chess.BB_RANK_1 | chess.BB_RANK_2 | chess.BB_RANK_3 | chess.BB_RANK_4
    attacked = 0
    for sq in chess.scan_forward(board.occupied_co[color]):
        attacked |= board.attacks_mask(sq)
    return chess.popcount(attacked & half)


def developed_minors(board: chess.Board, color: chess.Color) -> int:
    """Knights and bishops no longer on their own back rank."""
    back = chess.BB_RANK_1 if color == chess.WHITE else chess.BB_RANK_8
    minors = board.pieces(chess.KNIGHT, color) | board.pieces(chess.BISHOP, color)
    return sum(1 for sq in minors if not chess.BB_SQUARES[sq] & back)


def position_features(board: chess.Board, color: chess.Color) -> dict:
    open_r, half_r = rooks_on_open_files(board, color)
    return {
        "material": material(board, color),
        "isolated": isolated_pawns(board, color),
        "doubled": doubled_pawns(board, color),
        "backward": backward_pawns(board, color),
        "passed": passed_pawns(board, color),
        "islands": pawn_islands(board, color),
        "iqp": isolated_queen_pawn(board, color),
        "hanging": hanging_pawns(board, color),
        "bishop_pair": bishop_pair(board, color),
        "bad_bishop": bad_bishop_share(board, color),
        "outposts": knight_outposts(board, color),
        "rooks_open": open_r,
        "rooks_half_open": half_r,
        "rooks_7th": rooks_on_seventh(board, color),
        "king_side": king_side(board, color),
        "pawn_shield": pawn_shield(board, color),
        "open_files_near_king": open_files_near_king(board, color),
        "centre": centre_control(board, color),
        "space": space(board, color),
        "developed_minors": developed_minors(board, color),
    }


def game_timing(moves: Iterable[str]) -> dict:
    """When each side castled (and to which side), and when the queens came off."""
    board = chess.Board()
    out = {"white_castled": "", "black_castled": "", "white_castle_ply": None, "black_castle_ply": None,
           "queens_off_ply": None}
    for ply, san in enumerate(moves, start=1):
        move = board.parse_san(san)
        side = "white" if board.turn == chess.WHITE else "black"
        if board.is_castling(move) and not out[f"{side}_castled"]:
            out[f"{side}_castled"] = "kingside" if chess.square_file(move.to_square) > 4 else "queenside"
            out[f"{side}_castle_ply"] = ply
        board.push(move)
        if out["queens_off_ply"] is None and not board.pieces(chess.QUEEN, chess.WHITE) \
                and not board.pieces(chess.QUEEN, chess.BLACK):
            out["queens_off_ply"] = ply
    out["opposite_side_castling"] = bool(out["white_castled"] and out["black_castled"]
                                         and out["white_castled"] != out["black_castled"])
    return out
