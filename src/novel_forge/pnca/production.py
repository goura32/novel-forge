"""Production adapters for the first PNCA authoring task."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from novel_forge.pnca.defaults import default_pnca_task_registry
from novel_forge.pnca.registry import PNCATaskExecutor
from novel_forge.prompts import PromptManager
from novel_forge.runtime import ArtifactReference, RunHandle, RunRepository

_SYSTEM_PROMPT = "あなたは小説執筆支援AIです。与えられた指示と入力に従い、要求されたJSONのみを出力してください。"


def stage_series_request(
    *,
    repository: RunRepository,
    run: RunHandle,
    request_id: str,
    keywords: str,
    existing_slugs: tuple[str, ...],
) -> ArtifactReference:
    """Commit unmodified CLI planning intent before it reaches an LLM."""
    attempt = repository.start_attempt(
        run,
        task_id="pnca.series.request",
        phase="plan",
        reason="stage immutable series request",
    )
    return repository.commit_artifact(
        attempt,
        artifact_type="pnca.series.request",
        logical_key=f"pnca.series.request.{request_id}",
        payload={"keywords": keywords, "existing_slugs": list(existing_slugs)},
        payload_name="request.json",
    )


def stage_volume_request(
    *,
    repository: RunRepository,
    run: RunHandle,
    series_id: str,
    volume_ordinal: int,
) -> ArtifactReference:
    """Commit one CLI volume target as a provider-visible immutable input."""
    attempt = repository.start_attempt(run, task_id="pnca.volume.request", phase="design", reason="stage immutable volume request")
    return repository.commit_artifact(
        attempt,
        artifact_type="pnca.volume.request",
        logical_key=f"pnca.volume.request.{series_id}.{volume_ordinal:03d}",
        payload={"volume_ordinal": volume_ordinal},
        payload_name="request.json",
    )


def stage_chapter_request(
    *,
    repository: RunRepository,
    run: RunHandle,
    volume_id: str,
    chapter_ordinal: int,
) -> ArtifactReference:
    """Commit one CLI chapter target as a provider-visible immutable input."""
    attempt = repository.start_attempt(
        run,
        task_id="pnca.chapter.request",
        phase="design",
        reason="stage immutable chapter request",
    )
    return repository.commit_artifact(
        attempt,
        artifact_type="pnca.chapter.request",
        logical_key=f"pnca.chapter.request.{volume_id}.{chapter_ordinal:03d}",
        payload={"chapter_ordinal": chapter_ordinal},
        payload_name="request.json",
    )

def make_pnca_task_executor(*, client: Any, manager: PromptManager | None = None) -> PNCATaskExecutor:
    """Build the production provider adapter from registered PNCA task resources."""
    prompt_manager = manager or PromptManager()
    resources_by_task = {
        "pnca.series.contract": ("pnca_series_contract.md", "pnca_series_contract.json"),
        "pnca.volume.contract": ("pnca_volume_contract.md", "pnca_volume_contract.json"),
        "pnca.chapter.contract": ("pnca_chapter_contract.md", "pnca_chapter_contract.json"),
    }
    schemas = {
        task_id: json.loads(
            (resources.files("novel_forge") / "resources" / "schemas" / schema_name).read_text(encoding="utf-8")
        )
        for task_id, (_prompt_name, schema_name) in resources_by_task.items()
    }

    def provider(task_id: str, projection: dict[str, Any], operation_key: str) -> Any:
        try:
            prompt_name, _schema_name = resources_by_task[task_id]
            schema = schemas[task_id]
        except KeyError as exc:
            raise ValueError(f"production PNCA provider does not implement task: {task_id}") from exc
        variables = {
            "request": json.dumps(projection["request"], ensure_ascii=False),
            "schema": json.dumps(schema, ensure_ascii=False, indent=2),
        }
        if task_id in {"pnca.volume.contract", "pnca.chapter.contract"}:
            variables["parent"] = json.dumps(projection["parent"], ensure_ascii=False)
        user_prompt = prompt_manager.render(prompt_name, variables)
        return client.complete_json(
            kind=task_id,
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            schema=schema,
        )

    return PNCATaskExecutor(registry=default_pnca_task_registry(), provider=provider)
