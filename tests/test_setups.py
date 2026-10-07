"""White system and Black defence detectors, including move-order independence."""
import pytest

from chessanalytics.setups import BLACK_DEFENCES, WHITE_SYSTEMS, classify_setups


def setups(moves: str) -> tuple[str, str]:
    return classify_setups(moves.split())


@pytest.mark.parametrize("moves,white,black", [
    # the matchups from the original idea that can happen on the board
    ("d4 f5 Bf4 Nf6 e3 e6", "London System", "Dutch: Classical / other"),
    ("d4 d5 c4 e6 Nc3 Nf6", "Queen's Gambit", "Queen's Gambit Declined"),
    ("e4 e5 f4 exf4", "King's Gambit", "Open Game: 1...e5 (other)"),
    # London move orders
    ("d4 d5 Bf4 Nf6 e3 e6 Nf3 c5 c3", "London System", "Queen's Pawn: 1...d5 (other)"),
    ("Nf3 Nf6 d4 e6 Bf4", "London System", "Indian Defence (other)"),
    ("d4 d5 Nc3 Nf6 Bf4", "Jobava London", "Queen's Pawn: 1...d5 (other)"),
    # 1.e4 defences and White's anti-Sicilians
    ("e4 c6 d4 d5", "King's Pawn (1.e4)", "Caro-Kann Defence"),
    ("e4 e6 d4 d5", "King's Pawn (1.e4)", "French Defence"),
    ("e4 d5 exd5", "King's Pawn (1.e4)", "Scandinavian Defence"),
    ("e4 Nf6", "King's Pawn (1.e4)", "Alekhine Defence"),
    ("e4 d6 d4 Nf6 Nc3 g6", "King's Pawn (1.e4)", "Pirc / Modern Defence"),
    ("e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6", "Open Sicilian", "Sicilian Defence"),
    ("e4 c5 c3", "Alapin Sicilian", "Sicilian Defence"),
    ("e4 c5 d4 cxd4 c3", "Smith-Morra Gambit", "Sicilian Defence"),
    ("e4 c5 Nc3 Nc6 g3", "Closed Sicilian", "Sicilian Defence"),
    ("e4 c5 Nc3 Nc6 f4", "Grand Prix Attack", "Sicilian Defence"),
    ("e4 c5 Nf3 Nc6 Bb5", "Rossolimo / Moscow", "Sicilian Defence"),
    # open games
    ("e4 e5 Nf3 Nc6 Bb5 Nf6", "Ruy Lopez", "Berlin Defence"),
    ("e4 e5 Nf3 Nc6 Bc4 Nf6", "Italian Game", "Two Knights Defence"),
    ("e4 e5 Nf3 Nc6 d4 exd4", "Scotch Game", "Open Game: 1...e5 (other)"),
    ("e4 e5 Nc3 Nf6", "Vienna Game", "Open Game: 1...e5 (other)"),
    ("e4 e5 Nf3 Nf6", "Open Game: 2.Nf3 (other)", "Petrov Defence"),
    ("e4 e5 Nf3 d6", "Open Game: 2.Nf3 (other)", "Philidor Defence"),
    # 1.d4 defences
    ("d4 Nf6 c4 g6 Nc3 Bg7 e4 d6", "Queen's Pawn: d4 + c4", "King's Indian Defence"),
    ("d4 Nf6 c4 g6 Nc3 d5", "Queen's Pawn: d4 + c4", "Grünfeld Defence"),
    ("d4 Nf6 c4 e6 Nc3 Bb4", "Queen's Pawn: d4 + c4", "Nimzo-Indian Defence"),
    ("d4 Nf6 c4 e6 Nf3 Bb4+", "Queen's Pawn: d4 + c4", "Bogo-Indian Defence"),
    ("d4 Nf6 c4 e6 Nf3 b6", "Queen's Pawn: d4 + c4", "Queen's Indian Defence"),
    ("d4 d5 c4 c6", "Queen's Gambit", "Slav Defence"),
    ("d4 d5 c4 c6 Nf3 Nf6 Nc3 e6", "Queen's Gambit", "Semi-Slav Defence"),
    ("d4 d5 c4 dxc4", "Queen's Gambit", "Queen's Gambit Accepted"),
    ("d4 Nf6 c4 c5 d5 b5", "Queen's Pawn: d4 + c4", "Benko Gambit"),
    ("d4 Nf6 c4 e5", "Queen's Pawn: d4 + c4", "Budapest Gambit"),
    ("d4 Nf6 c4 c5 d5 e6", "Queen's Pawn: d4 + c4", "Benoni Defence"),
    ("d4 f5 c4 Nf6 g3 g6 Bg2 Bg7", "Queen's Pawn: d4 + c4", "Dutch: Leningrad"),
    ("d4 f5 g3 Nf6 Bg2 e6 Nf3 d5 O-O Bd6 c4 c6", "Queen's Pawn: kingside fianchetto", "Dutch: Stonewall"),
    ("d4 e5", "Queen's Pawn (other)", "Englund Gambit"),
    # White systems
    ("d4 Nf6 c4 e6 g3 d5 Bg2", "Catalan", "Queen's Gambit Declined"),
    ("d4 d5 Nf3 Nf6 e3 e6 Bd3 c5 c3", "Colle / Zukertort", "Queen's Pawn: 1...d5 (other)"),
    ("d4 Nf6 Bg5", "Trompowsky Attack", "Indian Defence (other)"),
    ("d4 Nf6 Nf3 e6 Bg5", "Torre Attack", "Indian Defence (other)"),
    ("d4 d5 Nc3 Nf6 Bg5", "Veresov Attack", "Queen's Pawn: 1...d5 (other)"),
    ("d4 d5 e4", "Blackmar-Diemer Gambit", "Queen's Pawn: 1...d5 (other)"),
    ("Nf3 d5 g3 Nf6 Bg2 e6 O-O Be7 d3", "King's Indian Attack", "Flank: 1...d5"),
    ("c4 e5", "English Opening", "Reversed Sicilian (1...e5)"),
    ("c4 c5", "English Opening", "Symmetrical (1...c5)"),
    ("f4 d5", "Bird Opening", "Flank: 1...d5"),
    ("b3 e5", "Nimzo-Larsen Attack", "Reversed Sicilian (1...e5)"),
    ("g4 d5", "Other", "Flank: 1...d5"),
    # found by cross-checking labels against catalogue names on 10 million real games
    ("d4 e5 dxe5 Nc6 Nf3 Qe7 Bf4 Qb4+", "Queen's Pawn (other)", "Englund Gambit"),
    ("e4 e5 Nf3 d6 d4 exd4", "Open Game: 2.Nf3 (other)", "Philidor Defence"),
    ("e4 e5 Nf3 d6 Bc4 Be7", "Open Game: 2.Nf3 (other)", "Philidor Defence"),
    ("e4 e5 Nf3 d6 Bc4 Nf6", "Open Game: 2.Nf3 (other)", "Philidor Defence"),
])
def test_known_setups(moves, white, black):
    assert setups(moves) == (white, black)


def test_flank_move_order_transposing_to_queens_gambit():
    assert setups("Nf3 d5 d4 Nf6 c4 e6") == ("Queen's Gambit", "Queen's Gambit Declined")


def test_kings_indian_against_the_english_is_still_a_kings_indian():
    assert setups("c4 Nf6 Nc3 g6 e4 d6 Nf3 Bg7")[1] == "King's Indian Defence"


def test_impossible_pairings_never_appear():
    """London vs Caro-Kann and Queen's Gambit vs King's Gambit cannot happen: both labels need 1.d4 vs 1.e4."""
    assert setups("e4 c6 d4 d5 Bf4")[0] != "London System"
    assert setups("d4 c6 Bf4 d5")[1] != "Caro-Kann Defence"


def test_every_game_gets_a_label_from_the_known_lists():
    for moves in ("a3 a6", "h4 h5 Rh3", "e4", "Nc3 Nf6"):
        w, b = setups(moves)
        assert w in WHITE_SYSTEMS and b in BLACK_DEFENCES


def test_empty_game():
    assert classify_setups([]) == ("No moves", "No moves")
