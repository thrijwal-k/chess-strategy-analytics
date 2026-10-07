"""Clock times at moves 10, 15, 20 and 25 for every saved game (seconds left for each player). Needs no download.

    python scripts/extract_clocks.py data/games/games_2020-09.parquet data/games/games_2020-10.parquet ...
Writes data/clocks/clocks_<month>.parquet: game_id, then w_clock_mN and b_clock_mN for N in 10, 15, 20, 25 (the
clock of each player after their own Nth move; empty if the game was shorter or had no clock data).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

MOVES = (10, 15, 20, 25)
SCHEMA = pa.schema([("game_id", pa.string())] + [(f"{s}_clock_m{m}", pa.int32()) for m in MOVES for s in "wb"])


def clocks_at(clocks: str) -> list[int | None]:
    toks = clocks.split() if clocks else []
    out: list[int | None] = []
    for m in MOVES:
        for ply in (2 * m - 1, 2 * m):  # White's Nth move is ply 2N-1, Black's is ply 2N
            tok = toks[ply - 1] if len(toks) >= ply else "_"
            out.append(None if tok == "_" else int(tok))
    return out


def run(src: Path) -> Path:
    out_dir = Path("data/clocks")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / src.name.replace("games_", "clocks_")
    tmp = out.with_name(out.name + ".partial")
    t0, done = time.monotonic(), 0
    with pq.ParquetWriter(tmp, SCHEMA, compression="zstd") as writer:
        for batch in pq.ParquetFile(src).iter_batches(batch_size=100_000, columns=["game_id", "clocks"]):
            ids, cl = batch.column("game_id").to_pylist(), batch.column("clocks").to_pylist()
            cols = list(zip(*[clocks_at(c) for c in cl], strict=True)) if ids else [[] for _ in SCHEMA.names[1:]]
            arrays = [pa.array(ids)] + [pa.array(list(c), type=pa.int32()) for c in cols]
            writer.write_table(pa.Table.from_arrays(arrays, schema=SCHEMA))
            done += len(ids)
    tmp.replace(out)
    print(f"{src} -> {out}: {done:,} games in {(time.monotonic() - t0) / 60:.1f} min", flush=True)
    return out


if __name__ == "__main__":
    for path in sys.argv[1:]:
        run(Path(path))
