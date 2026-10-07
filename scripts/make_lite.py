"""Write a slim copy of each games table without the moves, evals and clocks (about a tenth of the size).

The opening analysis only needs ratings, results and opening labels, so this is the file to share or upload.

    python scripts/make_lite.py data/games/games_2020-09.parquet data/games/games_2020-10.parquet
"""
from __future__ import annotations

import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

DROP = {"moves", "evals", "clocks"}


def make_lite(src: Path, out_dir: Path = Path("data/lite")) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / src.name.replace("games_", "games_lite_")
    pf = pq.ParquetFile(src)
    cols = [c for c in pf.schema_arrow.names if c not in DROP]
    schema = pa.schema([pf.schema_arrow.field(c) for c in cols])
    writer = pq.ParquetWriter(out, schema, compression="zstd")
    try:
        for batch in pf.iter_batches(batch_size=200_000, columns=cols):
            writer.write_batch(batch)
    finally:
        writer.close()
    return out


def main(paths: list[str]) -> int:
    for p in paths:
        out = make_lite(Path(p))
        print(f"{p} -> {out} ({out.stat().st_size / 1e6:,.0f} MB)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
