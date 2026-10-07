"""A free, local question-answering explainer for people who know nothing about chess (retrieval-augmented).

1. Retrieve: the beginner knowledge base (docs/knowledge) and the results write-up (docs/RESULTS.md) are split into
   sections and ranked with BM25 keyword scoring. Pure Python, nothing to download.
2. Look up facts: opening names in the question are matched against the results tables, and their exact numbers are
   added as "fact" passages. Numbers therefore come from the tables, never from a language model.
3. Answer: if Ollama (a free local model runner) is running, a small model writes a plain-English answer from those
   passages only. Every number in its answer is checked against the passages; if any number is not found there, the
   generated text is rejected and the passages are shown instead. Without Ollama the passages are shown directly.

Out-of-scope questions (nothing relevant found) get a polite refusal instead of a guess.
"""
from __future__ import annotations

import json
import math
import os
import re
import urllib.request
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from difflib import get_close_matches
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE = ROOT / "docs" / "knowledge"
RESULTS = ROOT / "docs" / "RESULTS.md"
TABLES = ROOT / "docs" / "tables"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")  # from Docker: http://host.docker.internal:11434
DEFAULT_MODEL = "llama3.2:3b"
MIN_SCORE = 2.0  # below this best BM25 score, and with no facts found, the question is treated as out of scope

DOMAIN_WORDS = """chess board square rank piece pieces pawn pawns king queen rook bishop knight move moves opening
openings middlegame endgame endgames game games draw draws drawn drawish checkmate check stalemate castle castling
castled rating ratings elo glicko lichess clock clocks bullet blitz rapid classical gambit gambits defence defense
sacrifice sacrifices material edge pp percentage confidence interval prediction predictions accuracy model models engine
evaluation eval trend trends share popularity netflix lockdown pandemic forecast forecasting outpost fianchetto
structure isolated doubled backward passed island islands hanging space centre development developed trade trades
conversion promote promotion matchup project notation system systems variation attack play played opponent""".split()
# everyday words that only count as chess when an opening is also named ("play the French", "London System",
# "does the London suit weaker players")
WEAK = {"system", "systems", "variation", "attack", "play", "played", "opponent", "game", "games", "move", "moves",
        "player", "players", "weaker", "stronger", "beginner", "beginners", "club", "level", "better", "worse"}
# opening names that are also everyday words: they only count as chess when the question has other chess context
AMBIGUOUS = {"london", "english", "french", "dutch", "italian", "spanish", "scotch", "bird", "berlin", "vienna", "kid"}

STOP = set("""a an and are as at be by can do does for from has have how i if in into is it its me of on or so that
the their then there these this to was what when where which who why will with you your about than more most
much very also just""".split())


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9']+", text.lower().replace("’", "'"))
    out = []
    for w in words:
        w = w.strip("'")
        if not w or w in STOP:
            continue
        for suffix in ("'s", "ing", "es", "s"):  # light stemming
            if w.endswith(suffix) and len(w) - len(suffix) >= 3:
                w = w[: -len(suffix)]
                break
        out.append(w)
    return out


@dataclass
class Passage:
    source: str  # file or table name
    title: str
    text: str
    kind: str = "text"  # "text" or "fact"

    def cite(self) -> str:
        return f"{self.source} — {self.title}"


def split_markdown(path: Path) -> list[Passage]:
    """One passage per '##' section (falling back to '#' sections); images and tables are dropped."""
    text = path.read_text(encoding="utf-8")
    passages, title, buf = [], path.stem, []

    def flush():
        body = "\n".join(line for line in buf if not line.startswith("![")).strip()
        if body:
            passages.append(Passage(path.name, title, body))

    for line in text.splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            flush()
            title, buf = m.group(2).strip(), []
        else:
            buf.append(line)
    flush()
    return passages


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.4, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.avg = sum(map(len, docs)) / max(1, len(docs))
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in docs]

    def scores(self, query: list[str]) -> list[float]:
        out = []
        for tf, d in zip(self.tf, self.docs, strict=True):
            s = 0.0
            for t in query:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(d) / self.avg))
            out.append(s)
        return out


# ---- facts from the results tables -------------------------------------------------------------------------------

ALIASES = {  # common ways of naming openings -> labels used in the tables
    "london": "London System", "jobava": "Jobava London", "queen's gambit": "Queen's Gambit",
    "queens gambit": "Queen's Gambit", "king's gambit": "King's Gambit", "kings gambit": "King's Gambit",
    "scotch": "Scotch Game", "italian": "Italian Game", "ruy lopez": "Ruy Lopez", "spanish": "Ruy Lopez",
    "catalan": "Catalan", "english": "English Opening", "reti": "Réti Opening", "réti": "Réti Opening",
    "colle": "Colle / Zukertort", "trompowsky": "Trompowsky Attack", "vienna": "Vienna Game",
    "smith-morra": "Smith-Morra Gambit", "alapin": "Alapin Sicilian", "bird": "Bird Opening",
    "sicilian": "Sicilian Defence", "caro-kann": "Caro-Kann Defence", "caro kann": "Caro-Kann Defence",
    "caro": "Caro-Kann Defence", "french": "French Defence", "scandinavian": "Scandinavian Defence",
    "pirc": "Pirc / Modern Defence", "alekhine": "Alekhine Defence", "king's indian": "King's Indian Defence",
    "kings indian": "King's Indian Defence", "kid": "King's Indian Defence", "grunfeld": "Grünfeld Defence",
    "grünfeld": "Grünfeld Defence", "nimzo": "Nimzo-Indian Defence", "slav": "Slav Defence",
    "benoni": "Benoni Defence", "benko": "Benko Gambit", "budapest": "Budapest Gambit", "englund": "Englund Gambit",
    "petrov": "Petrov Defence", "philidor": "Philidor Defence", "berlin": "Berlin Defence",
    "queen's gambit accepted": "Queen's Gambit Accepted", "qga": "Queen's Gambit Accepted",
    "queen's gambit declined": "Queen's Gambit Declined", "qgd": "Queen's Gambit Declined",
    "dutch": "Dutch", "leningrad": "Dutch: Leningrad", "stonewall": "Dutch: Stonewall",
}


def _pp(x: float) -> str:
    return f"{x * 100:+.1f} pp"


class Facts:
    """Exact numbers from docs/tables for the openings named in a question."""

    def __init__(self, tables: Path = TABLES):
        self.white = pd.read_csv(tables / "white_setups.csv", index_col=0)
        self.black = pd.read_csv(tables / "black_defences.csv", index_col=0)
        self.match = pd.read_csv(tables / "matchups.csv")
        self.london_band = pd.read_csv(tables / "london_by_band.csv", index_col=0)

    def entities(self, question: str) -> list[str]:
        q = question.lower().replace("’", "'")
        found: list[tuple[int, str]] = []
        for alias in sorted(ALIASES, key=len, reverse=True):  # longest first, so "queen's gambit accepted" wins
            for pos in re.finditer(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", q):
                if ALIASES[alias] not in [e for _, e in found]:
                    found.append((pos.start(), ALIASES[alias]))
                q = q[: pos.start()] + " " * len(alias) + q[pos.end():]  # blank it so shorter aliases skip it
        if not found:  # fall back to fuzzy matching of whole table labels
            labels = list(self.white.index) + list(self.black.index)
            for word in re.findall(r"[a-z][a-z'\-]{4,}", q):
                for m in get_close_matches(word, [lab.lower() for lab in labels], n=1, cutoff=0.88):
                    found.append((q.find(word), next(lab for lab in labels if lab.lower() == m)))
        return [e for _, e in sorted(found)]

    def _row_text(self, label: str, row: pd.Series, side: str) -> str:
        ci = row.ci95
        verdict = "too small to tell apart from chance, so no clear advantage either way" if abs(row.excess) <= ci \
            else ("a real advantage for White beyond what the ratings predict" if row.excess > 0 else
                  "a real advantage for Black beyond what the ratings predict")
        return (f"{label} ({side}): {int(row.games):,} games; White scored {row.white_score * 100:.1f}% against "
                f"{row.expected * 100:.1f}% predicted by the ratings, an edge for White of {_pp(row.excess)} "
                f"± {ci * 100:.1f} pp, {verdict}. Draw rate {row.draw_rate * 100:.1f}%.")

    def lookup(self, question: str) -> list[Passage]:
        ents = self.entities(question)
        out: list[Passage] = []
        whites = [e for e in ents if e in self.white.index]
        blacks = [e for e in ents if e in self.black.index or e == "Dutch"]
        for w in whites:
            for b in blacks:
                rows = self.match[(self.match.white_setup == w) & (
                    self.match.black_setup.str.startswith("Dutch") if b == "Dutch" else self.match.black_setup == b)]
                if len(rows):
                    g = rows.games.sum()
                    excess = (rows.excess * rows.games).sum() / g
                    ci = math.sqrt(((rows.ci95 * rows.games) ** 2).sum()) / g
                    row = pd.Series({"games": g, "excess": excess, "ci95": ci,
                                     "white_score": (rows.white_score * rows.games).sum() / g,
                                     "expected": (rows.expected * rows.games).sum() / g,
                                     "draw_rate": (rows.draw_rate * rows.games).sum() / g})
                    out.append(Passage("matchups.csv", f"{w} against {b}",
                                       self._row_text(f"{w} against {b}", row, "matchup"), "fact"))
        for w in whites:
            out.append(Passage("white_setups.csv", w, self._row_text(w, self.white.loc[w], "White system"), "fact"))
            if w == "London System":
                parts = [f"{band}: {_pp(r.excess)}" for band, r in self.london_band.iterrows()]
                out.append(Passage("london_by_band.csv", "London System by rating",
                                   "London System edge for White by average rating: " + "; ".join(parts) + ".",
                                   "fact"))
        for b in blacks:
            if b == "Dutch":
                for lab in [x for x in self.black.index if x.startswith("Dutch")]:
                    out.append(Passage("black_defences.csv", lab, self._row_text(lab, self.black.loc[lab],
                                                                                 "Black defence"), "fact"))
            else:
                out.append(Passage("black_defences.csv", b, self._row_text(b, self.black.loc[b], "Black defence"),
                                   "fact"))
        return out


# ---- the explainer -------------------------------------------------------------------------------------------------

@dataclass
class Answer:
    text: str
    mode: str  # "generated", "passages" or "out of scope"
    passages: list[Passage] = field(default_factory=list)
    note: str = ""


NUMBER = re.compile(r"(?<![\w.])[-+−]?\d[\d,]*(?:\.\d+)?")


def numbers_in(text: str) -> set[str]:
    out = set()
    for m in NUMBER.findall(text):
        n = m.replace(",", "").replace("−", "-").lstrip("+")
        try:
            out.add(f"{abs(float(n)):g}")
        except ValueError:
            continue
    return out


def unsupported_numbers(answer: str, passages: list[Passage]) -> set[str]:
    """Numbers in the answer that appear in none of the passages (small integers such as 1 to 10 are allowed)."""
    allowed = set().union(*(numbers_in(p.text + " " + p.title) for p in passages)) if passages else set()
    return {n for n in numbers_in(answer) if n not in allowed and not (float(n).is_integer() and float(n) <= 10)}


SYSTEM_PROMPT = (
    "You explain chess and the results of a chess data project to someone who knows nothing about chess or "
    "statistics. Answer in plain, everyday English in at most 150 words.\n"
    "Rules:\n"
    "1. Use ONLY the numbered sources provided. Do not add chess knowledge of your own.\n"
    "2. Start with a one-sentence direct answer. Then give the most important numbers from the sources (for example "
    "the number of games and the edge in pp), copied exactly as written, and say in simple words what they mean. "
    "Never calculate or invent numbers.\n"
    "3. Avoid statistical jargon. Instead of 'not distinguishable from zero' or 'not significant', say the effect is "
    "too small to tell apart from chance. Explain 'pp' as percentage points the first time you use it.\n"
    "4. Do not draw conclusions stronger than the sources: a small or uncertain effect means 'no clear advantage', "
    "not 'it does not work'.\n"
    "5. Cite sources like [1] or [2] after the sentences that use them.\n"
    "6. If the sources do not answer the question, say you can only answer questions about chess basics and this "
    "project."
)


class Ollama:
    def __init__(self, model: str = DEFAULT_MODEL, url: str = OLLAMA_URL, timeout: float = 120,
                 opener: Callable = urllib.request.urlopen):
        self.model, self.url, self.timeout, self.opener = model, url, timeout, opener

    def available(self) -> bool:
        try:
            with self.opener(f"{self.url}/api/tags", timeout=2) as r:  # noqa: S310 - local service
                names = {m["name"] for m in json.loads(r.read()).get("models", [])}
            return self.model in names or f"{self.model}:latest" in names
        except Exception:  # noqa: BLE001 - any failure simply means "not available"
            return False

    def __call__(self, question: str, context: str) -> str:
        body = json.dumps({"model": self.model, "stream": False, "options": {"temperature": 0.1},
                           "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                                        {"role": "user", "content": f"Sources:\n{context}\n\nQuestion: {question}"}]})
        req = urllib.request.Request(f"{self.url}/api/chat", data=body.encode(),  # noqa: S310 - local service
                                     headers={"Content-Type": "application/json"})
        with self.opener(req, timeout=self.timeout) as r:  # noqa: S310
            return json.loads(r.read())["message"]["content"].strip()


class Explainer:
    def __init__(self, generator: Callable[[str, str], str] | None = None, k: int = 4):
        self.passages: list[Passage] = []
        for path in sorted(KNOWLEDGE.glob("*.md")) + [RESULTS]:
            self.passages += split_markdown(path)
        self.index = BM25([tokens(p.title + " " + p.title + " " + p.text) for p in self.passages])
        self.facts = Facts()
        self.generator, self.k = generator, k
        unambiguous = [a for a in ALIASES if a not in AMBIGUOUS]
        self.domain = set(tokens(" ".join(DOMAIN_WORDS + unambiguous))) - set(tokens(" ".join(WEAK)))
        self.weak = set(tokens(" ".join(WEAK)))

    def in_scope(self, question: str) -> bool:
        """A chess or project word, or at least two opening names. Everyday words ("good", "today") and a lone
        place-like name ("What time is it in London?") do not count."""
        toks = tokens(question)
        if any(t in self.domain for t in toks):
            return True
        n_entities = len(self.facts.entities(question))
        return n_entities >= 2 or (n_entities == 1 and any(t in self.weak for t in toks))

    def retrieve(self, question: str) -> tuple[list[Passage], float]:
        """Top passages, and the best score from words alone (numbers such as years do not count towards relevance,
        so "Who won in 2026?" is not treated as a question about this project)."""
        q = tokens(question)
        scores = self.index.scores(q)
        words = [t for t in q if not t.isdigit()]
        word_scores = self.index.scores(words) if words else [0.0] * len(scores)
        ranked = sorted(range(len(scores)), key=lambda i: -scores[i])
        return [self.passages[i] for i in ranked[: self.k] if scores[i] > 0], max(word_scores, default=0.0)

    def ask(self, question: str) -> Answer:
        facts = self.facts.lookup(question)
        texts, best = self.retrieve(question)
        if not self.in_scope(question) or (not facts and best < MIN_SCORE):
            return Answer("I can only answer questions about chess basics and this project's results. Try asking "
                          "about an opening, a chess term such as 'bishop pair', or what a number means.",
                          "out of scope")
        passages = facts + texts
        if self.generator is not None:
            context = "\n\n".join(f"[{i}] {p.title}: {p.text}" for i, p in enumerate(passages, 1))
            try:
                text = self.generator(question, context)
            except Exception as exc:  # noqa: BLE001 - fall back to passages if the local model fails
                return Answer(self._passage_answer(passages), "passages", passages,
                              f"The local model could not be reached ({type(exc).__name__}); showing sources.")
            bad = unsupported_numbers(text, passages)
            if not bad:
                if facts:  # the key figures always come straight from the tables, whatever the model wrote
                    text += f"\n\n**From the tables:** {facts[0].text}"
                return Answer(text, "generated", passages)
            return Answer(self._passage_answer(passages), "passages", passages,
                          f"The generated answer contained numbers not found in the sources ({', '.join(sorted(bad))})"
                          ", so the sources are shown instead.")
        return Answer(self._passage_answer(passages), "passages", passages)

    @staticmethod
    def _passage_answer(passages: list[Passage]) -> str:
        parts = [f"**{p.title}**: {p.text}" for p in passages[:4]]
        return "\n\n".join(parts)
