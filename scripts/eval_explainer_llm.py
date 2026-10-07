"""Evaluate the explainer with a real local language model (Ollama), for the manual CI job or your own computer.

For every in-scope question in tests/explainer_eval.yaml it records whether the model's answer was kept
("generated") or replaced by the sources because it contained a number not in them ("passages"), whether the
expected numbers from the tables appear (reported, not required), and how long it took. Out-of-scope questions
must still be refused.

    ollama pull llama3.2:1b
    python scripts/eval_explainer_llm.py --model llama3.2:1b --min-kept 0.7
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chessanalytics.explainer import Explainer, Ollama  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama3.2:1b")
    ap.add_argument("--min-kept", type=float, default=0.7,
                    help="minimum share of answers kept (not replaced because of an unsupported number)")
    ap.add_argument("--report", type=Path, help="write a Markdown report here (e.g. $GITHUB_STEP_SUMMARY)")
    a = ap.parse_args()
    llm = Ollama(model=a.model)
    if not llm.available():
        print(f"Ollama is not running or {a.model} is not pulled", file=sys.stderr)
        return 2
    ex = Explainer(generator=llm)
    spec = yaml.safe_load((ROOT / "tests" / "explainer_eval.yaml").read_text())
    rows, failures = [], []
    for item in spec["questions"]:
        if item.get("out_of_scope"):
            if ex.ask(item["q"]).mode != "out of scope":
                failures.append(f"answered an out-of-scope question: {item['q']}")
            continue
        t0 = time.time()
        ans = ex.ask(item["q"])
        secs = time.time() - t0
        missing = [n for n in item.get("numbers", []) if n not in ans.text]
        if ans.mode == "out of scope":
            failures.append(f"refused an in-scope question: {item['q']}")
        rows.append((item["q"], ans.mode, ", ".join(missing) or "-", f"{secs:.1f}"))
    kept = sum(r[1] == "generated" for r in rows) / len(rows)
    lines = [f"### Explainer with {a.model}", "",
             f"{kept:.0%} of {len(rows)} answers kept; the rest contained a number not in the sources and were "
             "replaced by the sources.", "", "| Question | Result | Missing numbers | Seconds |", "|---|---|---|---|"]
    lines += [f"| {q} | {m} | {miss} | {s} |" for q, m, miss, s in rows]
    if kept < a.min_kept:
        failures.append(f"only {kept:.0%} of answers kept (minimum {a.min_kept:.0%})")
    lines += ["", "**Failures**: " + ("; ".join(failures) if failures else "none")]
    report = "\n".join(lines)
    print(report)
    if a.report:
        with open(a.report, "a", encoding="utf-8") as f:
            f.write(report + "\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
