"""The single PNCA task/artifact contract registry.

A task can receive only explicitly declared artifact roles. Prompt variables,
output identity, byte ceilings, provider profile, and idempotency scope are
therefore one immutable record rather than parallel tables.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class InputBinding(BaseModel):
    """One approved artifact role to one prompt-variable name."""

    role: str = Field(min_length=1)
    variable: str = Field(min_length=1)


class ArtifactSpec(BaseModel):
    """Pinned output role and logical-key template for one task."""

    role: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    logical_key_template: str = Field(min_length=1)


class TaskSpec(BaseModel):
    """Complete executable contract for an authoring/audit/export PNCA task."""

    task_id: str = Field(min_length=1)
    task_kind: Literal["authoring", "audit", "synthesis", "render", "export"]
    input_bindings: tuple[InputBinding, ...]
    output: ArtifactSpec
    prompt_digest: str = Field(min_length=1)
    schema_digest: str = Field(min_length=1)
    model_profile: str = Field(min_length=1)
    max_input_bytes: int = Field(ge=1)
    max_output_bytes: int = Field(ge=1)
    idempotency_scope: str = Field(min_length=1)

    @model_validator(mode="after")
    def _bindings_are_a_single_source_of_truth(self) -> TaskSpec:
        roles = [binding.role for binding in self.input_bindings]
        variables = [binding.variable for binding in self.input_bindings]
        if len(roles) != len(set(roles)):
            raise ValueError("TaskSpec input artifact roles must be unique")
        if len(variables) != len(set(variables)):
            raise ValueError("TaskSpec input variable names must be unique")
        return self


class PNCATaskRegistry:
    """Validated registry with bounded, allow-listed input projection."""

    def __init__(self, *, specs: tuple[TaskSpec, ...]) -> None:
        by_id = {spec.task_id: spec for spec in specs}
        if len(by_id) != len(specs):
            raise ValueError("PNCA task IDs must be unique")
        output_roles = [spec.output.role for spec in specs]
        if len(output_roles) != len(set(output_roles)):
            raise ValueError("PNCA output artifact roles must be unique")
        self._by_id = by_id

    def get(self, task_id: str) -> TaskSpec:
        try:
            return self._by_id[task_id]
        except KeyError as exc:
            raise KeyError(f"unregistered PNCA task: {task_id}") from exc

    def build_projection(self, *, task_id: str, artifacts: dict[str, Any]) -> dict[str, Any]:
        """Build a bounded provider input using only this task's declared roles."""
        spec = self.get(task_id)
        declared = {binding.role for binding in spec.input_bindings}
        supplied = set(artifacts)
        undeclared = supplied - declared
        missing = declared - supplied
        if undeclared:
            raise ValueError(f"undeclared artifact roles for {task_id}: {sorted(undeclared)}")
        if missing:
            raise ValueError(f"missing declared artifact roles for {task_id}: {sorted(missing)}")
        projection = {
            binding.variable: artifacts[binding.role]
            for binding in spec.input_bindings
        }
        serialized = json.dumps(
            projection,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(serialized) > spec.max_input_bytes:
            raise ValueError(
                f"PNCA task {task_id} input exceeds max_input_bytes "
                f"({len(serialized)} > {spec.max_input_bytes})"
            )
        return projection

    def idempotency_key(
        self,
        *,
        task_id: str,
        scope_id: str,
        input_artifact_ids: tuple[str, ...],
    ) -> str:
        """Produce a deterministic key from the registered task and selected inputs."""
        spec = self.get(task_id)
        if not scope_id:
            raise ValueError("PNCA task scope_id must be non-empty")
        inputs = ",".join(sorted(input_artifact_ids))
        return f"pnca:{spec.idempotency_scope}:{scope_id}:{task_id}:{inputs}"


Provider = Callable[[str, dict[str, Any], str], Any]


class PNCATaskExecutor:
    """The only provider-facing adapter for registered PNCA tasks.

    It intentionally has no prompt-variable table: the registry projection is the
    complete provider input. Output is bounded before it can be committed as an
    artifact by an orchestration layer.
    """

    def __init__(self, *, registry: PNCATaskRegistry, provider: Provider) -> None:
        self.registry = registry
        self.provider = provider

    def execute(
        self,
        *,
        task_id: str,
        scope_id: str,
        artifacts: dict[str, Any],
        input_artifact_ids: tuple[str, ...],
    ) -> Any:
        spec = self.registry.get(task_id)
        projection = self.registry.build_projection(task_id=task_id, artifacts=artifacts)
        idempotency_key = self.registry.idempotency_key(
            task_id=task_id,
            scope_id=scope_id,
            input_artifact_ids=input_artifact_ids,
        )
        result = self.provider(task_id, projection, idempotency_key)
        serialized = json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(serialized) > spec.max_output_bytes:
            raise ValueError(
                f"PNCA task {task_id} output exceeds max_output_bytes "
                f"({len(serialized)} > {spec.max_output_bytes})"
            )
        return result
