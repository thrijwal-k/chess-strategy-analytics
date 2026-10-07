"""End-to-end smoke test of the whole data pipeline on the sample games (used by CI; also runs locally).

Runs every stage in a temporary folder: extract -> features -> relabel setups -> settled endgames -> clocks -> lite
copy, then checks that every output has one row per game, that the game ids line up, and that the known sample
games get the expected labels. Writes a short Markdown summary to $GITHUB_STEP_SUMMARY when it is set.

    python scripts/smoke_pipeline.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "sample_lichess.pgn"


def run(args: list[str], cwd: Path) -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    print("$", " ".join(args[1:]), flush=True)
    subprocess.run(args, cwd=cwd, env=env, check=True)  # noqa: S603 - fixed commands


def main() -> int:
    py = sys.executable
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "data" / "games").mkdir(parents=True)
        shutil.copytree(ROOT / "data" / "openings", work / "data" / "openings")
        games = work / "data" / "games" / "games_fixture.parquet"
        run([py, "-m", "chessanalytics.extract", str(FIXTURE), "--out", str(games), "--progress", "0"], work)
        run([py, "-m", "chessanalytics.features", str(games), "--out", "data/features/features_fixture.parquet"], work)
        for script in ("relabel_setups.py", "endgame_pass.py", "extract_clocks.py", "make_lite.py"):
            run([py, str(ROOT / "scripts" / script), str(games)], work)

        outputs = {
            "games": games,
            "features": work / "data/features/features_fixture.parquet",
            "setups": work / "data/setups/setups_fixture.parquet",
            "endgames": work / "data/endgames/endgames_fixture.parquet",
            "clocks": work / "data/clocks/clocks_fixture.parquet",
            "lite": work / "data/lite/games_lite_fixture.parquet",
        }
        tables = {name: pd.read_parquet(path) for name, path in outputs.items()}
        ids = list(tables["games"].game_id)
        problems = [f"{name}: {len(t)} rows" for name, t in tables.items() if len(t) != len(ids)]
        problems += [f"{name}: game ids differ" for name, t in tables.items() if list(t.game_id) != ids]
        g = tables["games"].set_index("game_id")
        expected = {"AAAA0001": ("London System", "Dutch: Classical / other"),
                    "AAAA0002": ("Open Sicilian", "Sicilian Defence"),
                    "AAAA0003": ("Queen's Gambit", "Queen's Gambit Declined")}
        for gid, (w, b) in expected.items():
            if (g.loc[gid, "white_setup"], g.loc[gid, "black_setup"]) != (w, b):
                problems.append(f"{gid}: got {g.loc[gid, 'white_setup']} / {g.loc[gid, 'black_setup']}")
        if "moves" in tables["lite"].columns:
            problems.append("lite copy still contains moves")

    summary = "\n".join(["### Pipeline smoke test", "", "| Stage | Rows |", "|---|---|"]
                        + [f"| {name} | {len(t)} |" for name, t in tables.items()]
                        + ["", "Result: " + ("**passed**" if not problems else "**failed**: " + "; ".join(problems))])
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(summary + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
