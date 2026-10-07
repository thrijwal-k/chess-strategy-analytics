"""Recompute the White system / Black defence labels from the saved moves, after the detector rules change.

Reads only the game id and the moves, so it is much faster than the full extract, and needs no download.

    python scripts/relabel_setups.py data/games/games_2020-09.parquet data/games/games_2020-10.parquet ...
Writes data/setups/setups_<month>.parquet with columns game_id, white_setup, black_setup.
"""
from __future__ import annotations

import sys
import time
from multiprocessing import Pool
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chessanalytics.setups import classify_setups  # noqa: E402

SCHEMA = pa.schema([("game_id", pa.string()), ("white_setup", pa.string()), ("black_setup", pa.string())])


def _label(batch: pa.RecordBatch) -> pa.Table:
    ids = batch.column("game_id").to_pylist()
    moves = batch.column("moves").to_pylist()
    w, b = [], []
    for m in moves:
        try:
            ws, bs = classify_setups((m or "").split())
        except ValueError:
            ws = bs = ""
        w.append(ws)
        b.append(bs)
    return pa.Table.from_arrays([pa.array(ids), pa.array(w), pa.array(b)], schema=SCHEMA)


def relabel(src: Path, workers: int = 4) -> Path:
    out_dir = Path("data/setups")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / src.name.replace("games_", "setups_")
    tmp = out.with_name(out.name + ".partial")
    pf = pq.ParquetFile(src)
    t0, done = time.monotonic(), 0
    with Pool(workers) as pool, pq.ParquetWriter(tmp, SCHEMA, compression="zstd") as writer:
        for table in pool.imap(_label, pf.iter_batches(batch_size=5000, columns=["game_id", "moves"])):
            writer.write_table(table)
            done += table.num_rows
            if done % 500_000 < 5000:
                print(f"  {done:>10,} games  {(time.monotonic() - t0) / 60:4.1f} min", flush=True)
    tmp.replace(out)
    print(f"{src} -> {out}: {done:,} games in {(time.monotonic() - t0) / 60:.1f} min", flush=True)
    return out


if __name__ == "__main__":
    for path in sys.argv[1:]:
        relabel(Path(path))
