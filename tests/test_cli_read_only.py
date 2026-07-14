from __future__ import annotations

from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import novel_forge.cli as cli
from novel_forge.config import RuntimeConfig

app = cli.app


@pytest.fixture(autouse=True)
def _isolated_canonical_config(monkeypatch):
    monkeypatch.setattr(cli.RuntimeConfig, "load", classmethod(lambda _cls: RuntimeConfig()))


def test_status_is_read_only_and_inspection_commands_are_registered(tmp_path):
    runner = CliRunner()
    before = list(tmp_path.rglob("*"))

    result = runner.invoke(app, ["status", "--workdir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert list(tmp_path.rglob("*")) == before
    help_result = runner.invoke(app, ["--help"])
    assert help_result.exit_code == 0
    for command in ("runs", "run", "attempt", "llm", "artifact"):
        assert command in help_result.output


def test_side_effect_commands_expose_wait_lock_option_and_no_inert_review_overrides(tmp_path):
    runner = CliRunner()
    for command in ("plan", "design", "write", "export", "resume"):
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0, result.output
        assert "--wait-lock" in result.output, f"{command} must expose --wait-lock"
    for command in ("plan", "design", "write"):
        result = runner.invoke(app, [command, "--help"])
        assert "--max-review-count" not in result.output
        assert "--max-summary-review-count" not in result.output
    help_result = runner.invoke(app, ["--help"])
    assert "│ complete" not in help_result.output
    removed = runner.invoke(app, ["complete", "--help"])
    assert removed.exit_code != 0
    assert "No such command" in removed.output


def test_design_all_skips_already_selected_volumes() -> None:
    snapshot = SimpleNamespace(
        slots={
            "pnca.series.contract.run_001": "art_series",
            "pnca.volume.contract.series_001.001": "art_volume_001",
        }
    )

    assert cli._pending_volume_ordinals(
        snapshot=snapshot,
        slug="series_001",
        declared_ordinals={1, 2, 3},
    ) == [2, 3]
