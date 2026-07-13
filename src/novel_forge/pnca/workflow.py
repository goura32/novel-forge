"""Public PNCA workflow boundaries built from immutable contract artifacts."""

from __future__ import annotations

from typing import Any, cast

from novel_forge.pnca.contracts import SeriesAcceptanceCommit, SeriesContract
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

    def bootstrap_series(
        self, *, run: RunHandle, scope_id: str, request: ArtifactReference
    ) -> SelectionSnapshot:
        """Convenience boundary for callers that do not need lock promotion."""
        return self.accept_series(authored=self.author_series(run=run, scope_id=scope_id, request=request))
