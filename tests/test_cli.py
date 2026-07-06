"""CLI behavior regression tests."""

from __future__ import annotations

from pathlib import Path

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


def test_plan_omitted_cli_options_do_not_override_config(monkeypatch, tmp_path) -> None:
    captured: dict = {}

    class Engine:
        _series_dir = Path("out")

        def plan(self, keywords: str):
            captured["keywords"] = keywords
            return {"title": "ok"}

    def fake_make_engine(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Engine()

    monkeypatch.setattr(cli, "make_engine", fake_make_engine)

    result = CliRunner().invoke(cli.app, ["plan", "テスト", "--workdir", str(tmp_path)])

    assert result.exit_code == 0
    assert captured["args"][1] is None  # model omitted; engine/config/default decide
    assert captured["kwargs"]["verbose"] is None


def test_plan_explicit_cli_options_override_config(monkeypatch, tmp_path) -> None:
    captured: dict = {}

    class Engine:
        _series_dir = Path("out")

        def plan(self, keywords: str):
            return {"title": "ok"}

    def fake_make_engine(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Engine()

    monkeypatch.setattr(cli, "make_engine", fake_make_engine)

    result = CliRunner().invoke(
        cli.app,
        ["plan", "テスト", "--workdir", str(tmp_path), "--model", "cli-model", "--verbose"],
    )

    assert result.exit_code == 0
    assert captured["args"][1] == "cli-model"
    assert captured["kwargs"]["verbose"] is True


def test_doctor_omitted_options_use_workdir_config(monkeypatch, tmp_path) -> None:
    captured: dict = {}
    workdir = tmp_path / "workspace"
    workdir.mkdir()
    (workdir / "config.yaml").write_text(
        "llm:\n  model: doctor-config-model\n  ollama_host: doctor-host:11434\n",
        encoding="utf-8",
    )

    def fake_cmd_doctor(model: str, ollama_host: str) -> None:
        captured["model"] = model
        captured["ollama_host"] = ollama_host

    monkeypatch.setattr(cli, "cmd_doctor", fake_cmd_doctor)

    result = CliRunner().invoke(cli.app, ["doctor", "--workdir", str(workdir)])

    assert result.exit_code == 0
    assert captured == {"model": "doctor-config-model", "ollama_host": "doctor-host:11434"}


def test_doctor_explicit_options_override_workdir_config(monkeypatch, tmp_path) -> None:
    captured: dict = {}
    workdir = tmp_path / "workspace"
    workdir.mkdir()
    (workdir / "config.yaml").write_text(
        "llm:\n  model: doctor-config-model\n  ollama_host: doctor-host:11434\n",
        encoding="utf-8",
    )

    def fake_cmd_doctor(model: str, ollama_host: str) -> None:
        captured["model"] = model
        captured["ollama_host"] = ollama_host

    monkeypatch.setattr(cli, "cmd_doctor", fake_cmd_doctor)

    result = CliRunner().invoke(
        cli.app,
        [
            "doctor",
            "--workdir",
            str(workdir),
            "--model",
            "doctor-cli-model",
            "--ollama-host",
            "doctor-cli-host:11434",
        ],
    )

    assert result.exit_code == 0
    assert captured == {"model": "doctor-cli-model", "ollama_host": "doctor-cli-host:11434"}
