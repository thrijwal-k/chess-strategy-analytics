"""Dashboard smoke test: the app runs on the committed summary tables without errors and shows London vs Dutch."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).parents[1] / "app.py")


def test_ask_tab_answers_and_refuses(monkeypatch):
    monkeypatch.setenv("EXPLAINER_NO_LLM", "1")
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.text_input(key="question").input("What is a bishop pair?").run()
    assert not at.exception
    assert any("Bishop pair" in m.value for m in at.markdown)
    assert any(c.value.startswith("Bishop pair:") for c in at.caption)  # the board diagram is drawn
    at.text_input(key="question").input("Is the London good against the Dutch?").run()
    assert any(c.value.startswith("London System against Dutch: 1.d4 f5") for c in at.caption)
    at.text_input(key="question").input("What is the capital of France?").run()
    assert any("only answer questions" in w.value for w in at.warning)


def test_app_runs_and_defaults_to_london_vs_dutch():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert at.selectbox[0].value == "London System"
    assert at.selectbox[1].value.startswith("Dutch")
    assert any("Edge for White" in m.label for m in at.metric)


def test_changing_the_matchup_updates_the_numbers():
    at = AppTest.from_file(APP, default_timeout=60).run()
    before = [m.value for m in at.metric]
    at.selectbox[0].set_value("Queen's Gambit").run()
    at.selectbox[1].set_value("Queen's Gambit Accepted").run()
    assert not at.exception
    assert [m.value for m in at.metric] != before


def test_chances_calculator_follows_the_inputs():
    at = AppTest.from_file(APP, default_timeout=60).run()

    def chances():
        m = {x.label: int(x.value.rstrip("%")) for x in at.metric if x.label in ("White wins", "Draw", "Black wins")}
        assert 98 <= sum(m.values()) <= 102
        return m

    even = chances()
    assert abs(even["White wins"] - even["Black wins"]) < 10
    at.number_input(key="calc_white").set_value(1900).run()
    assert chances()["White wins"] > 75
    at.number_input(key="calc_white").set_value(1500).run()
    at.toggle(key="calc_during").set_value(True).run()
    at.slider(key="calc_mat").set_value(9).run()
    assert chances()["White wins"] > 70
    at.slider(key="calc_mat").set_value(-9).run()
    assert chances()["Black wins"] > 70
    assert not at.exception
