"""Explainer: retrieval quality on an evaluation set, refusals, exact facts, and the guard against invented numbers."""
import io
import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from chessanalytics.explainer import BM25, Explainer, Ollama, numbers_in, tokens, unsupported_numbers

EVAL = yaml.safe_load((Path(__file__).parent / "explainer_eval.yaml").read_text(encoding="utf-8"))["questions"]
TABLES = Path(__file__).parents[1] / "docs" / "tables"


@pytest.fixture(scope="module")
def ex():
    return Explainer()


def test_retrieval_finds_the_right_source_for_every_question(ex):
    misses = []
    for item in [i for i in EVAL if not i.get("out_of_scope")]:
        ans = ex.ask(item["q"])
        titles = [p.title for p in ans.passages]
        if ans.mode == "out of scope" or not set(item["expect"]) & set(titles):
            misses.append((item["q"], titles[:4]))
    hit_rate = 1 - len(misses) / sum(1 for i in EVAL if not i.get("out_of_scope"))
    assert hit_rate >= 0.95, misses  # quality gate: at most 1 miss in 32


def test_out_of_scope_questions_are_refused(ex):
    wrong = [i["q"] for i in EVAL if i.get("out_of_scope") and ex.ask(i["q"]).mode != "out of scope"]
    assert not wrong


def test_answers_carry_the_exact_numbers_from_the_tables(ex):
    for item in [i for i in EVAL if i.get("numbers")]:
        text = ex.ask(item["q"]).text
        for n in item["numbers"]:
            assert n in text, (item["q"], n)


def test_matchup_fact_matches_the_table(ex):
    m = pd.read_csv(TABLES / "matchups.csv")
    row = m[(m.white_setup == "London System") & (m.black_setup == "King's Indian Defence")].iloc[0]
    fact = next(p for p in ex.facts.lookup("London against the King's Indian") if p.kind == "fact")
    assert f"{int(row.games):,} games" in fact.text and f"{row.excess * 100:+.1f} pp" in fact.text


def test_invented_numbers_are_caught_and_sources_shown_instead(ex):
    liar = Explainer(generator=lambda q, ctx: "The bishop pair is worth 9.7 pp [1].")
    ans = liar.ask("What is a bishop pair?")
    assert ans.mode == "passages" and "9.7" in ans.note


def test_faithful_generated_answers_are_kept():
    honest = Explainer(generator=lambda q, ctx: "Having both bishops is worth about 2.5 percentage points [1].")
    ans = honest.ask("What is a bishop pair?")
    assert ans.mode == "generated" and "2.5" in ans.text


def test_generated_answers_always_show_the_table_figures():
    vague = Explainer(generator=lambda q, ctx: "The London is not clearly better than the Dutch [1].")
    ans = vague.ask("Is the London good against the Dutch?")
    assert ans.mode == "generated" and "From the tables" in ans.text and "12,309" in ans.text
    assert "no clear advantage" in ans.text


def test_model_failure_falls_back_to_sources():
    def broken(q, ctx):
        raise ConnectionError("ollama is not running")

    ans = Explainer(generator=broken).ask("What is castling?")
    assert ans.mode == "passages" and "could not be reached" in ans.note


def test_number_helpers():
    assert numbers_in("12,309 games, +0.8 pp and −2.2 pp, 51.8%") == {"12309", "0.8", "2.2", "51.8"}
    assert unsupported_numbers("about 3 games", []) == set()  # small counting words are allowed
    assert unsupported_numbers("worth 2.6 pp", []) == {"2.6"}


def test_bm25_prefers_the_matching_document():
    docs = [tokens("the knight jumps in an L shape"), tokens("rooks like open files")]
    s = BM25(docs).scores(tokens("how does the knight move"))
    assert s[0] > s[1] == 0


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def test_ollama_client_without_a_server():
    seen = []

    def opener(req, timeout=0):
        url = req if isinstance(req, str) else req.full_url
        seen.append(req)
        if url.endswith("/api/tags"):
            return _Resp(json.dumps({"models": [{"name": "llama3.2:3b"}]}).encode())
        body = json.loads(req.data)
        assert body["messages"][0]["role"] == "system" and "Question: hi" in body["messages"][1]["content"]
        return _Resp(json.dumps({"message": {"content": " An answer. "}}).encode())

    model = Ollama(opener=opener)
    assert model.available()
    assert model("hi", "[1] ctx") == "An answer."
    assert not Ollama(opener=lambda *a, **k: (_ for _ in ()).throw(OSError())).available()
