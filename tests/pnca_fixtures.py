"""Strict PNCA contract fixtures shared by PNCA tests."""

from __future__ import annotations

from novel_forge.pnca.contracts import ChapterPlan, SceneMandate, SceneSlot, WriterView


def mandate() -> SceneMandate:
    return SceneMandate(
        start_state="調査前", required_transition="手がかりを確認する", end_state="確認済み",
        relationship_contribution="危険を共有する", prohibited_repetition="同じ手がかりを調べ直す",
    )


def chapter_plan(*, scene_count: int = 1) -> ChapterPlan:
    return ChapterPlan(
        ordinal=1, chapter_purpose="試験章の変化", relationship_shift="関係が変わる",
        reader_pull="次の問い", scene_count=scene_count,
    )


def scene_slot(slot_id: str = "scene_001", ordinal: int = 1) -> SceneSlot:
    return SceneSlot(slot_id=slot_id, ordinal=ordinal, mandate=mandate())


def writer_view(*, pov: str = "リナ", final_state: str = "塔の扉に手を置く") -> WriterView:
    return WriterView(
        start_context={"pov": pov, "location": "塔", "observable_start_state": "塔の扉が見える"},
        narrative_contract={"goal": "塔へ行く", "progression": "扉を調べる", "obstacle": "扉が閉ざされている", "remaining_uncertainty": "扉の向こう"},
        end_constraints={"pov": pov, "final_state": final_state},
        presentation_constraints={"pov": pov, "tone": "抑制的"},
        required_beats=({"description": final_state},),
    )
