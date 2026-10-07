"""Download resilience: a dropped connection resumes from the right byte, and odd PGN text cannot hang the parser."""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import zstandard

from chessanalytics.pgn_stream import Game, iter_games, parse_movetext

FIXTURE = Path(__file__).parent / "fixtures" / "sample_lichess.pgn"


def _serve(payload: bytes, drop_after: int):
    """HTTP server with Range support whose first response is cut off after drop_after bytes."""
    state = {"requests": [], "dropped": False}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            rng = self.headers.get("Range")
            state["requests"].append(rng)
            start = int(rng.split("=")[1].rstrip("-")) if rng else 0
            body = payload[start:]
            self.send_response(206 if rng else 200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not state["dropped"]:
                state["dropped"] = True
                self.wfile.write(body[:drop_after])
                self.wfile.flush()
                self.connection.shutdown(2)  # simulate the Wi-Fi dropping mid-download
                return
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, state


def test_download_resumes_after_a_dropped_connection(monkeypatch):
    monkeypatch.setattr("chessanalytics.pgn_stream.time.sleep", lambda s: None)
    text = "\n".join(FIXTURE.read_text().replace("AAAA", f"{i:04d}") for i in range(300))
    payload = zstandard.ZstdCompressor().compress(text.encode())
    server, state = _serve(payload, drop_after=len(payload) // 3)
    try:
        games = list(iter_games(f"http://127.0.0.1:{server.server_address[1]}/month.pgn.zst"))
    finally:
        server.shutdown()
    assert len(games) == 1500  # every game, none lost or duplicated at the join
    assert len({g.headers["Site"] for g in games}) == 1500
    assert state["requests"][0] is None and state["requests"][1].startswith("bytes=")


def test_stray_closing_brace_cannot_hang_the_parser():
    g = Game({})
    parse_movetext("1. e4 } e5 ( 1... c5 } ) 2. Nf3 *", g)
    assert g.moves == ["e4", "e5", "Nf3"]
