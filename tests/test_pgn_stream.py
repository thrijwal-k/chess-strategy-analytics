"""Streaming PGN reader: headers, moves, eval and clock comments, zstd, sampling budgets."""
import random
from pathlib import Path

import pytest
import zstandard

from chessanalytics.extract import extract, game_row
from chessanalytics.pgn_stream import MATE_SCORE, Game, iter_games, parse_movetext, speed_from_time_control

FIXTURE = Path(__file__).parent / "fixtures" / "sample_lichess.pgn"


@pytest.fixture(scope="module")
def games():
    return list(iter_games(FIXTURE))


def test_reads_every_game(games):
    assert len(games) == 5
    assert [g.result for g in games] == [1.0, 0.0, 0.5, 0.0, None]


def test_eval_and_clock_comments_attach_to_the_right_ply(games):
    g = games[0]
    assert len(g.moves) == len(g.evals) == len(g.clocks) == 11
    assert g.evals[0] == pytest.approx(0.17) and g.clocks[0] == 180
    assert g.moves[7] == "Be7"  # '?!' annotation stripped
    assert g.evals[7] == pytest.approx(0.9) and g.clocks[7] == 170


def test_mate_scores_keep_sign_and_distance(games):
    g = games[1]
    assert g.evals[-2:] == [-MATE_SCORE, -MATE_SCORE]
    assert g.mates[-2:] == [-2, -1]


def test_variations_nags_and_line_comments_are_skipped(games):
    assert games[2].moves == ["d4", "d5", "c4", "e6", "Nc3", "Nf6", "Bg5", "Be7", "e3", "O-O", "Nf3", "h6"]
    assert not games[2].has_eval and not games[2].has_clock


def test_move_numbers_without_spaces_and_unknown_rating(games):
    assert games[3].moves == ["e4", "c6", "d4", "d5", "e5", "Bf5"]
    assert games[3].white_elo is None and games[3].black_elo == 1500


@pytest.mark.parametrize("tc,speed", [
    ("15+0", "ultrabullet"), ("60+0", "bullet"), ("180+2", "blitz"), ("600+0", "rapid"),
    ("1800+20", "classical"), ("-", "correspondence"), ("bad", "unknown"),
])
def test_speed_categories(tc, speed):
    assert speed_from_time_control(tc) == speed


def test_eval_on_the_first_comment_before_any_move_is_ignored():
    g = Game({})
    parse_movetext("{ [%eval 0.3] } 1. e4 { [%eval 0.2] } *", g)
    assert g.moves == ["e4"] and g.evals == [0.2]


def _zst(tmp_path, copies: int) -> Path:
    rng = random.Random(7)  # varied ids and ratings so the file does not compress into a single zstd block
    text = FIXTURE.read_text()
    raw = "\n".join(text.replace("AAAA", f"{rng.getrandbits(32):08x}").replace("1850", str(rng.randint(800, 2800)))
                     for _ in range(copies)).encode()
    path = tmp_path / "games.pgn.zst"
    path.write_bytes(zstandard.ZstdCompressor().compress(raw))
    return path


def test_zstd_stream_and_limit(tmp_path):
    path = _zst(tmp_path, 40)
    assert sum(1 for _ in iter_games(path)) == 200
    assert sum(1 for _ in iter_games(path, limit=17)) == 17


def test_byte_budget_samples_the_start_without_errors(tmp_path):
    path = _zst(tmp_path, 4000)
    full = path.stat().st_size
    sampled = list(iter_games(path, max_bytes=full // 4))
    assert 0 < len(sampled) < 20000
    assert all(g.headers.get("Result") for g in sampled)  # the possibly cut-off last game is dropped


def test_game_row_has_no_usernames_and_labels_the_opening(games):
    row = game_row(games[0])
    assert "player_a" not in str(row.values())
    assert row["white_setup"] == "London System" and row["black_setup"].startswith("Dutch")
    assert row["family"] == "Dutch Defense" and row["rating_diff"] == 60 and row["month"] == "2020-10"


def test_extract_end_to_end():
    df = extract(str(FIXTURE))
    assert len(df) == 5 and (df["error"] == "").all()
    assert set(df["speed"]) == {"blitz", "rapid", "classical", "bullet", "correspondence"}


def test_streamed_parquet_and_csv_match_and_no_partial_file_is_left(tmp_path):
    import pandas as pd

    from chessanalytics.extract import main

    pq_out, csv_out = tmp_path / "g.parquet", tmp_path / "g.csv"
    path = _zst(tmp_path, 900)  # 4,500 games: more than one 2,000-game batch
    assert main([str(path), "--out", str(pq_out), "--progress", "0"]) == 0
    assert main([str(path), "--out", str(csv_out), "--progress", "0", "--workers", "2"]) == 0
    a, b = pd.read_parquet(pq_out), pd.read_csv(csv_out, keep_default_na=False)
    assert len(a) == len(b) == 4500
    assert list(a["white_setup"]) == list(b["white_setup"])
    assert not list(tmp_path.glob("*.partial"))


def test_moves_evals_and_clocks_round_trip_through_the_table(games):
    from chessanalytics.pgn_stream import decode_game

    for g in games:
        row = game_row(g)
        back = decode_game(row["moves"], row["evals"], row["clocks"])
        assert back.moves == g.moves
        assert back.evals == g.evals and back.mates == g.mates and back.clocks == g.clocks
