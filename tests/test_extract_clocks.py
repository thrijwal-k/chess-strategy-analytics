"""Clock extraction picks each player's clock after their own Nth move."""
import importlib.util
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

spec = importlib.util.spec_from_file_location("extract_clocks", Path(__file__).parents[1] / "scripts/extract_clocks.py")
ec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ec)


def test_clock_positions():
    clocks = " ".join(str(1000 - i) for i in range(60))  # ply 1 -> 1000, ply 2 -> 999, ...
    out = ec.clocks_at(clocks)
    assert out[:2] == [1000 - 18, 1000 - 19]  # move 10: White's 10th move is ply 19, Black's is ply 20
    assert out[-2:] == [1000 - 48, 1000 - 49]  # move 25


def test_short_games_and_missing_clocks():
    assert ec.clocks_at("") == [None] * 8
    assert ec.clocks_at("60 60 58 59")[0] is None  # game shorter than 10 moves
    long_with_gap = ["60"] * 50
    long_with_gap[18] = "_"  # White's 10th-move clock missing
    assert ec.clocks_at(" ".join(long_with_gap))[:2] == [None, 60]


def test_run_writes_one_row_per_game(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    t = pa.table({"game_id": ["a", "b"], "clocks": [" ".join(["30"] * 50), ""], "moves": ["e4", "d4"]})
    pq.write_table(t, tmp_path / "games_x.parquet")
    out = pq.read_table(ec.run(tmp_path / "games_x.parquet")).to_pydict()
    assert out["game_id"] == ["a", "b"] and out["w_clock_m25"] == [30, None]
