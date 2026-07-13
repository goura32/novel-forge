"""Public PNCA workflow boundaries built from immutable contract artifacts."""

from __future__ import annotations

from typing import Any, cast

from novel_forge.pnca.contracts import (
    AcceptanceCommit,
    ChapterAcceptanceCommit,
    ChapterContract,
    FrontierBinding,
    SceneContract,
    SeriesAcceptanceCommit,
    SeriesContract,
    VolumeAcceptanceCommit,
    VolumeContract,
)
from novel_forge.pnca.progression import AuthoredContract
from novel_forge.runtime import (
    ArtifactReference,
    RunHandle,
    RunRepository,
    RuntimeContractError,
    SelectionSnapshot,
)


class PNCAWorkflow:
    """Public orchestration facade; it never reads mutable "latest" state."""

    def __init__(self, *, repository: RunRepository, contract_author: Any) -> None:
        self.repository = repository
        self.contract_author = contract_author

    def author_series(
        self, *, run: RunHandle, scope_id: str, request: ArtifactReference
    ) -> AuthoredContract[SeriesContract]:
        """Produce root artifacts before the caller acquires the final series lock."""
        return cast(
            AuthoredContract[SeriesContract],
            self.contract_author.author_series(run=run, scope_id=scope_id, request=request),
        )

    def accept_series(self, *, authored: AuthoredContract[SeriesContract]) -> SelectionSnapshot:
        """Atomically select one fully materialized Series root."""
        contract = authored.contract
        seed = self.repository.verify_artifact(contract.canon_seed_artifact_id)
        frontier = self.repository.verify_artifact(contract.root_frontier_artifact_id)
        if frontier.manifest.content_digest != contract.root_frontier_digest:
            raise RuntimeContractError("SeriesContract root frontier digest is not the selected artifact digest")
        acceptance = SeriesAcceptanceCommit(
            acceptance_id=f"accept_{contract.contract_id}",
            operation_key=f"{contract.contract_id}:root:{contract.contract_id}:accept",
            role_artifact_ids={
                "series.contract": authored.artifact.artifact_id,
                "canon.seed": seed.artifact_id,
                "canon.frontier.output": frontier.artifact_id,
            },
        )
        return self.repository.commit_pnca_series_acceptance(
            slug=contract.contract_id,
            acceptance=acceptance,
        )


    def author_volume(
        self, *, run: RunHandle, parent: AuthoredContract[SeriesContract], request: ArtifactReference, scope_id: str
    ) -> AuthoredContract[VolumeContract]:
        return cast(AuthoredContract[VolumeContract], self.contract_author.author_volume(run=run, parent=parent, request=request, scope_id=scope_id))

    def accept_volume(self, *, slug: str, authored: AuthoredContract[VolumeContract], base_snapshot_id: str) -> SelectionSnapshot:
        contract = authored.contract
        return self.repository.commit_pnca_volume_acceptance(
            slug=slug,
            acceptance=VolumeAcceptanceCommit(
                acceptance_id=f"accept_{contract.contract_id}",
                base_snapshot_id=base_snapshot_id,
                operation_key=f"{slug}:volume:{contract.volume_ordinal:03d}:accept",
                role_artifact_ids={"volume.contract": authored.artifact.artifact_id},
            ),
        )

    def author_chapter(
        self, *, run: RunHandle, parent: AuthoredContract[VolumeContract], request: ArtifactReference, scope_id: str
    ) -> AuthoredContract[ChapterContract]:
        return cast(
            AuthoredContract[ChapterContract],
            self.contract_author.author_chapter(run=run, parent=parent, request=request, scope_id=scope_id),
        )

    def accept_chapter(
        self,
        *,
        slug: str,
        authored: AuthoredContract[ChapterContract],
        base_snapshot_id: str,
        volume_ordinal: int,
    ) -> SelectionSnapshot:
        contract = authored.contract
        return self.repository.commit_pnca_chapter_acceptance(
            slug=slug,
            acceptance=ChapterAcceptanceCommit(
                acceptance_id=f"accept_{contract.contract_id}",
                base_snapshot_id=base_snapshot_id,
                operation_key=(
                    f"{slug}:volume:{volume_ordinal:03d}:chapter:{contract.chapter_ordinal:03d}:accept"
                ),
                role_artifact_ids={"chapter.contract": authored.artifact.artifact_id},
            ),
        )

    def author_scene(
        self,
        *,
        run: RunHandle,
        parent: AuthoredContract[ChapterContract],
        request: ArtifactReference,
        frontier: ArtifactReference,
        frontier_binding: FrontierBinding,
        scope_id: str,
    ) -> AuthoredContract[SceneContract]:
        """Author one scene from only the pinned Chapter, frontier, and request."""
        return cast(
            AuthoredContract[SceneContract],
            self.contract_author.author_scene(
                run=run,
                parent=parent,
                request=request,
                frontier=frontier,
                frontier_binding=frontier_binding,
                scope_id=scope_id,
            ),
        )

    def accept_scene(
        self,
        *,
        slug: str,
        acceptance: AcceptanceCommit,
        frontier_binding: FrontierBinding,
    ) -> SelectionSnapshot:
        """Publish a complete validated scene acceptance without recomposing its roles."""
        return self.repository.commit_pnca_acceptance(
            slug=slug,
            acceptance=acceptance,
            frontier_binding=frontier_binding,
        )

    def bootstrap_series(
        self, *, run: RunHandle, scope_id: str, request: ArtifactReference
    ) -> SelectionSnapshot:
        """Convenience boundary for callers that do not need lock promotion."""
        return self.accept_series(authored=self.author_series(run=run, scope_id=scope_id, request=request))
