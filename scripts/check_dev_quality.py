#!/usr/bin/env python3
"""Run NovelForge local development quality gates.

This is intentionally a local gate, not CI. It keeps the command sequence in one
place so developers can run the same verification before committing.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from time import monotonic


@dataclass(frozen=True)
class Gate:
    name: str
    command: tuple[str, ...]
    full_only: bool = False


GATES: tuple[Gate, ...] = (
    Gate("pytest", ("uv", "run", "pytest", "tests", "-q")),
    Gate("ruff", ("uv", "run", "ruff", "check", "src/novel_forge", "tests", "scripts")),
    Gate(
        "mypy",
        ("uv", "run", "mypy", "src/novel_forge", "tests", "--show-error-codes"),
    ),
    Gate("prompt placeholders", ("uv", "run", "python", "scripts/validate_prompts.py")),
    Gate("build", ("uv", "build"), full_only=True),
)


def run_gate(gate: Gate) -> int:
    command_text = " ".join(gate.command)
    print(f"\n=== {gate.name}: {command_text} ===", flush=True)
    start = monotonic()
    completed = subprocess.run(gate.command, check=False)
    elapsed = monotonic() - start
    if completed.returncode == 0:
        print(f"✅ {gate.name} passed ({elapsed:.1f}s)", flush=True)
    else:
        print(f"❌ {gate.name} failed with exit code {completed.returncode} ({elapsed:.1f}s)", flush=True)
    return completed.returncode


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run NovelForge local development quality gates.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Also run slower release-readiness gates such as uv build.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop at the first failing gate instead of running all selected gates.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    selected_gates = [gate for gate in GATES if args.full or not gate.full_only]

    failures: list[str] = []
    for gate in selected_gates:
        exit_code = run_gate(gate)
        if exit_code != 0:
            failures.append(gate.name)
            if args.fail_fast:
                break

    print("\n=== summary ===", flush=True)
    if failures:
        print(f"❌ failed gates: {', '.join(failures)}", flush=True)
        return 1

    mode = "full" if args.full else "fast"
    print(f"✅ all {mode} quality gates passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
