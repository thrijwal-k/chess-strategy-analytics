"""Settled endgame types for every saved game (see endgame.settled_endgames). Needs no download.

    python scripts/endgame_pass.py data/games/games_2020-09.parquet data/games/games_2020-10.parquet ...
Writes data/endgames/endgames_<month>.parquet: game_id plus, for each key endgame type, the ply it settled at and
the pawn and material balance (White minus Black) at that point.
"""
from __future__ import annotations

import sys
import time
from multiprocessing import Pool
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chessanalytics.endgame import KEY_TYPES, settled_endgames  # noqa: E402

FIELDS = [("game_id", pa.string()), ("settled_ply", pa.int32()), ("settled_type", pa.string()),
          ("settled_pawns", pa.int32()), ("settled_material", pa.int32()), ("final_type", pa.string())]
for short in KEY_TYPES.values():
    FIELDS += [(f"{short}_ply", pa.int32()), (f"{short}_pawns", pa.int32()), (f"{short}_material", pa.int32())]
SCHEMA = pa.schema(FIELDS)


def _batch(batch: pa.RecordBatch) -> pa.Table:
    rows = []
    for gid, moves in zip(batch.column("game_id").to_pylist(), batch.column("moves").to_pylist(), strict=True):
        try:
            r = settled_endgames((moves or "").split())
        except ValueError:
            r = {}
        r["game_id"] = gid
        rows.append(r)
    return pa.Table.from_pylist(rows, schema=SCHEMA)


def run(src: Path, workers: int = 4) -> Path:
    out_dir = Path("data/endgames")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / src.name.replace("games_", "endgames_")
    tmp = out.with_name(out.name + ".partial")
    t0, done = time.monotonic(), 0
    pf = pq.ParquetFile(src)
    with Pool(workers) as pool, pq.ParquetWriter(tmp, SCHEMA, compression="zstd") as writer:
        for table in pool.imap(_batch, pf.iter_batches(batch_size=5000, columns=["game_id", "moves"])):
            writer.write_table(table)
            done += table.num_rows
            if done % 500_000 < 5000:
                print(f"  {done:>10,} games  {(time.monotonic() - t0) / 60:4.1f} min", flush=True)
    tmp.replace(out)
    print(f"{src} -> {out}: {done:,} games in {(time.monotonic() - t0) / 60:.1f} min", flush=True)
    return out


if __name__ == "__main__":
    for path in sys.argv[1:]:
        run(Path(path))
