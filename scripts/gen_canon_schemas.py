"""Generate v2 Canon JSON Schemas from Pydantic models (§9).

Pydantic v2 models in ``novel_forge.canon.models`` are the single source of
truth for the Canon domain contract. This script emits ``model_json_schema()``
output for each public model, attaches a fixed ``$id`` (so sibling ``$ref``
resolves through a ``referencing.Registry``), and writes the files into
``src/novel_forge/canon/schemas/``.

Run this only when the models change — the generated artifacts are committed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from novel_forge.canon.models import (
    Canon,
    CanonPatch,
    ContextScope,
    DesignIntent,
    EntityRef,
    SourceRef,
    WriterContext,
)

_OUT_DIR = Path(__file__).resolve().parent.parent / "src" / "novel_forge" / "canon" / "schemas"
SCHEMA_BASE = "https://novel-forge.local/schemas/canon"
DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"

_SCHEMAS: list[tuple[type[BaseModel], str]] = [
    (CanonPatch, "canon_patch"),
    (DesignIntent, "design_intent"),
    (ContextScope, "context_scope"),
    (WriterContext, "writer_context"),
    (EntityRef, "entity_ref"),
    (SourceRef, "source_ref"),
    (Canon, "canon"),
]


def _attach_ids(raw: dict[str, Any], root_name: str) -> dict[str, Any]:
    """Stamp a fixed ``$id`` and ``$schema`` on the root document only.

    §9 requires a fixed ``$id`` per schema so sibling ``$ref`` resolves through
    the ``referencing.Registry``. We attach ``$id`` to the root document only —
    ``$defs`` entries must NOT carry their own ``$id`` (that breaks
    ``referencing``'s specification detection). The absolute ``$ref`` values
    (rewritten by ``_rewrite_refs``) already point at the root document's
    ``$id#/$defs/X``, which the registry resolves without per-def ``$id``.

    Pydantic's ``model_json_schema()`` does not emit a top-level ``$schema``
    keyword, so ``referencing`` cannot auto-detect the dialect — we inject it
    explicitly so ``Resource.from_contents`` can build the right spec.
    """
    root_id = f"{SCHEMA_BASE}/{root_name}.json"
    raw = dict(raw)
    raw["$schema"] = DRAFT_2020_12
    raw["$id"] = root_id
    return raw


def _rewrite_refs(node: Any, root_id: str) -> Any:
    """Rewrite local ``#/$defs/X`` refs to absolute ``canon_patch.json#/$defs/X``.

    Every generated model shares the same ``$defs`` shape (all derive from
    the same Canon sub-models), so we point intra-document refs at the
    canonical home ``canon_patch.json#/$defs/X``.
    """
    if isinstance(node, dict):
        new = {k: _rewrite_refs(v, root_id) for k, v in node.items()}
        ref = new.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            def_name = ref.split("/", 2)[2]
            new["$ref"] = f"{SCHEMA_BASE}/canon_patch.json#/$defs/{def_name}"
        return new
    if isinstance(node, list):
        return [_rewrite_refs(v, root_id) for v in node]
    return node


def main() -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for model, name in _SCHEMAS:
        raw = model.model_json_schema(by_alias=True)
        rooted = _attach_ids(raw, name)
        rooted = _rewrite_refs(rooted, rooted["$id"])
        out_path = _OUT_DIR / f"{name}.json"
        out_path.write_text(
            json.dumps(rooted, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(out_path.name)

    # scene_design is the only artifact that $refs canon_patch (§9).
    scene_design = {
        "$schema": DRAFT_2020_12,
        "$id": f"{SCHEMA_BASE}/scene_design.json",
        "type": "object",
        "properties": {
            "canon_patch": {"$ref": f"{SCHEMA_BASE}/canon_patch.json"},
            "context_scope": {"$ref": f"{SCHEMA_BASE}/context_scope.json"},
            "design_intent": {"$ref": f"{SCHEMA_BASE}/design_intent.json"},
        },
        "additionalProperties": True,
    }
    sd_path = _OUT_DIR / "scene_design.json"
    sd_path.write_text(
        json.dumps(scene_design, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    written.append(sd_path.name)
    print(f"wrote {len(written)} schema files to {_OUT_DIR}")
    for w in written:
        print(f"  - {w}")


if __name__ == "__main__":
    main()
