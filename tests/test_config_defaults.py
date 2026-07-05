"""Configuration/default precedence tests."""

from __future__ import annotations

from novel_forge.engine import NovelEngine


def test_missing_config_uses_builtin_defaults(monkeypatch, tmp_path) -> None:
    """When no config.yaml is discoverable, built-in defaults must be sufficient."""
    monkeypatch.delenv("NOVEL_FORGE_CONFIG", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.chdir(tmp_path)

    workdir = tmp_path / "workspace"
    workdir.mkdir()

    engine = NovelEngine(workdir=workdir, model=None, verbose=None, raw_log_enabled=None)

    assert engine._llm.model == "qwen3.6:35b-a3b-mtp-q4_K_M"
    assert engine._llm.api_url == "http://ws1.local:11434/api/chat"
    assert engine._llm.timeout_seconds == 3600
    assert engine._llm.max_retries == 2
    assert engine._llm.num_ctx == 262144
    assert engine._llm.num_predict == -1
    assert engine._quality.generation_max_count == 3
    assert engine._quality.review_max_count == 8
    assert engine._verbose is False
    assert engine._raw_log_enabled is False


def test_workdir_config_applies_when_cli_options_are_omitted(monkeypatch, tmp_path) -> None:
    """config.yaml in --workdir should apply even when cwd is elsewhere."""
    monkeypatch.delenv("NOVEL_FORGE_CONFIG", raising=False)
    other_cwd = tmp_path / "other"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    workdir = tmp_path / "workspace"
    workdir.mkdir()
    (workdir / "config.yaml").write_text(
        """
quality:
  max_generation_count: 5
  max_review_count: 6
logging:
  verbose: true
  raw_log: true
llm:
  model: config-model
  ollama_host: config-host:11434
  timeout_seconds: 123
  max_retries: 4
  num_ctx: 8192
  num_predict: 2048
  ollama_options:
    think: false
    temperature: 0.2
""".strip(),
        encoding="utf-8",
    )

    engine = NovelEngine(workdir=workdir, model=None, verbose=None, raw_log_enabled=None)

    assert engine._llm.model == "config-model"
    assert engine._llm.api_url == "http://config-host:11434/api/chat"
    assert engine._llm.timeout_seconds == 123
    assert engine._llm.max_retries == 4
    assert engine._llm.num_ctx == 8192
    assert engine._llm.num_predict == 2048
    assert engine._llm._ollama_options["think"] is False
    assert engine._llm._ollama_options["temperature"] == 0.2
    assert engine._quality.generation_max_count == 5
    assert engine._quality.review_max_count == 6
    assert engine._verbose is True
    assert engine._raw_log_enabled is True


def test_cli_values_override_workdir_config(monkeypatch, tmp_path) -> None:
    """Explicit CLI values still outrank config.yaml."""
    monkeypatch.delenv("NOVEL_FORGE_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)

    workdir = tmp_path / "workspace"
    workdir.mkdir()
    (workdir / "config.yaml").write_text(
        """
quality:
  max_generation_count: 5
  max_review_count: 6
logging:
  verbose: false
  raw_log: false
llm:
  model: config-model
""".strip(),
        encoding="utf-8",
    )

    engine = NovelEngine(
        workdir=workdir,
        model="cli-model",
        max_generation_count=7,
        max_review_count=8,
        verbose=True,
        raw_log_enabled=True,
    )

    assert engine._llm.model == "cli-model"
    assert engine._quality.generation_max_count == 7
    assert engine._quality.review_max_count == 8
    assert engine._verbose is True
    assert engine._raw_log_enabled is True
