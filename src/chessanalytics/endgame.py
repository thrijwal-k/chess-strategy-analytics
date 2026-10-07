"""Endgame detection and classification by remaining material.

Definition used throughout the report: a game *enters the endgame* at the first position where the combined
non-pawn material of both sides is at most ENDGAME_THRESHOLD points (knight = bishop = 3, rook = 5, queen = 9).
The starting position has 62 points. With the default of 26, two rooks and a minor piece each (26) or a queen and
a minor piece each (24) count as an endgame, a queen and rook each (28) does not.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import chess

VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
ENDGAME_THRESHOLD = 26

CATEGORIES = [
    "Pawn endgame",
    "Rook endgame",
    "Double rook endgame",
    "Opposite-coloured bishops",
    "Same-coloured bishops",
    "Knight endgame",
    "Bishop vs knight",
    "Queen endgame",
    "Rook vs minor piece",
    "Rook and minor endgame",
    "Queen vs other pieces",
    "Pieces vs pawns",
    "Minor pieces (two or more)",
    "Mixed",
]


def piece_points(board: chess.Board, color: chess.Color) -> int:
    """Non-pawn material in points."""
    return sum(len(board.pieces(pt, color)) * VALUES[pt]
               for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN))


def material(board: chess.Board, color: chess.Color) -> int:
    return piece_points(board, color) + len(board.pieces(chess.PAWN, color))


def is_endgame(board: chess.Board, threshold: int = ENDGAME_THRESHOLD) -> bool:
    return piece_points(board, chess.WHITE) + piece_points(board, chess.BLACK) <= threshold


def _pieces(board: chess.Board, color: chess.Color) -> dict[int, int]:
    return {pt: len(board.pieces(pt, color)) for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)}


def classify(board: chess.Board) -> str:
    """Endgame type from the pieces left on the board (pawns and kings ignored)."""
    w, b = _pieces(board, chess.WHITE), _pieces(board, chess.BLACK)
    nw, nb = sum(w.values()), sum(b.values())
    if nw == 0 and nb == 0:
        return "Pawn endgame"
    if nw == 0 or nb == 0:
        return "Pieces vs pawns"

    def only(side: dict[int, int], **want: int) -> bool:
        names = {"n": chess.KNIGHT, "b": chess.BISHOP, "r": chess.ROOK, "q": chess.QUEEN}
        target = {names[k]: v for k, v in want.items()}
        return all(side[pt] == target.get(pt, 0) for pt in side)

    if only(w, r=1) and only(b, r=1):
        return "Rook endgame"
    if only(w, r=2) and only(b, r=2):
        return "Double rook endgame"
    if only(w, b=1) and only(b, b=1):
        wsq = next(iter(board.pieces(chess.BISHOP, chess.WHITE)))
        bsq = next(iter(board.pieces(chess.BISHOP, chess.BLACK)))
        same = _is_light(wsq) == _is_light(bsq)
        return "Same-coloured bishops" if same else "Opposite-coloured bishops"
    if only(w, n=1) and only(b, n=1):
        return "Knight endgame"
    if (only(w, b=1) and only(b, n=1)) or (only(w, n=1) and only(b, b=1)):
        return "Bishop vs knight"
    if only(w, q=1) and only(b, q=1):
        return "Queen endgame"
    minor_only = {chess.KNIGHT, chess.BISHOP}
    w_minor = nw == w[chess.KNIGHT] + w[chess.BISHOP]
    b_minor = nb == b[chess.KNIGHT] + b[chess.BISHOP]
    if (only(w, r=1) and b_minor and nb == 1) or (only(b, r=1) and w_minor and nw == 1):
        return "Rook vs minor piece"
    if (w[chess.ROOK] == 1 and b[chess.ROOK] == 1 and nw == 2 and nb == 2
            and all(pt in minor_only for pt in _non_rook(w)) and all(pt in minor_only for pt in _non_rook(b))):
        return "Rook and minor endgame"
    if (w[chess.QUEEN] >= 1) != (b[chess.QUEEN] >= 1):
        return "Queen vs other pieces"
    if w_minor and b_minor:
        return "Minor pieces (two or more)"
    return "Mixed"


def _is_light(sq: int) -> bool:
    return bool(chess.BB_SQUARES[sq] & chess.BB_LIGHT_SQUARES)


def _non_rook(side: dict[int, int]) -> list[int]:
    return [pt for pt, n in side.items() if pt != chess.ROOK for _ in range(n)]


def opposite_coloured_bishops_only(board: chess.Board) -> bool:
    return classify(board) == "Opposite-coloured bishops"


@dataclass
class EndgameEntry:
    ply: int  # number of moves played when the endgame was entered (0 = starting position)
    category: str
    pawn_balance: int  # White pawns minus Black pawns
    material_balance: int  # White minus Black, in points including pawns
    pieces_total: int  # all men on the board including kings (7 or fewer = tablebase territory)
    fen: str


def find_entry(moves: Iterable[str], threshold: int = ENDGAME_THRESHOLD) -> EndgameEntry | None:
    """First position of the game that is an endgame, or None if the game never reaches one."""
    board = chess.Board()
    for ply, san in enumerate(moves, start=1):
        board.push_san(san)
        if is_endgame(board, threshold):
            return entry_for(board, ply)
    return None


def entry_for(board: chess.Board, ply: int) -> EndgameEntry:
    return EndgameEntry(
        ply=ply,
        category=classify(board),
        pawn_balance=len(board.pieces(chess.PAWN, chess.WHITE)) - len(board.pieces(chess.PAWN, chess.BLACK)),
        material_balance=material(board, chess.WHITE) - material(board, chess.BLACK),
        pieces_total=chess.popcount(board.occupied),
        fen=board.fen(),
    )


# ---------------------------------------------------------------------------------------------------------------
# Settled endgame types. The material at the instant the threshold is crossed is often mid-exchange (a queen has
# just been taken and the recapture is one move away). For the textbook comparisons we want the material balance
# once the exchanges are over, so a type only counts once the same material has stood for STABLE_PLIES plies.

STABLE_PLIES = 4
KEY_TYPES = {
    "Pawn endgame": "pawn",
    "Rook endgame": "rook",
    "Double rook endgame": "rook2",
    "Opposite-coloured bishops": "ocb",
    "Same-coloured bishops": "scb",
    "Knight endgame": "knight",
    "Bishop vs knight": "bvn",
    "Queen endgame": "queen",
    "Rook vs minor piece": "rvm",
    "Rook and minor endgame": "rm",
}


def _signature(board: chess.Board) -> tuple:
    light = chess.BB_LIGHT_SQUARES
    return tuple(len(board.pieces(pt, c)) for c in (chess.WHITE, chess.BLACK)
                 for pt in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)) + (
        chess.popcount(board.pieces_mask(chess.BISHOP, chess.WHITE) & light),
        chess.popcount(board.pieces_mask(chess.BISHOP, chess.BLACK) & light))


def settled_endgames(moves: Iterable[str], start_fen: str = chess.STARTING_FEN) -> dict:
    """For each key endgame type: the first ply at which it was reached and held for STABLE_PLIES plies, with the
    pawn and material balance (White minus Black) at that point. Also the first settled endgame of any type."""
    out: dict = {}
    for short in KEY_TYPES.values():
        out[f"{short}_ply"] = None
        out[f"{short}_pawns"] = None
        out[f"{short}_material"] = None
    out.update(settled_ply=None, settled_type="", settled_pawns=None, settled_material=None, final_type="")
    board = chess.Board(start_fen)
    sig, since, recorded = None, 0, False
    for ply, san in enumerate(moves, start=1):
        board.push_san(san)
        s = _signature(board)
        if s != sig:
            sig, since, recorded = s, ply, False
            continue
        if recorded or ply - since + 1 < STABLE_PLIES or not is_endgame(board):
            continue
        recorded = True
        cat = classify(board)
        pawns = len(board.pieces(chess.PAWN, chess.WHITE)) - len(board.pieces(chess.PAWN, chess.BLACK))
        mat = material(board, chess.WHITE) - material(board, chess.BLACK)
        start = since  # the position the material settled at
        if out["settled_ply"] is None:
            out.update(settled_ply=start, settled_type=cat, settled_pawns=pawns, settled_material=mat)
        out["final_type"] = cat
        short = KEY_TYPES.get(cat)
        if short and out[f"{short}_ply"] is None:
            out[f"{short}_ply"], out[f"{short}_pawns"], out[f"{short}_material"] = start, pawns, mat
    return out
