"""Progressive, parent-pinned PNCA contract authoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from novel_forge.pnca.contracts import ChapterContract, SeriesContract, VolumeContract
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

    def author_series(self, *, run: RunHandle, scope_id: str) -> AuthoredContract[SeriesContract]:
        return self._author(
            run=run,
            task_id="pnca.series.contract",
            scope_id=scope_id,
            model=SeriesContract,
            parent=None,
        )

    def author_volume(
        self, *, run: RunHandle, parent: AuthoredContract[SeriesContract], scope_id: str
    ) -> AuthoredContract[VolumeContract]:
        authored = self._author(
            run=run,
            task_id="pnca.volume.contract",
            scope_id=scope_id,
            model=VolumeContract,
            parent=parent,
        )
        if authored.contract.parent_series_contract_id != parent.contract.contract_id:
            raise RuntimeContractError("VolumeContract does not bind its parent SeriesContract")
        return authored

    def author_chapter(
        self, *, run: RunHandle, parent: AuthoredContract[VolumeContract], scope_id: str
    ) -> AuthoredContract[ChapterContract]:
        authored = self._author(
            run=run,
            task_id="pnca.chapter.contract",
            scope_id=scope_id,
            model=ChapterContract,
            parent=parent,
        )
        if authored.contract.parent_volume_contract_id != parent.contract.contract_id:
            raise RuntimeContractError("ChapterContract does not bind its parent VolumeContract")
        return authored

    def _author(
        self,
        *,
        run: RunHandle,
        task_id: str,
        scope_id: str,
        model: type[ContractT],
        parent: AuthoredContract[Any] | None,
    ) -> AuthoredContract[ContractT]:
        artifacts = {} if parent is None else {"parent.contract": parent.contract.model_dump(mode="json")}
        input_ids = () if parent is None else (parent.artifact.artifact_id,)
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
