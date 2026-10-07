"""Setup detectors: label White's system and Black's defence independently of move order.

The catalogue name of a game depends on the exact move order, so the London System is split across at least
four catalogue families (Queen's Pawn Game, Indian Defense, London System, Dutch Defense...). For matchups such
as "London vs Dutch" we need to know what each side *set up*, so each side is described by where its pieces and
pawns first arrived and when, and simple rules are applied to that description.

Rules are checked in order and the first match wins. Every game gets a label: anything that no rule catches
falls back to a broad group such as "Queen's Pawn (other)".
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import chess

SETUP_MOVES = 10  # look at each side's first 10 moves


@dataclass
class SideSetup:
    """When (own move number, 1-based) each piece type first arrived on each square, plus castling."""

    arrivals: dict[str, int] = field(default_factory=dict)
    moves: list[str] = field(default_factory=list)

    def has(self, key: str, by: int = SETUP_MOVES) -> bool:
        """key is SAN-like: 'Bf4', 'Nf3', a pawn square like 'd4', or 'O-O' / 'O-O-O'."""
        return self.arrivals.get(key, 99) <= by

    def at(self, key: str) -> int:
        return self.arrivals.get(key, 99)

    def first(self) -> str | None:
        return self.moves[0] if self.moves else None

    def before(self, a: str, b: str) -> bool:
        """a happened, and either b never did or a came first."""
        return self.at(a) < 99 and self.at(a) < self.at(b)


def describe_sides(moves: Iterable[str], max_moves: int = SETUP_MOVES) -> tuple[SideSetup, SideSetup]:
    board = chess.Board()
    sides = (SideSetup(), SideSetup())
    for ply, san in enumerate(moves):
        if ply >= 2 * max_moves:
            break
        move = board.parse_san(san)
        side = sides[ply % 2]
        n = ply // 2 + 1
        piece = board.piece_at(move.from_square)
        if board.is_castling(move):
            key = "O-O" if chess.square_file(move.to_square) > 4 else "O-O-O"
        else:
            letter = piece.symbol().upper() if piece else "?"
            key = chess.square_name(move.to_square) if letter == "P" else letter + chess.square_name(move.to_square)
        side.arrivals.setdefault(key, n)
        side.moves.append(san)
        board.push(move)
    return sides


Rule = tuple[str, Callable[[SideSetup, SideSetup], bool]]


def _sicilian(w: SideSetup, b: SideSetup) -> bool:
    return w.first() == "e4" and b.at("c5") == 1


def _open_game(w: SideSetup, b: SideSetup) -> bool:
    return w.first() == "e4" and b.at("e5") == 1


def _no_c4_d4(w: SideSetup, by: int) -> bool:
    return not w.has("c4", by) and not w.has("d4", by)


def _kia(w: SideSetup, b: SideSetup) -> bool:
    return all(w.has(k, 6) for k in ("Nf3", "g3", "Bg2", "d3")) and _no_c4_d4(w, 6)


def _englund(w: SideSetup, b: SideSetup) -> bool:
    return w.first() == "d4" and b.at("e5") == 1


def _queen_pawn(w: SideSetup) -> bool:
    """1.d4, or 1.Nf3 / 1.c4 / 1.g3 followed quickly by d4 (a transposition into queen's pawn openings)."""
    return w.first() == "d4" or (w.first() in ("Nf3", "c4", "g3") and w.has("d4", 3))


WHITE_RULES: list[Rule] = [
    # 1.e4: open games
    ("King's Gambit", lambda w, b: _open_game(w, b) and w.at("f4") == 2),
    ("Vienna Game", lambda w, b: _open_game(w, b) and w.at("Nc3") == 2),
    # these three are defined by 2...Nc6; 2...d6 lines are the Philidor
    ("Scotch Game", lambda w, b: _open_game(w, b) and w.at("Nf3") == 2 and b.at("Nc6") == 2 and w.at("d4") == 3),
    ("Ruy Lopez", lambda w, b: _open_game(w, b) and w.at("Nf3") == 2 and b.at("Nc6") == 2 and w.at("Bb5") == 3),
    ("Italian Game", lambda w, b: _open_game(w, b) and w.at("Nf3") == 2 and b.at("Nc6") == 2 and w.at("Bc4") == 3),
    ("Bishop's Opening", lambda w, b: _open_game(w, b) and w.at("Bc4") == 2),
    ("Open Game: 2.Nf3 (other)", lambda w, b: _open_game(w, b) and w.at("Nf3") == 2),
    # 1.e4 c5: White's choice against the Sicilian
    ("Smith-Morra Gambit", lambda w, b: _sicilian(w, b) and w.at("d4") == 2 and w.at("c3") == 3),
    ("Alapin Sicilian", lambda w, b: _sicilian(w, b) and w.at("c3") == 2),
    ("Grand Prix Attack", lambda w, b: _sicilian(w, b) and w.has("f4", 3) and w.has("Nc3", 3) and not w.has("d4", 4)),
    ("Rossolimo / Moscow", lambda w, b: _sicilian(w, b) and w.at("Nf3") == 2 and w.at("Bb5") == 3),
    ("Open Sicilian", lambda w, b: _sicilian(w, b) and w.has("d4", 3) and w.has("Nf3", 3)),
    ("Closed Sicilian", lambda w, b: _sicilian(w, b) and w.at("Nc3") == 2 and not w.has("d4", 4)),
    ("King's Indian Attack", _kia),
    # queen's pawn systems
    # 1.d4 e5 (Englund) lines with Bf4, such as 2.dxe5 Nc6 3.Nf3 Qe7 4.Bf4, are not London set-ups
    ("Jobava London", lambda w, b: _queen_pawn(w) and w.has("Nc3", 3) and w.has("Bf4", 3) and not w.has("c4", 4)
     and not _englund(w, b)),
    ("London System", lambda w, b: _queen_pawn(w) and w.has("Bf4", 4) and w.before("Bf4", "c4") and not _englund(w, b)),
    ("Trompowsky Attack", lambda w, b: w.first() == "d4" and b.first() == "Nf6" and w.at("Bg5") == 2),
    ("Veresov Attack", lambda w, b: w.first() == "d4" and w.at("Nc3") == 2 and w.at("Bg5") == 3),
    ("Torre Attack", lambda w, b: _queen_pawn(w) and w.has("Nf3", 3) and w.has("Bg5", 3) and not w.has("c4", 3)),
    ("Blackmar-Diemer Gambit", lambda w, b: w.first() == "d4" and b.at("d5") == 1 and w.at("e4") == 2),
    ("Catalan", lambda w, b: _queen_pawn(w) and w.has("c4", 4) and w.has("g3", 5) and w.has("Bg2", 6)
     and b.has("d5", 4) and not b.has("f5", 2)),
    ("Queen's Gambit", lambda w, b: _queen_pawn(w) and w.has("c4", 3) and b.has("d5", 2)),
    ("Queen's Pawn: d4 + c4", lambda w, b: _queen_pawn(w) and w.has("c4", 3)),
    ("Colle / Zukertort", lambda w, b: _queen_pawn(w) and w.has("e3", 5) and w.has("Bd3", 5) and not w.has("c4", 5)),
    ("Queen's Pawn: kingside fianchetto", lambda w, b: _queen_pawn(w) and w.has("g3", 5) and w.has("Bg2", 6)),
    ("Queen's Pawn (other)", lambda w, b: _queen_pawn(w)),
    # flank openings
    ("English Opening", lambda w, b: w.first() == "c4"),
    ("Réti Opening", lambda w, b: w.first() == "Nf3"),
    ("Bird Opening", lambda w, b: w.first() == "f4"),
    ("Nimzo-Larsen Attack", lambda w, b: w.first() == "b3"),
    ("King's Pawn (1.e4)", lambda w, b: w.first() == "e4"),
]


def _vs_e4(w: SideSetup, b: SideSetup) -> bool:
    return w.first() == "e4"


def _vs_d4(w: SideSetup, b: SideSetup) -> bool:
    return _queen_pawn(w)


BLACK_RULES: list[Rule] = [
    # against 1.e4
    ("Sicilian Defence", lambda w, b: _vs_e4(w, b) and b.at("c5") == 1),
    ("French Defence", lambda w, b: _vs_e4(w, b) and b.at("e6") == 1),
    ("Caro-Kann Defence", lambda w, b: _vs_e4(w, b) and b.at("c6") == 1 and b.has("d5", 3)),
    ("Scandinavian Defence", lambda w, b: _vs_e4(w, b) and b.at("d5") == 1),
    ("Alekhine Defence", lambda w, b: _vs_e4(w, b) and b.at("Nf6") == 1),
    ("Pirc / Modern Defence", lambda w, b: _vs_e4(w, b) and b.first() in ("d6", "g6")),
    ("Petrov Defence", lambda w, b: _vs_e4(w, b) and b.at("e5") == 1 and w.at("Nf3") == 2 and b.at("Nf6") == 2),
    ("Philidor Defence", lambda w, b: _vs_e4(w, b) and b.at("e5") == 1 and w.at("Nf3") == 2 and b.at("d6") == 2),
    ("Berlin Defence", lambda w, b: _vs_e4(w, b) and b.at("e5") == 1 and w.at("Bb5") == 3 and b.at("Nf6") == 3),
    ("Two Knights Defence", lambda w, b: _vs_e4(w, b) and b.at("e5") == 1 and b.at("Nc6") == 2 and w.at("Bc4") == 3
     and b.at("Nf6") == 3),
    ("Open Game: 1...e5 (other)", lambda w, b: _vs_e4(w, b) and b.at("e5") == 1),
    ("Irregular vs 1.e4", lambda w, b: _vs_e4(w, b)),
    # setups Black can use against 1.d4 and against flank openings
    ("Dutch: Leningrad", lambda w, b: b.has("f5", 2) and b.has("g6", 4)),
    ("Dutch: Stonewall", lambda w, b: b.has("f5", 2) and b.has("d5", 5) and b.has("e6", 5)),
    ("Dutch: Classical / other", lambda w, b: b.has("f5", 2) and _vs_d4(w, b)),
    ("Benko Gambit", lambda w, b: _vs_d4(w, b) and b.has("Nf6", 2) and b.has("c5", 2) and b.has("b5", 3)),
    ("Budapest Gambit", lambda w, b: _vs_d4(w, b) and b.at("Nf6") == 1 and b.at("e5") == 2),
    ("Benoni Defence", lambda w, b: _vs_d4(w, b) and b.has("c5", 2) and b.has("Nf6", 2)),
    ("Grünfeld Defence", lambda w, b: b.has("Nf6", 2) and b.has("g6", 3) and b.has("d5", 4) and b.before("g6", "d5")),
    ("King's Indian Defence", lambda w, b: b.has("Nf6", 3) and b.has("g6", 4) and b.has("Bg7", 5) and b.has("d6", 6)
     and not b.has("d5", 5)),
    ("Nimzo-Indian Defence", lambda w, b: b.has("e6", 3) and b.has("Bb4", 4) and w.at("Nc3") <= b.at("Bb4")
     and w.has("c4", 4) and not b.has("d5", 3)),
    ("Bogo-Indian Defence", lambda w, b: _vs_d4(w, b) and b.has("e6", 3) and b.has("Bb4", 4) and not b.has("d5", 3)),
    ("Queen's Indian Defence", lambda w, b: _vs_d4(w, b) and b.has("e6", 3) and b.has("b6", 4) and not b.has("d5", 3)),
    ("Queen's Gambit Accepted", lambda w, b: _vs_d4(w, b) and b.has("d5", 2) and w.has("c4", 3) and b.has("c4", 3)),
    ("Semi-Slav Defence", lambda w, b: _vs_d4(w, b) and b.has("d5", 2) and b.has("c6", 4) and b.has("e6", 4)
     and w.has("c4", 4)),
    ("Slav Defence", lambda w, b: _vs_d4(w, b) and b.has("d5", 2) and b.has("c6", 3) and w.has("c4", 3)),
    ("Queen's Gambit Declined", lambda w, b: _vs_d4(w, b) and b.has("d5", 3) and b.has("e6", 3) and w.has("c4", 3)),
    ("Englund Gambit", lambda w, b: w.first() == "d4" and b.at("e5") == 1),
    ("Modern Defence (vs 1.d4)", lambda w, b: _vs_d4(w, b) and b.at("g6") == 1),
    ("Old Indian Defence", lambda w, b: _vs_d4(w, b) and b.at("Nf6") == 1 and b.at("d6") == 2),
    ("Queen's Pawn: 1...d5 (other)", lambda w, b: _vs_d4(w, b) and b.has("d5", 2)),
    ("Indian Defence (other)", lambda w, b: _vs_d4(w, b) and b.at("Nf6") == 1),
    ("Other vs 1.d4", lambda w, b: _vs_d4(w, b)),
    # replies to flank openings
    ("Symmetrical (1...c5)", lambda w, b: b.at("c5") == 1),
    ("Reversed Sicilian (1...e5)", lambda w, b: b.at("e5") == 1),
    ("Flank: 1...d5", lambda w, b: b.at("d5") == 1),
    ("Flank: 1...Nf6", lambda w, b: b.at("Nf6") == 1),
    ("Other defence", lambda w, b: True),
]


def _apply(rules: list[Rule], w: SideSetup, b: SideSetup, default: str) -> str:
    for name, rule in rules:
        if rule(w, b):
            return name
    return default


def classify_setups(san_moves: Iterable[str]) -> tuple[str, str]:
    """(White system, Black defence) for a game given as SAN moves."""
    w, b = describe_sides(san_moves)
    if not w.moves:
        return "No moves", "No moves"
    return _apply(WHITE_RULES, w, b, "Other"), _apply(BLACK_RULES, w, b, "Other defence")


WHITE_SYSTEMS = [n for n, _ in WHITE_RULES] + ["Other"]
BLACK_DEFENCES = [n for n, _ in BLACK_RULES]
