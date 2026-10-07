"""Phase 2: middlegame and endgame features for every game in a games table, from the stored moves.

Each game is replayed once. Position features are taken for both sides after move 15, 20 and 25 (if the game
lasts that long); castling and queen-trade timing come from the whole game; the endgame is the first position
meeting the threshold in endgame.py. Where the game has engine analysis, the evaluation at each snapshot and its
change over the next 10 moves are kept too.

    python -m chessanalytics.features data/games/games_2020-09.parquet --out data/features/features_2020-09.parquet
"""
from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Iterator
from multiprocessing import Pool
from pathlib import Path

import chess
import pyarrow as pa
import pyarrow.parquet as pq

from .endgame import entry_for, is_endgame
from .middlegame import position_features
from .pgn_stream import decode_game

SNAPSHOT_MOVES = (15, 20, 25)
EVAL_HORIZON_PLIES = 20

_I, _F, _B, _S = pa.int32(), pa.float64(), pa.bool_(), pa.string()
POSITION_TYPES = {
    "material": _I, "isolated": _I, "doubled": _I, "backward": _I, "passed": _I, "islands": _I, "iqp": _B,
    "hanging": _B, "bishop_pair": _B, "bad_bishop": _F, "outposts": _I, "rooks_open": _I, "rooks_half_open": _I,
    "rooks_7th": _I, "king_side": _S, "pawn_shield": _I, "open_files_near_king": _I, "centre": _I, "space": _I,
    "developed_minors": _I,
}
GAME_FEATURE_FIELDS = [
    ("white_castled", _S), ("black_castled", _S), ("white_castle_ply", _I), ("black_castle_ply", _I),
    ("opposite_side_castling", _B), ("queens_off_ply", _I), ("endgame_ply", _I), ("endgame_type", _S),
    ("endgame_pawn_balance", _I), ("endgame_material_balance", _I), ("endgame_men", _I), ("endgame_eval", _F),
    ("feature_error", _S),
]
SNAPSHOT_FIELDS = [(f"{p}_{k}_m{m}", t)
                   for m in SNAPSHOT_MOVES for p in ("w", "b") for k, t in POSITION_TYPES.items()] \
    + [(f"{k}_m{m}", _F) for m in SNAPSHOT_MOVES for k in ("eval", "eval_change")]


def _eval_at(evals: list[float | None], ply: int) -> float | None:
    """Evaluation after `ply` moves have been played (ply is 1-based), or None if not available."""
    return evals[ply - 1] if 0 < ply <= len(evals) else None


def game_features(moves: str, evals: str = "", clocks: str = "") -> dict:
    g = decode_game(moves, evals, clocks)
    board = chess.Board()
    row: dict = {"white_castled": "", "black_castled": "", "white_castle_ply": None, "black_castle_ply": None,
                 "queens_off_ply": None, "endgame_ply": None, "endgame_type": "", "endgame_pawn_balance": None,
                 "endgame_material_balance": None, "endgame_men": None, "endgame_eval": None, "feature_error": ""}
    row.update({name: None for name, _ in SNAPSHOT_FIELDS})
    snapshot_plies = {2 * m: m for m in SNAPSHOT_MOVES}
    try:
        for ply, san in enumerate(g.moves, start=1):
            move = board.parse_san(san)
            side = "white" if board.turn == chess.WHITE else "black"
            if board.is_castling(move) and not row[f"{side}_castled"]:
                row[f"{side}_castled"] = "kingside" if chess.square_file(move.to_square) > 4 else "queenside"
                row[f"{side}_castle_ply"] = ply
            board.push(move)
            if row["queens_off_ply"] is None and not board.pieces(chess.QUEEN, chess.WHITE) \
                    and not board.pieces(chess.QUEEN, chess.BLACK):
                row["queens_off_ply"] = ply
            if ply in snapshot_plies:
                m = snapshot_plies[ply]
                for color, prefix in ((chess.WHITE, "w"), (chess.BLACK, "b")):
                    for k, v in position_features(board, color).items():
                        row[f"{prefix}_{k}_m{m}"] = v
                e0 = _eval_at(g.evals, ply)
                e1 = _eval_at(g.evals, ply + EVAL_HORIZON_PLIES)
                row[f"eval_m{m}"] = e0
                row[f"eval_change_m{m}"] = e1 - e0 if e0 is not None and e1 is not None else None
            if row["endgame_ply"] is None and is_endgame(board):
                e = entry_for(board, ply)
                row.update(endgame_ply=e.ply, endgame_type=e.category, endgame_pawn_balance=e.pawn_balance,
                           endgame_material_balance=e.material_balance, endgame_men=e.pieces_total,
                           endgame_eval=_eval_at(g.evals, ply))
    except (ValueError, AssertionError) as exc:
        row["feature_error"] = type(exc).__name__
    row["opposite_side_castling"] = bool(row["white_castled"] and row["black_castled"]
                                         and row["white_castled"] != row["black_castled"])
    return row


def features_schema(games_schema: pa.Schema) -> pa.Schema:
    base = [f for f in games_schema if f.name not in ("moves", "evals", "clocks")]
    return pa.schema(base + [pa.field(n, t) for n, t in GAME_FEATURE_FIELDS + SNAPSHOT_FIELDS])


def _batch_features(table: pa.Table) -> list[dict]:
    rows = table.to_pylist()
    out = []
    for r in rows:
        f = game_features(r.pop("moves") or "", r.pop("evals") or "", r.pop("clocks") or "")
        r.update(f)
        out.append(r)
    return out


def _iter_batches(path: Path, batch_size: int, limit: int | None) -> Iterator[pa.Table]:
    seen = 0
    for rb in pq.ParquetFile(path).iter_batches(batch_size=batch_size):
        table = pa.Table.from_batches([rb])
        if limit is not None:
            table = table.slice(0, max(0, limit - seen))
        if table.num_rows == 0:
            return
        seen += table.num_rows
        yield table


def run(path: Path, out: Path, workers: int = 1, limit: int | None = None, progress_every: int = 100_000) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".partial")
    tmp.unlink(missing_ok=True)
    schema = features_schema(pq.ParquetFile(path).schema_arrow)
    t0, done, next_report = time.monotonic(), 0, progress_every
    batches = _iter_batches(path, 2000, limit)
    pool = Pool(workers) if workers > 1 else None
    writer = pq.ParquetWriter(tmp, schema, compression="zstd")
    try:
        results = pool.imap(_batch_features, batches) if pool else map(_batch_features, batches)
        for rows in results:
            writer.write_table(pa.Table.from_pylist(rows, schema=schema))
            done += len(rows)
            if progress_every and done >= next_report:
                secs = time.monotonic() - t0
                print(f"  {done:>10,} games  {secs / 60:5.1f} min  ({done / max(secs, 1e-9):,.0f} games/s)", flush=True)
                next_report += progress_every
    finally:
        if pool:
            pool.terminate()
            pool.join()
        writer.close()
    tmp.replace(out)
    return done


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("games", help="games table from chessanalytics.extract (.parquet)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--limit", type=int)
    args = ap.parse_args(argv)
    t0 = time.monotonic()
    n = run(Path(args.games), Path(args.out), args.workers, args.limit)
    print(f"{n:,} games -> {args.out} in {(time.monotonic() - t0) / 60:.1f} min", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
