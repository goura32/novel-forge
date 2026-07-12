#!/usr/bin/env python3
"""Replay saved ``write.draft.review`` inputs against A/B prompt templates.

The driver never touches a series ledger.  It reads immutable source attempts and
writes a fresh, append-only experiment directory containing every provider
request, raw response, parsed JSON, validation result, and mechanical score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from novel_forge.ab_review import (
    actionability_summary,
    extract_case_from_request,
    render_review_prompt,
    replay_ollama_options,
)
from novel_forge.config import RuntimeConfig
from novel_forge.llm_client import LLMClient
from novel_forge.task_registry import DEFAULT_TASK_REGISTRY

SYSTEM_PROMPT = "あなたは小説執筆支援AIです。与えられた指示と入力に従い、要求されたJSONのみを出力してください。"
PROMPTS_DIR = Path(__file__).parents[1] / "src" / "novel_forge" / "resources" / "prompts"


class ExperimentCapture:
    """Minimal AttemptCapture-compatible immutable writer for one experiment call."""

    def __init__(self, attempt_dir: Path) -> None:
        self._llm_dir = attempt_dir / "llm"
        self._llm_dir.mkdir(parents=True, exist_ok=False)

    def _write(self, name: str, value: Any) -> None:
        path = self._llm_dir / name
        with path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")

    def request(self, payload: dict[str, Any]) -> None:
        self._write("request.json", payload)

    def response_ndjson(self, lines: list[dict[str, Any]]) -> None:
        path = self._llm_dir / "response.ndjson"
        with path.open("x", encoding="utf-8") as stream:
            for line in lines:
                stream.write(json.dumps(line, ensure_ascii=False, sort_keys=True))
                stream.write("\n")

    def response_content(self, content: str) -> None:
        self._write("response.content.json", {"content": content})

    def parsed(self, value: dict[str, Any]) -> None:
        self._write("parsed.json", value)

    def validation(self, value: dict[str, Any]) -> None:
        self._write("validation.json", value)


def main() -> int:
    args = _parse_args()
    candidate_template = args.candidate_template.resolve()
    if not candidate_template.is_file():
        raise ValueError(f"candidate template does not exist: {candidate_template}")
    output = _create_experiment_dir(args.output_dir, args.experiment_id)
    config = RuntimeConfig.load()
    variants = {
        "A": PROMPTS_DIR / "write_draft_review.md",
        "B": candidate_template,
    }
    cases = [_load_case(path, index + 1) for index, path in enumerate(args.source_attempt)]
    seeds = _parse_seeds(args.seeds)
    manifest = {
        "format": "novel-forge-ab-write-review/v1",
        "created_at": _now(),
        "model": config.llm.model,
        "ollama_host": config.llm.ollama_host,
        "timeout_seconds": config.llm.timeout_seconds,
        "ollama_options": {
            key: value
            for key, value in config.llm.ollama_options.items()
            if key not in {"temperature", "top_p"}
        },
        "variants": {name: _digest(path.read_bytes()) for name, path in variants.items()},
        "seeds": seeds,
        "cases": [
            {"case_id": case.case_id, "source_attempt_id": case.source_attempt_id}
            for case in cases
        ],
    }
    _write_json_exclusive(output / "experiment.json", manifest)

    records: list[dict[str, Any]] = []
    for case in cases:
        for variant, template in variants.items():
            prompt = render_review_prompt(template, writer_context=case.writer_context, draft=case.draft)
            for seed in seeds:
                records.append(
                    _replay_one(
                        output=output,
                        case=case,
                        variant=variant,
                        prompt=prompt,
                        prompt_digest=_digest(prompt.encode()),
                        seed=seed,
                        config=config,
                    )
                )
                _write_json_exclusive(
                    output / f"scorecard.partial.{len(records):03d}.json",
                    _scorecard(records),
                )
    _write_json_exclusive(output / "scorecard.json", _scorecard(records))
    print(json.dumps({"experiment_dir": str(output), "scorecard": _scorecard(records)}, ensure_ascii=False))
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-attempt",
        type=Path,
        action="append",
        required=True,
        help="Path to a saved write.draft.review attempt directory. Repeat for each case.",
    )
    parser.add_argument(
        "--candidate-template",
        type=Path,
        required=True,
        help="Path to the isolated B prompt template; it must use {writer_context}, {draft}, and {schema}.",
    )
    parser.add_argument("--output-dir", type=Path, required=True, help="Empty parent directory for a new experiment.")
    parser.add_argument("--experiment-id", help="Optional immutable experiment directory name.")
    parser.add_argument("--seeds", default="101,202,303", help="Comma-separated fixed Ollama seeds.")
    return parser.parse_args()


def _load_case(attempt_dir: Path, index: int):
    request_path = attempt_dir / "llm" / "request.json"
    if not request_path.is_file():
        raise ValueError(f"source attempt has no saved request: {request_path}")
    attempt_path = attempt_dir / "attempt.json"
    attempt_id = attempt_dir.name
    if attempt_path.is_file():
        metadata = json.loads(attempt_path.read_text(encoding="utf-8"))
        attempt_id = str(metadata.get("attempt_id", attempt_id))
        if metadata.get("task_id") != "write.draft.review":
            raise ValueError(f"source attempt is not write.draft.review: {attempt_dir}")
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    return extract_case_from_request(
        case_id=f"case_{index:02d}_{attempt_id}",
        request_payload=payload,
        source_attempt_id=attempt_id,
    )


def _replay_one(
    *,
    output: Path,
    case: Any,
    variant: str,
    prompt: str,
    prompt_digest: str,
    seed: int,
    config: RuntimeConfig,
) -> dict[str, Any]:
    attempt_dir = output / "attempts" / f"{case.case_id}__{variant}__seed_{seed}"
    attempt_dir.mkdir(parents=True, exist_ok=False)
    metadata = {
        "case_id": case.case_id,
        "source_attempt_id": case.source_attempt_id,
        "variant": variant,
        "seed": seed,
        "prompt_digest": prompt_digest,
        "started_at": _now(),
        "model": config.llm.model,
    }
    _write_json_exclusive(attempt_dir / "attempt.json", metadata)
    capture = ExperimentCapture(attempt_dir)
    options = replay_ollama_options(config.llm.ollama_options, seed=seed)
    client = LLMClient(
        api_url=f"http://{config.llm.ollama_host}/api/chat",
        model=config.llm.model,
        timeout_seconds=config.llm.timeout_seconds,
        capture=capture,  # type: ignore[arg-type]
        phase="ab_write_review",
        ollama_options=options,
    )
    try:
        review = client.complete_json(
            kind="write_draft_review_ab",
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            schema=DEFAULT_TASK_REGISTRY.load_schema("write.draft.review"),
        )
    except Exception as exc:
        _write_json_exclusive(
            attempt_dir / "error.json",
            {"error_class": type(exc).__name__, "detail": str(exc), "finished_at": _now()},
        )
        return {**metadata, "status": "error", "error_class": type(exc).__name__}
    summary = actionability_summary(review)
    _write_json_exclusive(attempt_dir / "score.json", summary)
    return {**metadata, "status": "ok", **summary}


def _scorecard(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_variant: dict[str, dict[str, int]] = {}
    for record in records:
        summary = by_variant.setdefault(
            str(record["variant"]),
            {
                "calls": 0,
                "successes": 0,
                "errors": 0,
                "issues": 0,
                "schema_violations": 0,
            },
        )
        summary["calls"] += 1
        if record["status"] != "ok":
            summary["errors"] += 1
            continue
        summary["successes"] += 1
        summary["issues"] += int(record["issue_count"])
        summary["schema_violations"] += int(record["schema_violation_count"])
    return {"records": records, "by_variant": by_variant, "updated_at": _now()}


def _create_experiment_dir(parent: Path, experiment_id: str | None) -> Path:
    parent = parent.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    name = experiment_id or f"ab_write_review_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    path = parent / name
    path.mkdir(exist_ok=False)
    (path / "attempts").mkdir(exist_ok=False)
    return path


def _parse_seeds(raw: str) -> list[int]:
    try:
        seeds = [int(value.strip()) for value in raw.split(",") if value.strip()]
    except ValueError as exc:
        raise ValueError("--seeds must contain integers") from exc
    if not seeds:
        raise ValueError("--seeds must not be empty")
    if len(set(seeds)) != len(seeds):
        raise ValueError("--seeds must be unique")
    return seeds


def _write_json_exclusive(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ab_write_review: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
