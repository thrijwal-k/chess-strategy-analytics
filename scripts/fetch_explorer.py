"""Download monthly opening statistics from the Lichess opening explorer (run on your own computer).

1. Create a token at https://lichess.org/account/oauth/token (no boxes need ticking) and copy it.
2. In the Anaconda Prompt:   set LICHESS_TOKEN=lip_xxxxxxxx      (only lasts for that window)
3. Check it works:           python scripts/fetch_explorer.py --probe
4. Full download:            python scripts/fetch_explorer.py

Output: data/explorer/history.csv with one row per position, rating group and month. Responses are cached, so
the full run can be stopped (Ctrl+C) and restarted without repeating requests.
"""
from __future__ import annotations

import argparse
import csv
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chessanalytics.explorer import POSITIONS, RATING_GROUPS, Explorer, months, to_uci, token_from_env  # noqa: E402

SINCE, UNTIL = "2013-01", "2026-09"
OUT = Path("data/explorer/history.csv")
FIELDS = ["position", "moves", "group", "month", "white", "draws", "black"]


def probe(ex: Explorer) -> int:
    play = to_uci("d4 d5 c4")
    try:
        h = ex.history(play, RATING_GROUPS["all"], SINCE, UNTIL)
        total = sum(r["white"] + r["draws"] + r["black"] for r in h)
        print(f"OK: history endpoint works. Queen's Gambit: {len(h)} months ({h[0]['month']} to {h[-1]['month']}), "
              f"{total:,} games in the explorer.")
    except urllib.error.HTTPError as exc:
        print(f"History endpoint returned HTTP {exc.code}; trying the month-by-month fallback...")
        r = ex.month_counts(play, RATING_GROUPS["all"], "2020-11")
        print(f"OK (fallback): November 2020 Queen's Gambit games: {r['white'] + r['draws'] + r['black']:,}")
    return 0


def full(ex: Explorer) -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    jobs = [(g, label, san) for g in RATING_GROUPS for label, san in POSITIONS]
    use_fallback = False
    for i, (group, label, san) in enumerate(jobs, 1):
        play = to_uci(san)
        if not use_fallback:
            try:
                hist = ex.history(play, RATING_GROUPS[group], SINCE, UNTIL)
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
                print("History endpoint not available: switching to month-by-month requests (all ratings only).")
                use_fallback = True
        if use_fallback:
            if group != "all":
                continue
            hist = [ex.month_counts(play, RATING_GROUPS[group], m) for m in months(SINCE, UNTIL)]
        for r in hist:
            rows.append({"position": label, "moves": san, "group": group, **r})
        print(f"  [{i}/{len(jobs)}] {group:<11} {label:<26} {len(hist)} months  "
              f"({ex.requests_made} requests so far)", flush=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"Done: {len(rows):,} rows -> {OUT}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true", help="make one request to check the token and endpoint")
    args = ap.parse_args()
    ex = Explorer(token=token_from_env())
    try:
        return probe(ex) if args.probe else full(ex)
    except PermissionError as exc:
        print(exc)
        return 1
    except KeyboardInterrupt:
        print("\nStopped. Run the same command again to continue; finished requests are cached.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
