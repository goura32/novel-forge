"""Progressive, parent-pinned PNCA contract authoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from novel_forge.pnca.contracts import (
    ChapterContract,
    FrontierBinding,
    SceneContract,
    SeriesContract,
    SeriesContractProposal,
    VolumeContract,
)
from novel_forge.pnca.registry import PNCATaskExecutor
from novel_forge.runtime import ArtifactReference, RunHandle, RunRepository, RuntimeContractError

ContractT = TypeVar("ContractT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class AuthoredContract(Generic[ContractT]):  # noqa: UP046
    artifact: ArtifactReference
    contract: ContractT


class PNCAContractAuthor:
    """Execute the Series→Volume→Chapter contract progression immutably."""

    def __init__(self, *, repository: RunRepository, executor: PNCATaskExecutor) -> None:
        self.repository = repository
        self.executor = executor

    def author_series(
        self, *, run: RunHandle, scope_id: str, request: ArtifactReference
    ) -> AuthoredContract[SeriesContract]:
        """Materialize provider seed data before pinning a final SeriesContract."""
        result = self.executor.execute(
            task_id="pnca.series.contract",
            artifacts={"series.request": self.repository.read_payload(request)},
            input_artifact_ids=(request.artifact_id,),
            scope_id=scope_id,
        )
        proposal = SeriesContractProposal.model_validate(result)
        seed_attempt = self.repository.start_attempt(
            run, task_id="pnca.series.seed", phase="plan", reason="materialize series Canon seed"
        )
        seed = self.repository.commit_artifact(
            seed_attempt,
            artifact_type="canon.seed",
            logical_key="canon.seed",
            payload=proposal.canon_seed,
            payload_name="canon_seed.json",
        )
        frontier_attempt = self.repository.start_attempt(
            run, task_id="pnca.series.frontier", phase="plan", reason="materialize root Canon frontier"
        )
        frontier = self.repository.commit_artifact(
            frontier_attempt,
            artifact_type="canon.event_set",
            logical_key="canon.frontier.root",
            payload={"events": []},
            payload_name="frontier.json",
            canon_lineage_root_digest=seed.manifest.content_digest,
        )
        contract = SeriesContract(
            contract_id=proposal.contract_id,
            canon_seed_artifact_id=seed.artifact_id,
            root_frontier_artifact_id=frontier.artifact_id,
            root_frontier_digest=frontier.manifest.content_digest,
            volume_purposes=proposal.volume_purposes,
        )
        contract_attempt = self.repository.start_attempt(
            run, task_id="pnca.series.contract", phase="plan", reason="pin finalized series contract"
        )
        artifact = self.repository.commit_artifact(
            contract_attempt,
            artifact_type="pnca.series.contract",
            logical_key=f"pnca.series.contract.{scope_id}",
            payload=contract.model_dump(mode="json"),
            payload_name="contract.json",
            input_artifact_ids=(request.artifact_id, seed.artifact_id, frontier.artifact_id),
        )
        return AuthoredContract(artifact=artifact, contract=contract)

    def author_volume(
        self,
        *,
        run: RunHandle,
        parent: AuthoredContract[SeriesContract],
        request: ArtifactReference,
        scope_id: str,
    ) -> AuthoredContract[VolumeContract]:
        """Author a requested Volume only from its pinned Series and request artifacts."""
        request_payload = self.repository.read_payload(request)
        volume_ordinal = request_payload.get("volume_ordinal") if isinstance(request_payload, dict) else None
        if not isinstance(volume_ordinal, int) or volume_ordinal < 1:
            raise RuntimeContractError("volume request requires a positive volume_ordinal")
        if volume_ordinal not in {item.ordinal for item in parent.contract.volume_purposes}:
            raise RuntimeContractError("volume request ordinal is not allocated by its parent SeriesContract")
        authored = self._author(
            run=run,
            task_id="pnca.volume.contract",
            scope_id=scope_id,
            model=VolumeContract,
            parent=parent,
            request=request,
            request_role="volume.request",
        )
        if authored.contract.parent_series_contract_id != parent.contract.contract_id:
            raise RuntimeContractError("VolumeContract does not bind its parent SeriesContract")
        if authored.contract.volume_ordinal != volume_ordinal:
            raise RuntimeContractError("VolumeContract does not bind its requested volume ordinal")
        return authored

    def author_chapter(
        self,
        *,
        run: RunHandle,
        parent: AuthoredContract[VolumeContract],
        request: ArtifactReference,
        scope_id: str,
    ) -> AuthoredContract[ChapterContract]:
        request_payload = self.repository.read_payload(request)
        if not isinstance(request_payload, dict) or not isinstance(request_payload.get("chapter_ordinal"), int):
            raise RuntimeContractError("ChapterContract requires a chapter.request artifact with chapter_ordinal")
        chapter_ordinal = request_payload["chapter_ordinal"]
        authored = self._author(
            run=run,
            task_id="pnca.chapter.contract",
            scope_id=scope_id,
            model=ChapterContract,
            parent=parent,
            request=request,
            request_role="chapter.request",
        )
        if authored.contract.parent_volume_contract_id != parent.contract.contract_id:
            raise RuntimeContractError("ChapterContract does not bind its parent VolumeContract")
        if authored.contract.chapter_ordinal != chapter_ordinal:
            raise RuntimeContractError("ChapterContract does not bind its requested chapter ordinal")
        return authored

    def author_scene(
        self,
        *,
        run: RunHandle,
        parent: AuthoredContract[ChapterContract],
        slot_id: str,
        frontier: ArtifactReference,
        frontier_binding: FrontierBinding,
        scope_id: str,
    ) -> AuthoredContract[SceneContract]:
        if slot_id not in {slot.slot_id for slot in parent.contract.scene_slots}:
            raise RuntimeContractError("SceneContract slot is not allocated by its parent ChapterContract")
        if (
            frontier_binding.frontier_artifact_id != frontier.artifact_id
            or frontier_binding.frontier_digest != frontier.manifest.content_digest
        ):
            raise RuntimeContractError("SceneContract frontier binding must exactly match its input artifact")
        result = self.executor.execute(
            task_id="pnca.scene.contract",
            artifacts={
                "parent.contract": parent.contract.model_dump(mode="json"),
                "canon.frontier": self.repository.read_payload(frontier),
            },
            input_artifact_ids=(parent.artifact.artifact_id, frontier.artifact_id),
            scope_id=scope_id,
        )
        contract = SceneContract.model_validate(result)
        if contract.slot_id != slot_id:
            raise RuntimeContractError("SceneContract does not bind its allocated ChapterContract slot")
        if contract.frontier_binding != frontier_binding:
            raise RuntimeContractError("SceneContract does not preserve its exact input frontier binding")
        attempt = self.repository.start_attempt(
            run, task_id="pnca.scene.contract", phase="design", reason="author scene contract"
        )
        artifact = self.repository.commit_artifact(
            attempt,
            artifact_type="pnca.scene.contract",
            logical_key=f"pnca.scene.contract.{scope_id}",
            payload=contract.model_dump(mode="json"),
            payload_name="contract.json",
            input_artifact_ids=(parent.artifact.artifact_id, frontier.artifact_id),
        )
        return AuthoredContract(artifact=artifact, contract=contract)

    def _author(
        self,
        *,
        run: RunHandle,
        task_id: str,
        scope_id: str,
        model: type[ContractT],
        parent: AuthoredContract[Any] | None,
        request: ArtifactReference | None = None,
        request_role: str | None = None,
    ) -> AuthoredContract[ContractT]:
        if (request is None) != (request_role is None):
            raise ValueError("request and request_role must be supplied together")
        artifacts = {} if parent is None else {"parent.contract": parent.contract.model_dump(mode="json")}
        input_ids: tuple[str, ...] = () if parent is None else (parent.artifact.artifact_id,)
        if request is not None and request_role is not None:
            artifacts[request_role] = self.repository.read_payload(request)
            input_ids += (request.artifact_id,)
        result = self.executor.execute(
            task_id=task_id,
            artifacts=artifacts,
            input_artifact_ids=input_ids,
            scope_id=scope_id,
        )
        contract = model.model_validate(result)
        attempt = self.repository.start_attempt(run, task_id=task_id, phase="design", reason="author progressive contract")
        artifact = self.repository.commit_artifact(
            attempt,
            artifact_type=f"pnca.{task_id.removeprefix('pnca.')}",
            logical_key=f"{task_id}.{scope_id}",
            payload=contract.model_dump(mode="json"),
            payload_name="contract.json",
            input_artifact_ids=input_ids,
        )
        return AuthoredContract(artifact=artifact, contract=contract)
