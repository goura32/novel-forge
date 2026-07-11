from __future__ import annotations

from typer.testing import CliRunner

from novel_forge.cli import app


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
