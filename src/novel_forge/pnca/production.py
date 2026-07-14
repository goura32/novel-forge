"""Production adapters for the first PNCA authoring task."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any, cast

from novel_forge.llm_client import SchemaEchoError, SchemaValidationError
from novel_forge.pnca.defaults import default_pnca_task_registry
from novel_forge.pnca.registry import PNCATaskExecutor
from novel_forge.prompts import PromptManager, _build_simplified_schema
from novel_forge.runtime import ArtifactReference, AttemptCapture, RunHandle, RunRepository

_SYSTEM_PROMPT = "あなたは小説執筆支援AIです。与えられた指示と入力に従い、要求されたJSONのみを出力してください。"


def stage_series_request(
    *,
    repository: RunRepository,
    run: RunHandle,
    request_id: str,
    keywords: str,
    existing_slugs: tuple[str, ...],
    volume_count: int | None = None,
) -> ArtifactReference:
    """Commit unmodified CLI planning intent before it reaches an LLM."""
    if volume_count is not None and volume_count < 1:
        raise ValueError("volume_count must be >= 1 when supplied")
    payload: dict[str, Any] = {"keywords": keywords, "existing_slugs": list(existing_slugs)}
    if volume_count is not None:
        payload["volume_count"] = volume_count
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
        payload=payload,
        payload_name="request.json",
    )


def stage_volume_request(
    *,
    repository: RunRepository,
    run: RunHandle,
    series_id: str,
    volume_ordinal: int,
    min_chapters: int = 10,
    max_chapters: int = 14,
    min_scene_slots: int = 2,
    max_scene_slots: int = 5,
    min_total_scene_slots: int = 32,
    max_total_scene_slots: int = 45,
    max_five_scene_chapters: int = 2,
) -> ArtifactReference:
    """Commit one CLI volume target and its immutable topology bounds."""
    if min_chapters < 1 or max_chapters < min_chapters:
        raise ValueError("chapter bounds must satisfy 1 <= min <= max")
    if min_scene_slots < 1 or max_scene_slots < min_scene_slots:
        raise ValueError("scene slot bounds must satisfy 1 <= min <= max")
    if min_total_scene_slots < 1 or max_total_scene_slots < min_total_scene_slots:
        raise ValueError("volume scene bounds must satisfy 1 <= min <= max")
    if max_five_scene_chapters < 0:
        raise ValueError("max_five_scene_chapters must be >= 0")
    attempt = repository.start_attempt(run, task_id="pnca.volume.request", phase="design", reason="stage immutable volume request")
    return repository.commit_artifact(
        attempt,
        artifact_type="pnca.volume.request",
        logical_key=f"pnca.volume.request.{series_id}.{volume_ordinal:03d}",
        payload={
            "volume_ordinal": volume_ordinal,
            "min_chapters": min_chapters,
            "max_chapters": max_chapters,
            "min_scene_slots": min_scene_slots,
            "max_scene_slots": max_scene_slots,
            "min_total_scene_slots": min_total_scene_slots,
            "max_total_scene_slots": max_total_scene_slots,
            "max_five_scene_chapters": max_five_scene_chapters,
        },
        payload_name="request.json",
    )


def stage_chapter_request(
    *,
    repository: RunRepository,
    run: RunHandle,
    volume_id: str,
    chapter_ordinal: int,
    min_scene_slots: int = 2,
    max_scene_slots: int = 5,
    scene_slot_count: int | None = None,
) -> ArtifactReference:
    """Commit one CLI chapter target with bounded or selected scene topology."""
    if min_scene_slots < 1 or max_scene_slots < min_scene_slots:
        raise ValueError("scene slot bounds must satisfy 1 <= min <= max")
    if scene_slot_count is not None and not min_scene_slots <= scene_slot_count <= max_scene_slots:
        raise ValueError("scene_slot_count must fall inside the scene slot bounds")
    attempt = repository.start_attempt(
        run,
        task_id="pnca.chapter.request",
        phase="design",
        reason="stage immutable chapter request",
    )
    payload: dict[str, int] = {
        "chapter_ordinal": chapter_ordinal,
        "min_scene_slots": min_scene_slots,
        "max_scene_slots": max_scene_slots,
    }
    if scene_slot_count is not None:
        payload["scene_slot_count"] = scene_slot_count
    return repository.commit_artifact(
        attempt,
        artifact_type="pnca.chapter.request",
        logical_key=f"pnca.chapter.request.{volume_id}.{chapter_ordinal:03d}",
        payload=payload,
        payload_name="request.json",
    )

def stage_scene_request(
    *,
    repository: RunRepository,
    run: RunHandle,
    chapter_id: str,
    slot_id: str,
    is_terminal_scene: bool = False,
) -> ArtifactReference:
    """Commit one Chapter-owned Scene slot as a provider-visible immutable input."""
    attempt = repository.start_attempt(
        run,
        task_id="pnca.scene.request",
        phase="design",
        reason="stage immutable scene request",
    )
    return repository.commit_artifact(
        attempt,
        artifact_type="pnca.scene.request",
        logical_key=f"pnca.scene.request.{chapter_id}.{slot_id}",
        payload={"slot_id": slot_id, "is_terminal_scene": is_terminal_scene},
        payload_name="request.json",
    )


def _phase_for_task(task_id: str) -> str:
    if task_id == "pnca.series.contract":
        return "plan"
    if task_id.endswith(".contract"):
        return "design"
    return "write"


def make_pnca_task_executor(
    *,
    client: Any,
    manager: PromptManager | None = None,
    repository: RunRepository | None = None,
    run: RunHandle | None = None,
    max_generation_attempts: int = 1,
) -> PNCATaskExecutor:
    """Build the production adapter with bounded retries for invalid LLM contract output."""
    if max_generation_attempts < 1:
        raise ValueError("max_generation_attempts must be >= 1")
    if (repository is None) != (run is None):
        raise ValueError("repository and run must be supplied together for production LLM evidence")
    prompt_manager = manager or PromptManager()
    resources_by_task = {
        "pnca.series.contract": ("pnca_series_contract.md", "pnca_series_contract.json"),
        "pnca.volume.contract": ("pnca_volume_contract.md", "pnca_volume_contract.json"),
        "pnca.chapter.contract": ("pnca_chapter_contract.md", "pnca_chapter_contract.json"),
        "pnca.scene.contract": ("pnca_scene_contract.md", "pnca_scene_contract.json"),
        "pnca.writer_view.review": ("pnca_writer_view_review.md", "review_issues.json"),
        "pnca.writer_view.revise": ("pnca_writer_view_revise.md", "pnca_writer_view_revise.json"),
        "pnca.scene.render": ("pnca_scene_render.md", "pnca_scene_render.json"),
        "pnca.scene.rerender": ("pnca_scene_rerender.md", "pnca_scene_render.json"),
        "pnca.scene.coverage": ("pnca_scene_coverage.md", "pnca_scene_coverage.json"),
        "pnca.scene.revise": ("pnca_scene_revise.md", "pnca_scene_revise.json"),
        "pnca.draft.audit": ("pnca_draft_audit.md", "pnca_draft_audit.json"),
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
        variables: dict[str, str] = {
            "schema": _build_simplified_schema(schema),
        }
        if task_id == "pnca.writer_view.review":
            variables["writer_view"] = json.dumps(projection["writer_view"], ensure_ascii=False)
        elif task_id == "pnca.writer_view.revise":
            variables["writer_view"] = json.dumps(projection["writer_view"], ensure_ascii=False)
            variables["issues"] = json.dumps(projection["issues"], ensure_ascii=False)
        elif task_id == "pnca.scene.render":
            variables["start_context"] = json.dumps(projection["writer_view"]["start_context"], ensure_ascii=False)
            variables["narrative_contract"] = json.dumps(projection["writer_view"]["narrative_contract"], ensure_ascii=False)
            variables["end_constraints"] = json.dumps(projection["writer_view"]["end_constraints"], ensure_ascii=False)
            variables["presentation_constraints"] = json.dumps(
                projection["writer_view"]["presentation_constraints"], ensure_ascii=False
            )
            variables["required_beats"] = json.dumps(
                projection["writer_view"].get("required_beats", []), ensure_ascii=False
            )
        elif task_id == "pnca.scene.rerender":
            variables["writer_view"] = json.dumps(projection["writer_view"], ensure_ascii=False)
            variables["draft"] = json.dumps(projection["draft"], ensure_ascii=False)
            variables["issues"] = json.dumps(projection["issues"], ensure_ascii=False)
        elif task_id == "pnca.scene.coverage":
            writer_view = projection["writer_view"]
            variables["writer_view"] = json.dumps(writer_view, ensure_ascii=False)
            variables["draft"] = json.dumps(projection["draft"], ensure_ascii=False)
            variables["obligations"] = json.dumps({
                "required_beat_indexes": list(range(len(writer_view.get("required_beats", [])))),
                "requires_end_constraint": bool(writer_view.get("end_constraints")),
            }, ensure_ascii=False)
        elif task_id == "pnca.scene.revise":
            variables["writer_view"] = json.dumps(projection["writer_view"], ensure_ascii=False)
            variables["draft"] = json.dumps(projection["draft"], ensure_ascii=False)
            variables["protected_coverage"] = json.dumps(projection["protected_coverage"], ensure_ascii=False)
            variables["issues"] = json.dumps(projection["issues"], ensure_ascii=False)
        elif task_id == "pnca.draft.audit":
            variables["writer_view"] = json.dumps(projection["writer_view"], ensure_ascii=False)
            variables["draft"] = json.dumps(projection["draft"], ensure_ascii=False)
        else:
            variables["request"] = json.dumps(projection["request"], ensure_ascii=False)
            if task_id in {"pnca.volume.contract", "pnca.chapter.contract", "pnca.scene.contract"}:
                variables["parent"] = json.dumps(projection["parent"], ensure_ascii=False)
            if task_id == "pnca.scene.contract":
                variables["frontier"] = json.dumps(projection["frontier"], ensure_ascii=False)
                variables["canon_projection"] = json.dumps(projection["canon_projection"], ensure_ascii=False)
                variables["admission_allowances"] = json.dumps(projection["admission_allowances"], ensure_ascii=False)
        user_prompt = prompt_manager.render(prompt_name, variables)
        capture_factory = getattr(client, "with_capture", None)
        if repository is not None and run is not None and not callable(capture_factory):
            raise TypeError("production PNCA client must support attempt-scoped capture")
        for attempt_number in range(1, max_generation_attempts + 1):
            call_client = client
            evidence_attempt = None
            if repository is not None and run is not None:
                evidence_attempt = repository.start_attempt(
                    run,
                    task_id=task_id,
                    phase=_phase_for_task(task_id),
                    reason=(
                        "capture one provider request, response, parse, and validation result "
                        f"(generation attempt {attempt_number}/{max_generation_attempts})"
                    ),
                )
            try:
                if evidence_attempt is not None:
                    assert callable(capture_factory)
                    assert repository is not None
                    assert run is not None
                    call_client = cast(
                        Any,
                        capture_factory(AttemptCapture(repository, evidence_attempt, verbose=run.manifest.verbose)),
                    )
                result = call_client.complete_json(
                    kind=task_id,
                    system_prompt=_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    schema=schema,
                )
            except Exception as exc:
                retryable = isinstance(exc, (SchemaValidationError, SchemaEchoError))
                if evidence_attempt is not None and repository is not None:
                    repository.fail_attempt(
                        evidence_attempt,
                        error_code=type(exc).__name__.upper(),
                        retryable=retryable and attempt_number < max_generation_attempts,
                        detail=str(exc),
                    )
                if retryable and attempt_number < max_generation_attempts:
                    continue
                raise
            if evidence_attempt is not None and repository is not None:
                repository.succeed_attempt(evidence_attempt, reason="llm_evidence_captured")
            return result
        raise AssertionError("bounded generation retry loop exhausted without returning or raising")

    return PNCATaskExecutor(registry=default_pnca_task_registry(), provider=provider)
