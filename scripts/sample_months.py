"""Sample the start of several Lichess monthly files straight from the server (run on your own computer).

Each month reads only the first --gb gigabytes of the compressed file through the HTTP stream, so nothing is
saved to disk except the small per-game table.

    python scripts/sample_months.py 2023-01 2023-06 2024-01 --gb 1 --workers 6
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chessanalytics.extract import main as extract_main  # noqa: E402

URL = "https://database.lichess.org/standard/lichess_db_standard_rated_{month}.pgn.zst"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("months", nargs="+", help="YYYY-MM")
    ap.add_argument("--gb", type=float, default=1.0, help="compressed gigabytes to read per month")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out-dir", default="data/games")
    args = ap.parse_args()
    for month in args.months:
        out = Path(args.out_dir) / f"games_{month}.parquet"
        if out.exists():
            print(f"{out} exists, skipping")
            continue
        extract_main([URL.format(month=month), "--out", str(out), "--max-bytes", str(int(args.gb * 1e9)),
                      "--workers", str(args.workers)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
