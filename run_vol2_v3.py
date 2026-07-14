"""Drive PNCA design+write+export for Vol.2 and Vol.3 of an existing series.

Usage: uv run python run_vol2_v3.py
Resumes from the ledgered series; does NOT re-author the series.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

from novel_forge.cli import (
    _find_existing_series,
    _make_pnca_client,
    _make_pnca_workflow,
    _selected_series_contract,
)
from novel_forge.config import RuntimeConfig
from novel_forge.pnca.export import PNCAExporter
from novel_forge.pnca.production import make_pnca_task_executor
from novel_forge.prompts import PromptManager
from novel_forge.runtime import RunManager, RunRepository

WORKDIR = "/mnt/hdd/projects/novel-forge-romfantasy-prod-20260714T111205"
SLUG = "amnesiac_mage_duke_fake_engagement"
CHAPTERS = 3

# phases to run: 'design','write','export' — controllable via argv[1] e.g. 'write,export'
RUN_PHASES = set(sys.argv[1].split(",")) if len(sys.argv) > 1 else {"design", "write", "export"}
# volumes to run: argv[2] e.g. '2' or '3' or '2,3' (default both)
_VOL_ARG = sys.argv[2] if len(sys.argv) > 2 else "2,3"
VOLUMES = [int(v) for v in _VOL_ARG.split(",")]


def _client_executor(config: RuntimeConfig, model):
    client = _make_pnca_client(config, model)
    return make_pnca_task_executor(client=client, manager=PromptManager())


def main() -> int:
    config = RuntimeConfig.load()
    resolved_workdir = config.resolve_workdir(Path(WORKDIR))
    repo = RunRepository(resolved_workdir)
    manager = RunManager(repo)
    series_dir = _find_existing_series(resolved_workdir, SLUG)
    print(f"series_dir: {series_dir}")

    for volume in VOLUMES:
        # ---- design volume full ----
        if "design" in RUN_PHASES:
            snap_id = repo.current_snapshot_id(series_dir.name)
            run = repo.create_run(command="design", model=config.llm.model, verbose=False, input_snapshot_id=snap_id)
            with manager.side_effect_scope(scope=f"series-{series_dir.name}", run=run, phase="design"):
                workflow = _make_pnca_workflow(repo, config, None)
                parent = _selected_series_contract(repo, series_dir.name, run.manifest.input_snapshot_id)
                base_snapshot_id = repo.current_snapshot_id(series_dir.name)
                print(f"\n=== design_volume_full volume={volume} ===")
                try:
                    workflow.design_volume_full(
                        slug=series_dir.name, run=run, parent=parent,
                        volume_ordinal=volume, base_snapshot_id=base_snapshot_id,
                        chapters=CHAPTERS,
                    )
                    print(f"  design vol {volume} OK")
                except Exception as exc:  # noqa: BLE001
                    print(f"  design vol {volume} FAILED: {exc!r}")
                    traceback.print_exc()
                    return 1

        # ---- write volume ----
        if "write" in RUN_PHASES:
            snap_id = repo.current_snapshot_id(series_dir.name)
            run = repo.create_run(command="write", model=config.llm.model, verbose=False, input_snapshot_id=snap_id)
            with manager.side_effect_scope(scope=f"series-{series_dir.name}", run=run, phase="write"):
                workflow = _make_pnca_workflow(repo, config, None)
                executor = _client_executor(config, None)
                print(f"=== write_volume volume={volume} ===")
                try:
                    bundle = workflow.write_volume(
                        slug=series_dir.name, run=run, volume=volume, executor=executor,
                    )
                    print(f"  write vol {volume} OK (bundle {bundle.bundle_id})")
                except Exception as exc:  # noqa: BLE001
                    print(f"  write vol {volume} FAILED: {exc!r}")
                    traceback.print_exc()
                    return 1

        # ---- export volume ----
        if "export" in RUN_PHASES:
            snap_id = repo.current_snapshot_id(series_dir.name)
            run = repo.create_run(command="export", model=config.llm.model, verbose=False, input_snapshot_id=snap_id)
            with manager.side_effect_scope(scope=f"series-{series_dir.name}", run=run, phase="export"):
                workflow = _make_pnca_workflow(repo, config, None)
                bundle = workflow.load_selected_bundle(slug=series_dir.name, volume=volume)
                exporter = PNCAExporter(repository=repo)
                print(f"=== export_volume volume={volume} ===")
                try:
                    manuscript = exporter.export(run=run, bundle=bundle, format="markdown")
                    print(f"  export vol {volume} OK ({manuscript.artifact.artifact_id})")
                except Exception as exc:  # noqa: BLE001
                    print(f"  export vol {volume} FAILED: {exc!r}")
                    traceback.print_exc()
                    return 1

    print("\nALL DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
