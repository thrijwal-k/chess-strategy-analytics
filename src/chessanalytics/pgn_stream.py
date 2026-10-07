"""Fast streaming reader for Lichess-style PGN, plain or zstd-compressed, from a file or a URL.

A month of Lichess games is around 30 GB compressed and 90+ million games, so this reader:
- never decompresses to disk (zstd is decoded as a stream);
- does not build python-chess Game objects (slow); it tokenises movetext directly and keeps SAN strings,
  engine evaluations ([%eval ...]) and clock times ([%clk ...]);
- can stop after a byte budget or a number of games, which is how a month is sampled through an HTTP range
  request without downloading all of it.

Evaluations are stored in pawns from White's point of view. A forced mate is stored as +/-MATE_SCORE so
that it sorts above any normal evaluation; `Game.mates` keeps the mate distance.
"""
from __future__ import annotations

import http.client
import io
import re
import time
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

MATE_SCORE = 100.0
RESULTS = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}

_HEADER = re.compile(r'^\[(\w+)\s+"(.*)"\]\s*$')
_EVAL = re.compile(r"\[%eval\s+(#?)(-?[\d.]+)")
_CLK = re.compile(r"\[%clk\s+(\d+):(\d{2}):(\d{2})")
_MOVE_NUMBER = re.compile(r"^\d+\.(\.\.)?$")
_SAN_SUFFIX = re.compile(r"[!?]+$")


@dataclass
class Game:
    headers: dict[str, str]
    moves: list[str] = field(default_factory=list)
    evals: list[float | None] = field(default_factory=list)  # one per ply, pawns from White's view
    mates: list[int | None] = field(default_factory=list)  # signed mate distance where the eval is a mate
    clocks: list[int | None] = field(default_factory=list)  # seconds left after each ply

    @property
    def result(self) -> float | None:
        """White's score: 1, 0.5 or 0. None for unfinished games."""
        return RESULTS.get(self.headers.get("Result", "*"))

    def _elo(self, key: str) -> int | None:
        v = self.headers.get(key, "")
        return int(v) if v.isdigit() else None

    @property
    def white_elo(self) -> int | None:
        return self._elo("WhiteElo")

    @property
    def black_elo(self) -> int | None:
        return self._elo("BlackElo")

    @property
    def has_eval(self) -> bool:
        return any(e is not None for e in self.evals)

    @property
    def has_clock(self) -> bool:
        return any(c is not None for c in self.clocks)

    @property
    def speed(self) -> str:
        return speed_from_time_control(self.headers.get("TimeControl", "-"))


def speed_from_time_control(tc: str) -> str:
    """Lichess speed category: estimated duration = base + 40 x increment (seconds)."""
    if not tc or tc == "-":
        return "correspondence"
    try:
        base, inc = (int(x) for x in tc.split("+"))
    except ValueError:
        return "unknown"
    total = base + 40 * inc
    if total < 30:
        return "ultrabullet"
    if total < 180:
        return "bullet"
    if total < 480:
        return "blitz"
    if total < 1500:
        return "rapid"
    return "classical"


def _parse_comment(text: str, game: Game) -> None:
    """Attach a {comment}'s eval and clock to the last move played."""
    if not game.moves:
        return
    m = _EVAL.search(text)
    if m:
        value = float(m.group(2))
        if m.group(1):  # '#3' = White mates in 3, '#-3' = Black mates in 3
            game.evals[-1] = -MATE_SCORE if m.group(2).startswith("-") else MATE_SCORE
            game.mates[-1] = int(value)
        else:
            game.evals[-1] = value
    c = _CLK.search(text)
    if c:
        h, mi, s = (int(x) for x in c.groups())
        game.clocks[-1] = h * 3600 + mi * 60 + s


def parse_movetext(text: str, game: Game) -> None:
    i, n = 0, len(text)
    depth = 0  # variation nesting; moves inside (...) are skipped
    while i < n:
        ch = text[i]
        if ch == "{":
            j = text.find("}", i + 1)
            j = n if j < 0 else j
            if depth == 0:
                _parse_comment(text[i + 1 : j], game)
            i = j + 1
            continue
        if ch == ";":  # rest-of-line comment
            j = text.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            i += 1
            continue
        if ch.isspace():
            i += 1
            continue
        j = i
        while j < n and not text[j].isspace() and text[j] not in "{}();":
            j += 1
        if j == i:  # a stray '}' outside a comment: skip it (otherwise the loop would never advance)
            i += 1
            continue
        tok = text[i:j]
        i = j
        if depth or tok in RESULTS or tok == "*" or tok.startswith("$") or _MOVE_NUMBER.match(tok):
            continue
        if tok[0].isdigit() and "." in tok:  # "12.Nf3" written without a space
            tok = tok.split(".")[-1]
            if not tok:
                continue
        game.moves.append(_SAN_SUFFIX.sub("", tok))
        game.evals.append(None)
        game.mates.append(None)
        game.clocks.append(None)


def iter_pgn_text(lines: Iterator[str]) -> Iterator[Game]:
    headers: dict[str, str] = {}
    movetext: list[str] = []
    for raw in lines:
        line = raw.strip()
        if line.startswith("﻿"):
            line = line[1:]
        if line.startswith("[") and (m := _HEADER.match(line)):
            if movetext:  # a header after movetext starts a new game (tolerates missing blank lines)
                g = Game(headers)
                parse_movetext("\n".join(movetext), g)
                yield g
                headers, movetext = {}, []
            headers[m.group(1)] = m.group(2)
        elif line:
            movetext.append(line)
        elif movetext:
            g = Game(headers)
            parse_movetext("\n".join(movetext), g)
            yield g
            headers, movetext = {}, []
    if headers or movetext:
        g = Game(headers)
        parse_movetext("\n".join(movetext), g)
        yield g


class _ByteBudget(io.RawIOBase):
    """Stops reading after max_bytes of the compressed stream (used to sample the start of a month)."""

    def __init__(self, raw: BinaryIO, max_bytes: int | None):
        self.raw, self.left = raw, max_bytes

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:
        if self.left is not None and self.left <= 0:
            return 0
        size = len(b) if self.left is None else min(len(b), self.left)
        data = self.raw.read(size)
        b[: len(data)] = data
        if self.left is not None:
            self.left -= len(data)
        return len(data)


class ResumableHTTP(io.RawIOBase):
    """Reads a URL; if the connection drops or stalls (Wi-Fi blip, laptop sleep), reconnects with an HTTP Range
    request from the exact byte it had reached. The zstd decoder downstream never notices the gap."""

    def __init__(self, url: str, timeout: float = 60, retries: int = 20, log=print):
        self.url, self.timeout, self.retries, self.log = url, timeout, retries, log
        self.pos = 0
        self.total: int | None = None  # full file size, so a silently cut-off response is detected
        self.resumes = 0
        self._resp = self._connect()

    def _connect(self):
        headers = {"User-Agent": "chess-strategy-analytics (research)"}
        if self.pos:
            headers["Range"] = f"bytes={self.pos}-"
        req = urllib.request.Request(self.url, headers=headers)  # noqa: S310
        resp = urllib.request.urlopen(req, timeout=self.timeout)  # noqa: S310 - URL is supplied by the user
        if self.pos and resp.status != 206:
            resp.close()
            raise OSError("server ignored the resume request (no HTTP 206); cannot continue safely")
        length = resp.headers.get("Content-Length")
        if self.total is None and length is not None:
            self.total = self.pos + int(length)
        return resp

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:
        failures = 0
        while True:
            try:
                data = self._resp.read(len(b))
                if not data and self.total is not None and self.pos < self.total:
                    # http.client returns b"" rather than raising when a connection closes early
                    raise http.client.IncompleteRead(b"", self.total - self.pos)
                b[: len(data)] = data
                self.pos += len(data)
                return len(data)
            except (OSError, http.client.HTTPException) as exc:  # timeouts and resets are OSError subclasses
                failures += 1
                if failures > self.retries:
                    raise
                wait = min(60, 2 ** failures)
                self.log(f"  connection problem ({type(exc).__name__}); resuming at {self.pos / 1e6:,.0f} MB "
                         f"in {wait}s (attempt {failures}/{self.retries})")
                time.sleep(wait)
                try:
                    self._resp.close()
                    self._resp = self._connect()
                    self.resumes += 1
                except (OSError, http.client.HTTPException):
                    continue

    def close(self) -> None:
        try:
            self._resp.close()
        finally:
            super().close()


def open_binary(source: str | Path) -> BinaryIO:
    s = str(source)
    if s.startswith(("http://", "https://")):
        return io.BufferedReader(ResumableHTTP(s), 1 << 20)
    return open(s, "rb")


def iter_games(source: str | Path | BinaryIO, limit: int | None = None, max_bytes: int | None = None,
               compressed: bool | None = None) -> Iterator[Game]:
    """Yield games from a .pgn or .pgn.zst path, URL or binary file object.

    limit: stop after this many games. max_bytes: stop after this many bytes of the (compressed) input; the last
    game may then be cut off, so it is dropped.
    """
    name = getattr(source, "name", source) if not isinstance(source, (str, Path)) else str(source)
    if compressed is None:
        compressed = str(name).endswith(".zst")
    raw = open_binary(source) if isinstance(source, (str, Path)) else source
    try:
        stream: BinaryIO = io.BufferedReader(_ByteBudget(raw, max_bytes), 1 << 20) if max_bytes else raw
        if compressed:
            import zstandard

            stream = zstandard.ZstdDecompressor(max_window_size=1 << 31).stream_reader(stream, read_across_frames=True)
        text = io.TextIOWrapper(stream, encoding="utf-8", errors="replace", newline="")
        count = 0
        pending: Game | None = None
        for game in iter_pgn_text(text):
            if pending is not None:
                yield pending
                count += 1
                if limit is not None and count >= limit:
                    return
            pending = game
        # with a byte budget the last game may have been cut off mid-way, so it is dropped
        if pending is not None and not max_bytes:
            yield pending
    except Exception as exc:  # a byte budget can cut a zstd frame; treat that as end of sample
        if max_bytes and "zstd" in type(exc).__module__.lower() + str(exc).lower():
            return
        raise
    finally:
        if isinstance(source, (str, Path)):
            raw.close()



# Compact text encodings so the moves, evals and clocks can be stored in a Parquet table and later analysis
# (middlegame, endgame, in-game prediction) never needs the original download again. "_" marks a missing value.


def encode_evals(game: Game) -> str:
    if not game.has_eval:
        return ""
    out = []
    for e, m in zip(game.evals, game.mates, strict=True):
        out.append("_" if e is None else (f"#{m}" if m is not None else f"{e:g}"))
    return " ".join(out)


def encode_clocks(game: Game) -> str:
    return " ".join("_" if c is None else str(c) for c in game.clocks) if game.has_clock else ""


def decode_game(moves: str, evals: str = "", clocks: str = "", headers: dict | None = None) -> Game:
    g = Game(dict(headers or {}), moves.split() if moves else [])
    n = len(g.moves)
    g.evals, g.mates, g.clocks = [None] * n, [None] * n, [None] * n
    for i, tok in enumerate(evals.split() if evals else []):
        if tok == "_":
            continue
        if tok.startswith("#"):
            g.mates[i] = int(tok[1:])
            g.evals[i] = -MATE_SCORE if tok.startswith("#-") else MATE_SCORE
        else:
            g.evals[i] = float(tok)
    for i, tok in enumerate(clocks.split() if clocks else []):
        if tok != "_":
            g.clocks[i] = int(tok)
    return g
