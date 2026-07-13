"""Public PNCA workflow boundaries built from immutable contract artifacts."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from novel_forge.pnca.contracts import (
    AcceptanceCommit,
    AdmissionAllowance,
    AdmissionConsumption,
    BundleSlotRecord,
    ChapterAcceptanceCommit,
    ChapterContract,
    DesignBundle,
    FrontierBinding,
    SceneContract,
    SceneSlot,
    SeriesAcceptanceCommit,
    SeriesContract,
    VolumeAcceptanceCommit,
    VolumeContract,
)
from novel_forge.pnca.progression import AuthoredContract
from novel_forge.pnca.scene_audit import PNCASceneAuditSynthesizer
from novel_forge.pnca.scene_preparation import PNCASceneStructurePreparer, PreparedSceneStructure
from novel_forge.pnca.writer import PNCARenderer
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
        admission_allowances: Iterable[AdmissionAllowance] = (),
        scene_slot: SceneSlot | None = None,
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
                admission_allowances=admission_allowances,
                scene_slot=scene_slot,
            ),
        )

    def prepare_scene_structure(
        self,
        *,
        slug: str,
        run: RunHandle,
        scene: AuthoredContract[SceneContract],
        parent_chapter: AuthoredContract[ChapterContract],
        parent_volume: AuthoredContract[VolumeContract],
    ) -> PreparedSceneStructure:
        """Materialize deterministic scene roles before provider-backed audit synthesis."""
        return PNCASceneStructurePreparer(repository=self.repository).prepare(
            slug=slug,
            run=run,
            scene=scene,
            parent_chapter=parent_chapter,
            parent_volume=parent_volume,
        )

    def build_scene_acceptance(
        self,
        *,
        slug: str,
        run: RunHandle,
        scene: AuthoredContract[SceneContract],
        parent_chapter: AuthoredContract[ChapterContract],
        parent_volume: AuthoredContract[VolumeContract],
        frontier_binding: FrontierBinding,
        base_snapshot_id: str,
    ) -> AcceptanceCommit:
        """Assemble every required role into one acceptance commit for a non-mutating scene."""
        structure = PNCASceneStructurePreparer(repository=self.repository).prepare(
            slug=slug,
            run=run,
            scene=scene,
            parent_chapter=parent_chapter,
            parent_volume=parent_volume,
        )
        audit = PNCASceneAuditSynthesizer(repository=self.repository).run_structural_audit(
            run=run,
            slug=slug,
            scene=scene,
            parent_chapter=parent_chapter,
            parent_volume=parent_volume,
        )
        contract = scene.contract
        return AcceptanceCommit(
            acceptance_id=f"accept_{contract.contract_id}",
            base_snapshot_id=base_snapshot_id,
            operation_key=f"{slug}:scene:{contract.contract_id}:accept",
            canon_effect="none",
            role_artifact_ids={
                **structure.role_artifact_ids,
                "audit.batch": audit.batch.artifact_id,
                "review.synthesis": audit.synthesis.artifact_id,
            },
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

    def design_volume_full(
        self,
        *,
        slug: str,
        run: RunHandle,
        parent: AuthoredContract[SeriesContract],
        volume_ordinal: int,
        base_snapshot_id: str,
        chapters: int,
    ) -> SelectionSnapshot:
        """Author and accept one Volume Contract plus every Chapter and Scene it contains.

        The chapter count is supplied by the caller (the VolumeContract must not
        enumerate chapters).  Each Chapter Contract decides its own scene slots,
        which are then authored and accepted in sequence.
        """
        from novel_forge.pnca.production import (
            stage_chapter_request,
            stage_scene_request,
            stage_volume_request,
        )

        volume_request = stage_volume_request(
            repository=self.repository, run=run, series_id=slug, volume_ordinal=volume_ordinal
        )
        volume_authored = self.author_volume(
            run=run,
            parent=parent,
            request=volume_request,
            scope_id=f"{slug}.volume.{volume_ordinal:03d}",
        )
        snapshot = self.accept_volume(
            slug=slug, authored=volume_authored, base_snapshot_id=base_snapshot_id
        )
        current_snapshot_id = snapshot.selection_snapshot_id

        for chapter_ordinal in range(1, chapters + 1):
            chapter_request = stage_chapter_request(
                repository=self.repository,
                run=run,
                volume_id=volume_authored.contract.contract_id,
                chapter_ordinal=chapter_ordinal,
            )
            chapter_authored = self.author_chapter(
                run=run,
                parent=volume_authored,
                request=chapter_request,
                scope_id=f"{slug}.volume.{volume_ordinal:03d}.chapter.{chapter_ordinal:03d}",
            )
            snapshot = self.accept_chapter(
                slug=slug,
                authored=chapter_authored,
                base_snapshot_id=current_snapshot_id,
                volume_ordinal=volume_ordinal,
            )
            current_snapshot_id = snapshot.selection_snapshot_id

            base_snapshot = self.repository.load_snapshot(slug, current_snapshot_id)
            frontier_id = base_snapshot.slots.get("canon.frontier")
            if frontier_id is None:
                raise RuntimeContractError("selected snapshot requires canon.frontier for scene authoring")
            frontier = self.repository.verify_artifact(frontier_id)
            lineage_root = frontier.manifest.canon_lineage_root_digest
            if lineage_root is None:
                raise RuntimeContractError("scene frontier artifact requires a canon lineage root digest")

            consumed_admissions: tuple[AdmissionConsumption, ...] = ()
            for scene_slot in sorted(chapter_authored.contract.scene_slots, key=lambda s: s.ordinal):
                # The frontier artifact is stable per chapter; rebind its input
                # snapshot to the snapshot each scene is accepted against so the
                # acceptance commit's base snapshot matches the frontier binding.
                frontier_binding = FrontierBinding(
                    input_snapshot_id=current_snapshot_id,
                    frontier_artifact_id=frontier.artifact_id,
                    frontier_digest=frontier.manifest.content_digest,
                    lineage_root_digest=lineage_root,
                )
                scene_request = stage_scene_request(
                    repository=self.repository,
                    run=run,
                    chapter_id=chapter_authored.contract.contract_id,
                    slot_id=scene_slot.slot_id,
                )
                scene_authored, consumed_admissions = self.contract_author.author_scene(
                    run=run,
                    parent=chapter_authored,
                    request=scene_request,
                    frontier=frontier,
                    frontier_binding=frontier_binding,
                    scope_id=f"{slug}.{volume_ordinal:03d}.{chapter_ordinal:03d}.{scene_slot.slot_id}",
                    admission_allowances=volume_authored.contract.admission_allowances,
                    scene_slot=scene_slot,
                    previously_consumed=consumed_admissions,
                )
                acceptance = self.build_scene_acceptance(
                    slug=slug,
                    run=run,
                    scene=scene_authored,
                    parent_chapter=chapter_authored,
                    parent_volume=volume_authored,
                    frontier_binding=scene_authored.contract.frontier_binding,
                    base_snapshot_id=current_snapshot_id,
                )
                snapshot = self.accept_scene(
                    slug=slug, acceptance=acceptance, frontier_binding=scene_authored.contract.frontier_binding
                )
                current_snapshot_id = snapshot.selection_snapshot_id

        return snapshot

    def write_volume(
        self,
        *,
        slug: str,
        run: RunHandle,
        volume: int,
        executor: Any,
    ) -> DesignBundle:
        """Render every accepted Scene in a Volume into a frozen, export-ready DesignBundle."""
        snapshot_id = self.repository.current_snapshot_id(slug)
        snapshot = self.repository.load_snapshot(slug, snapshot_id)
        volume_artifact_id = snapshot.slots.get(f"pnca.volume.contract.{slug}.{volume:03d}")
        if volume_artifact_id is None:
            raise RuntimeContractError(f"selected snapshot has no accepted Volume {volume} contract")
        volume_ref = self.repository.verify_artifact(volume_artifact_id)
        VolumeContract.model_validate(self.repository.read_payload(volume_ref))

        renderer = PNCARenderer(repository=self.repository)
        slots: list[BundleSlotRecord] = []
        chapter_prefix = f"pnca.chapter.contract.{slug}.{volume:03d}."
        scene_prefix = f"pnca.scene.contract.{slug}.{volume:03d}."
        for chapter_key, chapter_artifact_id in sorted(snapshot.slots.items()):
            if not chapter_key.startswith(chapter_prefix):
                continue
            chapter_ref = self.repository.verify_artifact(chapter_artifact_id)
            chapter_contract = ChapterContract.model_validate(self.repository.read_payload(chapter_ref))
            for scene_slot in sorted(chapter_contract.scene_slots, key=lambda s: s.ordinal):
                scene_artifact_id = snapshot.slots.get(
                    f"{scene_prefix}{chapter_contract.chapter_ordinal:03d}.{scene_slot.slot_id}"
                )
                if scene_artifact_id is None:
                    continue
                scene_ref = self.repository.verify_artifact(scene_artifact_id)
                scene_contract = SceneContract.model_validate(self.repository.read_payload(scene_ref))
                scope_id = f"{slug}.volume.{volume:03d}.chapter.{chapter_contract.chapter_ordinal:03d}.scene.{scene_slot.slot_id}"
                rendered = renderer.render(
                    run=run,
                    scene_contract_artifact_id=scene_ref.artifact_id,
                    scene_contract_digest=scene_ref.manifest.content_digest,
                    view=scene_contract.writer_view,
                    executor=executor,
                    scope_id=scope_id,
                )
                audit = renderer.audit(
                    run=run,
                    scene_contract_artifact_id=scene_ref.artifact_id,
                    writer_view=scene_contract.writer_view,
                    writer_view_artifact_id=rendered.writer_view.artifact_id,
                    draft=rendered.draft,
                    executor=executor,
                    scope_id=scope_id,
                )
                slots.append(
                    BundleSlotRecord(
                        volume_ordinal=volume,
                        chapter_ordinal=chapter_contract.chapter_ordinal,
                        scene_ordinal=scene_slot.ordinal,
                        scene_slot_id=scene_slot.slot_id,
                        scene_contract_artifact_id=scene_ref.artifact_id,
                        writer_view_artifact_id=rendered.writer_view.artifact_id,
                        draft_artifact_id=rendered.draft.artifact_id,
                        draft_assessment_artifact_id=audit.artifact_id,
                        output_frontier_artifact_id=scene_contract.frontier_binding.frontier_artifact_id,
                    )
                )
        if not slots:
            raise RuntimeContractError(f"selected snapshot has no accepted scenes for Volume {volume}")
        return DesignBundle(bundle_id=f"{slug}.volume.{volume:03d}", slots=tuple(slots))

    def bootstrap_series(
        self, *, run: RunHandle, scope_id: str, request: ArtifactReference
    ) -> SelectionSnapshot:
        """Convenience boundary for callers that do not need lock promotion."""
        return self.accept_series(authored=self.author_series(run=run, scope_id=scope_id, request=request))
