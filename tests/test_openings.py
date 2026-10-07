"""Named-opening classification against the full Lichess catalogue."""
import pytest

from chessanalytics.openings import default_classifier, load_catalogue


@pytest.fixture(scope="module")
def clf():
    return default_classifier()


def name(clf, moves: str) -> str:
    op = clf.classify(moves.split())
    return op.name if op else ""


def test_whole_catalogue_loads_and_every_line_is_legal(clf):
    cat = load_catalogue()
    assert len(cat) == clf.size > 3800
    assert len({o.eco for o in cat}) == 500
    assert {o.volume for o in cat} == set("ABCDE")


def test_every_catalogue_line_classifies_to_itself(clf):
    """All 3,865 lines are replayed; each must come back with its own name (every opening is reachable)."""
    for op in load_catalogue():
        got = clf.classify([t for t in op.pgn.split() if not t[0].isdigit()])
        assert got is not None and got.name == op.name, op.pgn


@pytest.mark.parametrize("moves,expected", [
    ("e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6", "Sicilian Defense: Najdorf Variation"),
    ("e4 c6 d4 d5", "Caro-Kann Defense"),
    ("e4 e5 f4", "King's Gambit"),
    ("d4 d5 c4", "Queen's Gambit"),
    ("d4 Nf6 c4 g6 Nc3 Bg7 e4 d6", "King's Indian Defense: Normal Variation"),
    ("d4 d5 Nc3 Nf6 Bf4", "Rapport-Jobava System"),
])
def test_known_lines(clf, moves, expected):
    assert name(clf, moves) == expected


def test_transpositions_get_the_same_name(clf):
    a = name(clf, "Nf3 d5 d4 Nf6 c4 e6 Nc3")
    b = name(clf, "d4 d5 c4 e6 Nc3 Nf6 Nf3")
    assert a == b == "Queen's Gambit Declined: Three Knights Variation"


def test_deepest_named_position_wins_after_leaving_book(clf):
    # the game goes on with unusual moves; the label stays at the last named position
    assert name(clf, "e4 e5 f4 exf4 a3 a6 h3 h6") == name(clf, "e4 e5 f4 exf4")


def test_london_is_split_across_catalogue_families(clf):
    """Why setup detectors are needed: one system, several catalogue families."""
    fams = {clf.classify(m.split()).family for m in (
        "d4 d5 Bf4", "d4 Nf6 Nf3 e6 Bf4", "d4 Nf6 Nf3 g6 Bf4", "d4 f5 Bf4")}
    assert len(fams) >= 3


def test_no_moves_means_no_opening(clf):
    assert clf.classify([]) is None
