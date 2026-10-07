"""Chessboard diagrams for the explainer, so a beginner can see what an opening or idea looks like.

Openings are drawn from a typical move sequence (checked for legality by python-chess), and ideas such as a knight
outpost or an isolated queen pawn from a hand-made position with the key squares highlighted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import chess
import chess.svg

# label (as in docs/tables and the explainer's aliases) -> a typical sequence of moves reaching it
OPENINGS: dict[str, str] = {
    # White systems
    "London System": "d4 d5 Bf4 Nf6 e3 e6 Nf3 c5 c3 Nc6 Nbd2",
    "Jobava London": "d4 d5 Nc3 Nf6 Bf4",
    "Queen's Gambit": "d4 d5 c4",
    "King's Gambit": "e4 e5 f4",
    "Scotch Game": "e4 e5 Nf3 Nc6 d4",
    "Italian Game": "e4 e5 Nf3 Nc6 Bc4",
    "Ruy Lopez": "e4 e5 Nf3 Nc6 Bb5",
    "Catalan": "d4 Nf6 c4 e6 g3 d5 Bg2",
    "English Opening": "c4",
    "Réti Opening": "Nf3 d5 c4",
    "Colle / Zukertort": "d4 d5 Nf3 Nf6 e3 e6 Bd3",
    "Trompowsky Attack": "d4 Nf6 Bg5",
    "Torre Attack": "d4 Nf6 Nf3 e6 Bg5",
    "Vienna Game": "e4 e5 Nc3",
    "Smith-Morra Gambit": "e4 c5 d4 cxd4 c3",
    "Alapin Sicilian": "e4 c5 c3",
    "Open Sicilian": "e4 c5 Nf3 d6 d4 cxd4 Nxd4",
    "Closed Sicilian": "e4 c5 Nc3 Nc6 g3",
    "Grand Prix Attack": "e4 c5 Nc3 Nc6 f4",
    "Rossolimo / Moscow": "e4 c5 Nf3 Nc6 Bb5",
    "Bird Opening": "f4",
    "King's Indian Attack": "Nf3 d5 g3 Nf6 Bg2 e6 O-O Be7 d3",
    "Bishop's Opening": "e4 e5 Bc4",
    "Blackmar-Diemer Gambit": "d4 d5 e4 dxe4 Nc3 Nf6 f3",
    "Veresov Attack": "d4 d5 Nc3 Nf6 Bg5",
    "Nimzo-Larsen Attack": "b3",
    # Black defences
    "Sicilian Defence": "e4 c5",
    "Caro-Kann Defence": "e4 c6 d4 d5",
    "French Defence": "e4 e6 d4 d5",
    "Scandinavian Defence": "e4 d5",
    "Pirc / Modern Defence": "e4 d6 d4 Nf6 Nc3 g6",
    "Alekhine Defence": "e4 Nf6",
    "King's Indian Defence": "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6",
    "Grünfeld Defence": "d4 Nf6 c4 g6 Nc3 d5",
    "Nimzo-Indian Defence": "d4 Nf6 c4 e6 Nc3 Bb4",
    "Queen's Indian Defence": "d4 Nf6 c4 e6 Nf3 b6",
    "Bogo-Indian Defence": "d4 Nf6 c4 e6 Nf3 Bb4+",
    "Slav Defence": "d4 d5 c4 c6",
    "Semi-Slav Defence": "d4 d5 c4 c6 Nc3 Nf6 Nf3 e6",
    "Queen's Gambit Declined": "d4 d5 c4 e6",
    "Queen's Gambit Accepted": "d4 d5 c4 dxc4",
    "Benoni Defence": "d4 Nf6 c4 c5 d5 e6",
    "Benko Gambit": "d4 Nf6 c4 c5 d5 b5",
    "Budapest Gambit": "d4 Nf6 c4 e5",
    "Englund Gambit": "d4 e5",
    "Dutch": "d4 f5 c4 Nf6 g3 e6",
    "Dutch: Stonewall": "d4 f5 c4 Nf6 g3 e6 Bg2 d5 Nf3 c6 O-O Bd6",
    "Dutch: Leningrad": "d4 f5 c4 Nf6 g3 g6 Bg2 Bg7",
    "Dutch: Classical / other": "d4 f5 c4 Nf6 g3 e6 Bg2 Be7",
    "Petrov Defence": "e4 e5 Nf3 Nf6",
    "Philidor Defence": "e4 e5 Nf3 d6",
    "Berlin Defence": "e4 e5 Nf3 Nc6 Bb5 Nf6",
    "Two Knights Defence": "e4 e5 Nf3 Nc6 Bc4 Nf6",
    "Old Indian Defence": "d4 Nf6 c4 d6",
    "Modern Defence (vs 1.d4)": "d4 g6",
}

# idea -> (words that ask about it, position, squares to highlight, caption)
IDEAS: list[tuple[tuple[str, ...], str, tuple[str, ...], str]] = [
    (("fianchetto",), "rnbqkb1r/ppp1pppp/5n2/3p4/8/5NP1/PPPPPPBP/RNBQK2R b KQkq - 3 3", ("g2",),
     "Fianchetto: White's bishop on g2, on the long diagonal behind the g3 pawn"),
    (("castl",), "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQ1RK1 b kq - 5 4", ("g1", "f1"),
     "After White castles kingside: king on g1, rook on f1"),
    (("outpost",), "r2q1rk1/pp2bppp/3p1n2/3Np3/4P3/8/PPP2PPP/R2QKB1R w KQ - 0 12", ("d5",),
     "Knight outpost: the knight on d5 is protected by a pawn and no black pawn can attack it"),
    (("isolated", "iqp"), "r1bq1rk1/pp2bppp/2n1pn2/8/3P4/2NB1N2/PP3PPP/R1BQ1RK1 w - - 0 10", ("d4",),
     "Isolated queen pawn: White's d4 pawn has no pawns beside it on the c- or e-file"),
    (("passed",), "8/5kpp/8/1P6/8/8/5KPP/8 w - - 0 40", ("b5",),
     "Passed pawn: no black pawn can stop the b5 pawn on its way to promotion"),
    (("doubled",), "8/5kpp/8/8/8/2P5/2P2KPP/8 w - - 0 40", ("c2", "c3"),
     "Doubled pawns: two white pawns on the same file (c2 and c3)"),
    (("opposite-coloured", "opposite-colored", "opposite coloured", "opposite colored"),
     "8/5k2/4b3/3p4/3P2P1/4B3/5K2/8 w - - 0 45", ("e3", "e6"),
     "Opposite-coloured bishops: White's bishop moves on dark squares, Black's on light squares, so they never meet"),
    (("bishop pair",), "r2qk2r/pp3ppp/2n1pn2/3p4/3P4/3B1N2/PPPB1PPP/R2QK2R w KQkq - 0 10", ("d2", "d3"),
     "Bishop pair: White still has both bishops (d2 and d3); Black has none left"),
]


@dataclass
class Diagram:
    caption: str
    svg: str


def _play(moves: str) -> tuple[chess.Board, chess.Move | None, str]:
    board, last, sans = chess.Board(), None, []
    for i, san in enumerate(moves.split()):
        last = board.push_san(san)
        sans.append(f"{i // 2 + 1}.{san}" if i % 2 == 0 else san)
    return board, last, " ".join(sans)


def opening(label: str, size: int = 280) -> Diagram | None:
    if label not in OPENINGS:
        return None
    board, last, text = _play(OPENINGS[label])
    return Diagram(f"{label}: {text}", chess.svg.board(board, lastmove=last, size=size, coordinates=True))


def matchup(white: str, black: str, size: int = 280) -> Diagram | None:
    """White's moves from its system and Black's from its defence, played in turn while they stay legal."""
    if white not in OPENINGS or black not in OPENINGS:
        return None
    w = OPENINGS[white].split()[0::2]
    b = OPENINGS[black].split()[1::2]
    board, last, sans = chess.Board(), None, []
    for i in range(min(len(w), len(b)) * 2):
        san = (w if i % 2 == 0 else b)[i // 2]
        try:
            last = board.push_san(san)
        except ValueError:
            break
        sans.append(f"{i // 2 + 1}.{san}" if i % 2 == 0 else san)
    if len(sans) < 4:
        return None
    return Diagram(f"{white} against {black}: {' '.join(sans)}",
                   chess.svg.board(board, lastmove=last, size=size, coordinates=True))


def ideas(question: str, size: int = 280) -> list[Diagram]:
    q = question.lower()
    out = []
    for words, fen, squares, caption in IDEAS:
        if any(re.search(rf"\b{re.escape(w)}", q) for w in words):
            board = chess.Board(fen)
            fill = {chess.parse_square(s): "#f4d03f99" for s in squares}
            out.append(Diagram(caption, chess.svg.board(board, fill=fill, size=size, coordinates=True)))
    return out


def diagrams(question: str, entities: list[str], white_labels: set[str], max_boards: int = 3) -> list[Diagram]:
    """Boards for a question: the matchup if a White system and a Black defence are both named, then each opening,
    then any ideas mentioned."""
    whites = [e for e in entities if e in white_labels]
    blacks = [e for e in entities if e not in white_labels]
    out: list[Diagram] = []
    if whites and blacks:
        d = matchup(whites[0], blacks[0])
        if d:
            out.append(d)
    for e in dict.fromkeys(entities):
        d = opening(e)
        if d:
            out.append(d)
    out += ideas(question)
    return out[:max_boards]
