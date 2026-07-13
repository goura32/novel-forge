"""Production PNCA task specifications backed by packaged resources."""

from __future__ import annotations

from hashlib import sha256
from importlib import resources

from novel_forge.pnca.registry import ArtifactSpec, InputBinding, PNCATaskRegistry, TaskSpec


def _resource_digest(name: str, suffix: str) -> str:
    raw = (resources.files("novel_forge") / "resources" / name / suffix).read_bytes()
    return f"sha256:{sha256(raw).hexdigest()}"


def default_pnca_task_registry() -> PNCATaskRegistry:
    """Return the production allow-list; no task is inferred from filenames."""
    return PNCATaskRegistry(
        specs=(
            TaskSpec(
                task_id="pnca.series.contract",
                task_kind="authoring",
                input_bindings=(InputBinding(role="series.request", variable="request"),),
                output=ArtifactSpec(
                    role="series.contract.proposal",
                    artifact_type="pnca.series.contract.proposal",
                    logical_key_template="pnca.series.contract.proposal.{scope_id}",
                ),
                prompt_digest=_resource_digest("prompts", "pnca_series_contract.md"),
                schema_digest=_resource_digest("schemas", "pnca_series_contract.json"),
                model_profile="default",
                max_input_bytes=16_384,
                max_output_bytes=65_536,
                idempotency_scope="series-contract",
            ),
            TaskSpec(
                task_id="pnca.volume.contract",
                task_kind="authoring",
                input_bindings=(
                    InputBinding(role="parent.contract", variable="parent"),
                    InputBinding(role="volume.request", variable="request"),
                ),
                output=ArtifactSpec(
                    role="volume.contract.proposal",
                    artifact_type="pnca.volume.contract.proposal",
                    logical_key_template="pnca.volume.contract.proposal.{scope_id}",
                ),
                prompt_digest=_resource_digest("prompts", "pnca_volume_contract.md"),
                schema_digest=_resource_digest("schemas", "pnca_volume_contract.json"),
                model_profile="default",
                max_input_bytes=16_384,
                max_output_bytes=65_536,
                idempotency_scope="volume-contract",
            ),
        )
    )
