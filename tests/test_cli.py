"""CLI behavior regression tests."""

from __future__ import annotations

from typer.testing import CliRunner

from novel_forge import cli


class FailingEngine:
    def plan(self, keywords: str):
        raise RuntimeError(f"plan failed for {keywords}")


def test_complete_failure_reports_original_error_without_assertion(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "make_engine", lambda *args, **kwargs: FailingEngine())

    result = CliRunner().invoke(cli.app, ["complete", "テスト", "--workdir", str(tmp_path)])

    assert result.exit_code == 1
    assert "Plan failed: plan failed for テスト" in result.output
    assert "AssertionError" not in result.output
    assert "Complete!" not in result.output
