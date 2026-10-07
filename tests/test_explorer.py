"""Explorer client: positions are legal, responses are cached, 429s wait, bad tokens fail clearly. No network."""
import io
import json
import urllib.error

import pytest

from chessanalytics.explorer import POSITIONS, RATING_GROUPS, Explorer, months, to_uci


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def fake_opener(responses, seen):
    def opener(req, timeout=60):
        seen.append(req)
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(json.dumps(item).encode())
    return opener


def http_error(code):
    return urllib.error.HTTPError("https://explorer.lichess.ovh/lichess/history", code, "x", {}, None)


def test_every_tracked_line_is_legal_and_unique():
    ucis = [to_uci(san) for _, san in POSITIONS]
    assert len(set(ucis)) == len(ucis)
    assert to_uci("d4 d5 c4") == "d2d4,d7d5,c2c4"
    assert to_uci("") == ""


def test_months_span():
    assert months("2020-11", "2021-02") == ["2020-11", "2020-12", "2021-01", "2021-02"]
    assert len(months("2013-01", "2026-09")) == 165


def test_history_is_parsed_cached_and_token_sent(tmp_path):
    seen = []
    body = {"history": [{"month": "2020-10", "white": 5, "draws": 1, "black": 4},
                        {"month": "2020-11", "white": 7, "black": 3}]}
    ex = Explorer("secret-token", cache_dir=tmp_path, opener=fake_opener([body], seen), sleep=lambda s: None)
    h = ex.history("d2d4,d7d5,c2c4", RATING_GROUPS["all"], "2020-10", "2020-11")
    assert h[1] == {"month": "2020-11", "white": 7, "draws": 0, "black": 3}
    assert seen[0].get_header("Authorization") == "Bearer secret-token"
    assert "secret-token" not in seen[0].full_url  # never in the URL, so never in the cache file name
    assert ex.history("d2d4,d7d5,c2c4", RATING_GROUPS["all"], "2020-10", "2020-11") == h  # served from cache
    assert len(seen) == 1 and ex.requests_made == 1
    assert all("secret-token" not in p.read_text() for p in tmp_path.iterdir())


def test_rate_limit_waits_a_minute_then_retries(tmp_path):
    seen, waits = [], []
    ex = Explorer("t", cache_dir=tmp_path, opener=fake_opener([http_error(429), {"history": []}], seen),
                  sleep=waits.append, log=lambda *a: None)
    assert ex.history("e2e4", RATING_GROUPS["all"], "2020-01", "2020-02") == []
    assert 60 in waits and len(seen) == 2


def test_bad_token_gives_a_clear_error(tmp_path):
    ex = Explorer("bad", cache_dir=tmp_path, opener=fake_opener([http_error(401)], []), sleep=lambda s: None)
    with pytest.raises(PermissionError, match="LICHESS_TOKEN"):
        ex.history("e2e4", RATING_GROUPS["all"], "2020-01", "2020-02")


def test_month_fallback_reads_totals(tmp_path):
    ex = Explorer("t", cache_dir=tmp_path, opener=fake_opener([{"white": 10, "draws": 2, "black": 8, "moves": []}], []),
                  sleep=lambda s: None)
    assert ex.month_counts("e2e4", RATING_GROUPS["all"], "2020-11") == {"month": "2020-11", "white": 10, "draws": 2,
                                                                         "black": 8}
