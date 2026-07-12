"""Analyze NovelForge review quality from real LLM attempt evidence.

Compares a target run (new pipeline) against a baseline (past runs) to measure
the effect of prompt changes (e.g. before/after made optional).

Usage:
    uv run python scripts/analyze_review_quality.py <runs_root> [--baseline <dir>]
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re


def collect_review_attempts(runs_root: str) -> list[tuple[str, str, str, str]]:
    """Return list of (run_id, attnum, stage_op, parsed_path)."""
    out = []
    for rf in glob.glob(f"{runs_root}/**/llm/parsed.json", recursive=True):
        adir = os.path.dirname(os.path.dirname(rf))
        aname = os.path.basename(adir)
        run_dir = os.path.dirname(os.path.dirname(adir))
        m = re.match(r"(att_(\d+))_(\w+?)_(review|revise|generate)_([a-f0-9]+)$", aname)
        if not m:
            continue
        attnum = int(m.group(2))
        stage_op = m.group(3)
        out.append((os.path.basename(run_dir), attnum, stage_op, rf))
    return out


OVER_FLAG_PATTERNS = {
    "absence": r"登場し(ない|ていない)|出てこない|現れない|描写され(ていない|ない)",
    "possibility": r"可能性|かもしれ|恐れ|懸念",
    "should": r"~べき|必要がある|求められる|望ましい",
}
NON_ACTIONABLE = ("対象なし", "なし")


def analyze(attempts: list[tuple[str, str, str, str]]) -> dict:
    by_stage: dict[str, list] = collections.defaultdict(list)
    for _run_id, _attnum, stage_op, rf in attempts:
        if not stage_op.endswith("_review"):
            continue
        stage = stage_op.split("_")[-1]
        try:
            with open(rf, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        by_stage[stage].append(d)

    result = {
        "stage_counts": {k: len(v) for k, v in by_stage.items()},
        "total_issues": 0,
        "empty_after": 0,
        "empty_before": 0,
        "empty_suggestion": 0,
        "non_actionable_sugg": 0,
        "severity": collections.Counter(),
        "over_flag": collections.Counter(),
        "before_after_both": 0,
        "before_after_neither": 0,
    }
    for _stage, ds in by_stage.items():
        for d in ds:
            for it in d.get("issues", []):
                if not isinstance(it, dict):
                    continue
                result["total_issues"] += 1
                sev = it.get("severity")
                result["severity"][sev] += 1
                b = it.get("before")
                a = it.get("after")
                s = it.get("suggestion")
                if b is None or str(b).strip() == "":
                    result["empty_before"] += 1
                if a is None or str(a).strip() == "":
                    result["empty_after"] += 1
                if b is not None and a is not None:
                    result["before_after_both"] += 1
                if b is None and a is None:
                    result["before_after_neither"] += 1
                if s is None or str(s).strip() == "":
                    result["empty_suggestion"] += 1
                elif str(s).strip() in NON_ACTIONABLE:
                    result["non_actionable_sugg"] += 1
                desc = str(it.get("description", ""))
                for name, pat in OVER_FLAG_PATTERNS.items():
                    if re.search(pat, desc):
                        result["over_flag"][name] += 1
    return result


def summarize(label: str, r: dict) -> str:
    tot = r["total_issues"] or 1
    lines = [f"### {label}", f"- stages: {r['stage_counts']}", f"- total issues: {r['total_issues']}"]
    if r["total_issues"]:
        lines.append(f"- empty after: {r['empty_after']} ({r['empty_after']*100//tot}%)")
        lines.append(f"- empty before: {r['empty_before']} ({r['empty_before']*100//tot}%)")
        lines.append(f"- before+after both: {r['before_after_both']} ({r['before_after_both']*100//tot}%)")
        lines.append(f"- before/after neither: {r['before_after_neither']} ({r['before_after_neither']*100//tot}%)")
        lines.append(f"- empty suggestion: {r['empty_suggestion']} | non-actionable: {r['non_actionable_sugg']}")
        sev = " ".join(f"{k}={v}({v*100//tot}%)" for k, v in r["severity"].most_common())
        lines.append(f"- severity: {sev}")
        of = " ".join(f"{k}={v}" for k, v in r["over_flag"].most_common())
        lines.append(f"- over-flag heuristics: {of}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs_root")
    ap.add_argument("--baseline", default=None, help="past runs root to compare against")
    args = ap.parse_args()

    target = analyze(collect_review_attempts(args.runs_root))
    print(summarize(f"TARGET: {args.runs_root}", target))
    if args.baseline:
        base = analyze(collect_review_attempts(args.baseline))
        print()
        print(summarize(f"BASELINE: {args.baseline}", base))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
