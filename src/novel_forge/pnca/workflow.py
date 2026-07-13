"""Public PNCA workflow boundaries built from immutable contract artifacts."""

from __future__ import annotations

from typing import Any

from novel_forge.pnca.contracts import SeriesAcceptanceCommit
from novel_forge.runtime import RunHandle, RunRepository, RuntimeContractError, SelectionSnapshot


class PNCAWorkflow:
    """Public orchestration facade; it never reads mutable "latest" state."""

    def __init__(self, *, repository: RunRepository, contract_author: Any) -> None:
        self.repository = repository
        self.contract_author = contract_author

    def bootstrap_series(
        self, *, run: RunHandle, slug: str, scope_id: str
    ) -> SelectionSnapshot:
        """Author and atomically select the immutable PNCA Series root."""
        authored = self.contract_author.author_series(run=run, scope_id=scope_id)
        contract = authored.contract
        seed = self.repository.verify_artifact(contract.canon_seed_artifact_id)
        frontier = self.repository.verify_artifact(contract.root_frontier_artifact_id)
        if frontier.manifest.content_digest != contract.root_frontier_digest:
            raise RuntimeContractError("SeriesContract root frontier digest is not the selected artifact digest")
        acceptance = SeriesAcceptanceCommit(
            acceptance_id=f"accept_{contract.contract_id}",
            operation_key=f"{slug}:root:{contract.contract_id}:accept",
            role_artifact_ids={
                "series.contract": authored.artifact.artifact_id,
                "canon.seed": seed.artifact_id,
                "canon.frontier.output": frontier.artifact_id,
            },
        )
        return self.repository.commit_pnca_series_acceptance(slug=slug, acceptance=acceptance)
