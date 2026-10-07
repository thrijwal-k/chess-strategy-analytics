"""Turn a PGN stream into one row per game: ratings, time control, result, named opening and setups.

Usernames are not kept. Run on the laptop against a Lichess monthly file, for example:

    python -m chessanalytics.extract \\
        https://database.lichess.org/standard/lichess_db_standard_rated_2024-01.pgn.zst \\
        --max-bytes 2000000000 --out data/games_2024-01.parquet --workers 6
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
from collections import deque
from collections.abc import Iterator
from itertools import islice
from multiprocessing import Pool
from multiprocessing import TimeoutError as MPTimeoutError
from pathlib import Path

import chess
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .openings import default_classifier
from .pgn_stream import Game, encode_clocks, encode_evals, iter_games
from .setups import classify_setups


def game_row(g: Game) -> dict:
    h = g.headers
    we, be = g.white_elo, g.black_elo
    row = {
        "game_id": h.get("Site", "").rsplit("/", 1)[-1],
        "utc_date": h.get("UTCDate", h.get("Date", "")),
        "time_control": h.get("TimeControl", ""),
        "speed": g.speed,
        "rated": h.get("Event", "").lower().startswith("rated"),
        "white_elo": we,
        "black_elo": be,
        "rating_diff": we - be if we is not None and be is not None else None,
        "mean_elo": (we + be) / 2 if we is not None and be is not None else None,
        "result": g.result,
        "termination": h.get("Termination", ""),
        "eco_header": h.get("ECO", ""),
        "opening_header": h.get("Opening", ""),
        "plies": len(g.moves),
        "has_eval": g.has_eval,
        "has_clock": g.has_clock,
        "error": "",
        "moves": " ".join(g.moves),
        "evals": encode_evals(g),
        "clocks": encode_clocks(g),
    }
    row["month"] = row["utc_date"][:7].replace(".", "-")
    try:
        op = default_classifier().classify(g.moves)
        row["eco"], row["opening"], row["family"] = (op.eco, op.name, op.family) if op else ("", "", "")
        row["white_setup"], row["black_setup"] = classify_setups(g.moves)
    except (ValueError, chess.IllegalMoveError, chess.AmbiguousMoveError, chess.InvalidMoveError) as exc:
        row.update(eco="", opening="", family="", white_setup="", black_setup="", error=type(exc).__name__)
    return row


def _ignore_ctrl_c() -> None:
    """Workers ignore Ctrl+C; the main process handles it and shuts them all down."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)


WORKER_TIMEOUT_S = 600  # one batch of 2,000 games takes seconds; ten minutes means a worker has died


def _wait(result):
    """Wait for a worker result in short steps so Ctrl+C is noticed promptly on Windows, and give up with a clear
    message if a worker has died (a dead pool worker would otherwise make the run wait for ever)."""
    deadline = time.monotonic() + WORKER_TIMEOUT_S
    while True:
        try:
            return result.get(timeout=0.5)
        except MPTimeoutError:
            if time.monotonic() > deadline:
                raise RuntimeError("a worker stopped responding for 10 minutes; run the command again") from None


def _rows(games: list[Game]) -> list[dict]:
    return [game_row(g) for g in games]


def _chunks(it: Iterator[Game], size: int) -> Iterator[list[Game]]:
    while chunk := list(islice(it, size)):
        yield chunk


_STR = pa.string()
SCHEMA = pa.schema([
    ("game_id", _STR), ("utc_date", _STR), ("month", _STR), ("time_control", _STR), ("speed", _STR),
    ("rated", pa.bool_()), ("white_elo", pa.int32()), ("black_elo", pa.int32()), ("rating_diff", pa.int32()),
    ("mean_elo", pa.float64()), ("result", pa.float64()), ("termination", _STR), ("eco_header", _STR),
    ("opening_header", _STR), ("eco", _STR), ("opening", _STR), ("family", _STR), ("white_setup", _STR),
    ("black_setup", _STR), ("plies", pa.int32()), ("has_eval", pa.bool_()), ("has_clock", pa.bool_()),
    ("error", _STR), ("moves", _STR), ("evals", _STR), ("clocks", _STR),
])


def iter_row_batches(source: str, limit: int | None = None, max_bytes: int | None = None, workers: int = 1,
                     rated_standard_only: bool = True, progress_every: int = 0) -> Iterator[list[dict]]:
    """Yield games as batches of row dicts, so memory use stays flat however many games are read.

    progress_every: print a progress line every this many games (0 = silent).
    """
    games = iter_games(source, limit=limit, max_bytes=max_bytes)
    if rated_standard_only:
        games = (g for g in games if g.headers.get("Variant", "Standard") == "Standard")
    done, next_report, t0 = 0, progress_every, time.monotonic()

    def report(n: int) -> None:
        nonlocal done, next_report
        done += n
        if progress_every and done >= next_report:
            secs = time.monotonic() - t0
            print(f"  {done:>10,} games  {secs / 60:5.1f} min  ({done / max(secs, 1e-9):,.0f} games/s)", flush=True)
            next_report += progress_every

    if workers > 1:
        pool = Pool(workers, initializer=_ignore_ctrl_c)
        # at most a few batches waiting per worker: if the download outpaces the workers, reading pauses
        # instead of queueing millions of games in memory (Pool.imap has no such limit)
        pending: deque = deque()
        try:
            for chunk in _chunks(games, 2000):
                pending.append(pool.apply_async(_rows, (chunk,)))
                if len(pending) >= 3 * workers:
                    part = _wait(pending.popleft())
                    report(len(part))
                    yield part
            while pending:
                part = _wait(pending.popleft())
                report(len(part))
                yield part
            pool.close()
        except KeyboardInterrupt:
            # stop every worker at once so Ctrl+C returns to the prompt cleanly (important on Windows)
            print("\nStopped by Ctrl+C.", flush=True)
            pool.terminate()
            raise SystemExit(130) from None
        finally:
            pool.terminate()
            pool.join()
    else:
        for chunk in _chunks(games, 2000):
            part = _rows(chunk)
            report(len(part))
            yield part


def extract(source: str, limit: int | None = None, max_bytes: int | None = None, workers: int = 1,
            rated_standard_only: bool = True) -> pd.DataFrame:
    """Small inputs only (tests, quick looks): everything is held in memory."""
    rows = [r for batch in iter_row_batches(source, limit, max_bytes, workers, rated_standard_only) for r in batch]
    return pa.Table.from_pylist(rows, schema=SCHEMA).to_pandas()


def write_games(batches: Iterator[list[dict]], out: Path) -> tuple[int, int]:
    """Stream batches to Parquet or CSV. Writes to a .partial file and renames at the end, so an interrupted
    run never leaves a file that looks finished. Returns (games, unparseable)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".partial")
    tmp.unlink(missing_ok=True)  # left over from an interrupted run
    games = bad = 0
    writer = None
    try:
        for batch in batches:
            table = pa.Table.from_pylist(batch, schema=SCHEMA)
            if out.suffix == ".parquet":
                writer = writer or pq.ParquetWriter(tmp, SCHEMA, compression="zstd")
                writer.write_table(table)
            else:
                table.to_pandas().to_csv(tmp, mode="a", header=games == 0, index=False)
            games += len(batch)
            bad += sum(1 for r in batch if r["error"])
    finally:
        if writer is not None:
            writer.close()
    if games == 0:
        pq.write_table(SCHEMA.empty_table(), tmp) if out.suffix == ".parquet" else tmp.write_text("")
    tmp.replace(out)
    return games, bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help=".pgn or .pgn.zst path or URL")
    ap.add_argument("--out", required=True, help="output .parquet or .csv")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--max-bytes", type=int, help="read only this many compressed bytes (samples the start)")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--progress", type=int, default=100_000, help="print progress every N games (0 = silent)")
    args = ap.parse_args(argv)
    print(f"Reading {args.source}", flush=True)
    t0 = time.monotonic()
    out = Path(args.out)
    games, bad = write_games(
        iter_row_batches(args.source, args.limit, args.max_bytes, args.workers, progress_every=args.progress), out)
    secs = time.monotonic() - t0
    print(f"{games:,} games -> {out} in {secs / 60:.1f} min ({games / max(secs, 1e-9):,.0f} games/s); "
          f"{bad} unparseable", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
