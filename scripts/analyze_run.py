#!/usr/bin/env python3
"""Analyze a novel-forge run directory and report quality/crash metrics.

Usage:
    uv run python scripts/analyze_run.py <run_dir>

Reads every att_*/llm/parsed.json for review/revise attempts and aggregates:
  - crash signals in the run log (RuntimeContractError / Traceback / schema)
  - per-stem review issue counts, contradiction rate, no-op rate, undefined-term rate
  - overall contradiction rate per design/write stage

This is used to measure prompt-improvement impact across full runs (not
mid-run, where prompt edits distort before/after windows).
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

CONTRA_KW = ["矛盾", "不整合", "整合", "一貫", "食い違", "canon", "結界", "年代", "定義"]
NOOP_KW = ["no-op", "重複", "空更新"]
UNDEF_KW = ["定義", "未定義", "不明", "導入"]


def load_parsed(attempt_dir: str):
    p = os.path.join(attempt_dir, "llm", "parsed.json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return None
    return None


def is_contra(issue: dict) -> bool:
    if not isinstance(issue, dict):
        return False
    t = (issue.get("description", "") + issue.get("issue", "")).lower()
    return any(k in t for k in CONTRA_KW)


def is_noop(issue: dict) -> bool:
    if not isinstance(issue, dict):
        return False
    t = issue.get("description", "") + issue.get("issue", "")
    return any(k in t for k in NOOP_KW)


def is_undef(issue: dict) -> bool:
    if not isinstance(issue, dict):
        return False
    t = issue.get("description", "") + issue.get("issue", "")
    return "定義" in t and ("ない" in t or "未" in t or "欠如" in t)


def main(run_dir: str) -> int:
    if not os.path.isdir(run_dir):
        print(f"not a dir: {run_dir}", file=sys.stderr)
        return 1

    attempts = sorted(glob.glob(os.path.join(run_dir, "attempts", "att_*")))
    stem_stats = defaultdict(lambda: Counter())
    total_issues = total_contra = total_noop = total_undef = 0
    review_attempts = 0

    for f in attempts:
        base = os.path.basename(f)
        m = re.match(r"att_\d+_(\w+)_(review|revise)_", base)
        if not m:
            continue
        stem, kind = m.group(1), m.group(2)
        d = load_parsed(f)
        if not d or "issues" not in d:
            continue
        issues = d["issues"]
        if kind == "review":
            review_attempts += 1
            n = len(issues)
            nc = sum(1 for it in issues if is_contra(it))
            nn = sum(1 for it in issues if is_noop(it))
            nu = sum(1 for it in issues if is_undef(it))
            stem_stats[stem]["reviews"] += 1
            stem_stats[stem]["issues"] += n
            stem_stats[stem]["contra"] += nc
            stem_stats[stem]["noop"] += nn
            stem_stats[stem]["undef"] += nu
            total_issues += n
            total_contra += nc
            total_noop += nn
            total_undef += nu

    print(f"=== run: {run_dir} ===")
    print(f"attempts total: {len(attempts)}")
    print(f"review attempts: {review_attempts}")
    print(f"total issues: {total_issues}  contradiction: {total_contra} "
          f"({total_contra/max(total_issues,1)*100:.0f}%)  "
          f"no-op: {total_noop}  undefined-term: {total_undef}")
    print()
    print(f"{'stem':24} {'rev':>4} {'iss':>5} {'con':>5} {'con%':>5} {'noop':>5} {'und':>4}")
    for stem, c in sorted(stem_stats.items(), key=lambda x: -x[1]["issues"]):
        iss = c["issues"]
        con = c["contra"]
        print(f"{stem:24} {c['reviews']:>4} {iss:>5} {con:>5} "
              f"{con/max(iss,1)*100:>4.0f}% {c['noop']:>5} {c['undef']:>4}")

    # crash signals: caller passes log path via env or we skip
    log = os.environ.get("RUN_LOG")
    if log and os.path.exists(log):
        txt = open(log, encoding="utf-8", errors="ignore").read()
        crashes = sum(
            txt.count(s)
            for s in ["RuntimeContractError", "Traceback", "LLMError: schema"]
        )
        print(f"\ncrash signals in log: {crashes}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: analyze_run.py <run_dir>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
