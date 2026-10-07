"""Monthly opening statistics from the Lichess opening explorer (explorer.lichess.ovh), for the time-series study.

For each tracked position and rating group this downloads how many rated Lichess games reached the position in
each month, and how they ended (White win, draw, Black win). The starting position is fetched with the same filters,
so every opening's monthly *share* is its count divided by the number of games that month. That ratio stays valid
even though the explorer indexes a sample of games rather than all of them.

Since 2026 the explorer requires a personal Lichess API token (no scopes needed). The token is read from the
LICHESS_TOKEN environment variable and is never printed or saved.

Every response is cached as JSON under data/explorer/cache, so an interrupted run resumes where it stopped and a
rerun makes no requests at all.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import chess

BASE = "https://explorer.lichess.ovh/lichess"
SPEEDS = "bullet,blitz,rapid,classical"
RATING_GROUPS = {
    "all": "0,1000,1200,1400,1600,1800,2000,2200,2500",
    "under_1600": "0,1000,1200,1400",
    "1600_1999": "1600,1800",
    "2000_plus": "2000,2200,2500",
}

# (label, SAN moves). Positions are matched exactly by the explorer, so each line is the opening's defining moves.
POSITIONS: list[tuple[str, str]] = [
    ("Start position", ""),
    ("1.e4", "e4"), ("1.d4", "d4"), ("1.c4 English", "c4"), ("1.Nf3 Réti", "Nf3"), ("1.f4 Bird", "f4"),
    ("Sicilian", "e4 c5"), ("French", "e4 e6"), ("Caro-Kann", "e4 c6"), ("Scandinavian", "e4 d5"),
    ("Pirc", "e4 d6"), ("Modern", "e4 g6"), ("Alekhine", "e4 Nf6"), ("Open game 1...e5", "e4 e5"),
    ("Italian", "e4 e5 Nf3 Nc6 Bc4"), ("Ruy Lopez", "e4 e5 Nf3 Nc6 Bb5"), ("Scotch", "e4 e5 Nf3 Nc6 d4"),
    ("Petrov", "e4 e5 Nf3 Nf6"), ("Philidor", "e4 e5 Nf3 d6"), ("King's Gambit", "e4 e5 f4"),
    ("Vienna", "e4 e5 Nc3"), ("Alapin Sicilian", "e4 c5 c3"), ("Smith-Morra Gambit", "e4 c5 d4 cxd4 c3"),
    ("Najdorf", "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6"),
    ("Queen's Gambit", "d4 d5 c4"), ("Queen's Gambit Accepted", "d4 d5 c4 dxc4"),
    ("Queen's Gambit Declined", "d4 d5 c4 e6"), ("Slav", "d4 d5 c4 c6"),
    ("London vs 1...d5", "d4 d5 Bf4"), ("London vs 1...Nf6", "d4 Nf6 Bf4"), ("Jobava London", "d4 d5 Nc3 Nf6 Bf4"),
    ("Dutch", "d4 f5"), ("London vs Dutch", "d4 f5 Bf4"), ("King's Indian", "d4 Nf6 c4 g6"),
    ("Grünfeld", "d4 Nf6 c4 g6 Nc3 d5"), ("Nimzo-Indian", "d4 Nf6 c4 e6 Nc3 Bb4"), ("Benoni", "d4 Nf6 c4 c5"),
    ("Catalan", "d4 Nf6 c4 e6 g3"), ("Trompowsky", "d4 Nf6 Bg5"), ("Englund Gambit", "d4 e5"),
]


def to_uci(san_line: str) -> str:
    board = chess.Board()
    out = []
    for san in san_line.split():
        move = board.parse_san(san)
        out.append(move.uci())
        board.push(move)
    return ",".join(out)


@dataclass
class Explorer:
    token: str
    cache_dir: Path = Path("data/explorer/cache")
    pause_s: float = 1.0  # polite gap between live requests
    opener: Callable = urllib.request.urlopen
    sleep: Callable = time.sleep
    log: Callable = print
    requests_made: int = 0

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".json")

    def get(self, path: str, params: dict) -> dict:
        url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
        cached = self._cache_path(url)
        if cached.exists():
            return json.loads(cached.read_text())
        for attempt in range(1, 8):
            req = urllib.request.Request(url, headers={  # noqa: S310 - fixed https host
                "Authorization": f"Bearer {self.token}", "Accept": "application/json",
                "User-Agent": "chess-strategy-analytics (MSc research project)"})
            try:
                with self.opener(req, timeout=60) as resp:  # noqa: S310 - fixed https host
                    data = json.loads(resp.read().decode())
                self.requests_made += 1
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                cached.write_text(json.dumps(data))
                self.sleep(self.pause_s)
                return data
            except urllib.error.HTTPError as exc:
                if exc.code == 429:  # Lichess asks clients to wait a full minute after a 429
                    self.log(f"  rate limited; waiting 60 s (attempt {attempt})")
                    self.sleep(60)
                    continue
                if exc.code in (401, 403):
                    msg = f"Lichess rejected the token (HTTP {exc.code}). Check LICHESS_TOKEN."
                    raise PermissionError(msg) from None
                if exc.code >= 500:
                    self.sleep(min(60, 5 * attempt))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                self.log(f"  network problem ({type(exc).__name__}); retrying")
                self.sleep(min(60, 5 * attempt))
        raise RuntimeError(f"giving up after repeated failures: {path}")

    def history(self, play: str, ratings: str, since: str, until: str) -> list[dict]:
        """Monthly counts for one position: [{'month': 'YYYY-MM', 'white': .., 'draws': .., 'black': ..}, ...]."""
        data = self.get("/history", {"variant": "standard", "play": play, "speeds": SPEEDS, "ratings": ratings,
                                     "since": since, "until": until})
        return [{"month": h["month"], "white": int(h.get("white", 0)), "draws": int(h.get("draws", 0)),
                 "black": int(h.get("black", 0))} for h in data.get("history", [])]

    def month_counts(self, play: str, ratings: str, month: str) -> dict:
        """Fallback: one month at a time from the main endpoint."""
        data = self.get("", {"variant": "standard", "play": play, "speeds": SPEEDS, "ratings": ratings,
                             "since": month, "until": month, "moves": 0, "topGames": 0, "recentGames": 0})
        return {"month": month, "white": int(data.get("white", 0)), "draws": int(data.get("draws", 0)),
                "black": int(data.get("black", 0))}


def months(since: str, until: str) -> list[str]:
    y, m = map(int, since.split("-"))
    ye, me = map(int, until.split("-"))
    out = []
    while (y, m) <= (ye, me):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def token_from_env() -> str:
    token = os.environ.get("LICHESS_TOKEN", "").strip()
    if not token:
        raise SystemExit("Set LICHESS_TOKEN first (see the instructions). The token is never printed or saved.")
    return token
