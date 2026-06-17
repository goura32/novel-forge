from __future__ import annotations

from pathlib import Path

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


class PromptLoader:
    def __init__(self, prompt_dir: Path | None = None):
        self._dir = prompt_dir or _PROMPT_DIR

    def load(self, name: str) -> str:
        path = self._dir / name
        if not path.exists():
            raise FileNotFoundError(f"Prompt not found: {path}")
        return path.read_text(encoding="utf-8")


def render_prompt(template: str, variables: dict[str, str]) -> str:
    """Render a template by replacing {key} placeholders with values.

    Placeholders use single-brace format: {key}
    Keys are sorted by length (longest first) to avoid partial matches.
    """
    result = template
    for key in sorted(variables, key=len, reverse=True):
        result = result.replace(f"{{{key}}}", str(variables[key]))
    return result


class PromptManager:
    def __init__(self, loader: PromptLoader | None = None):
        self._loader = loader or PromptLoader()

    def render(self, name: str, variables: dict[str, str]) -> str:
        template = self._loader.load(name)
        return render_prompt(template, variables)
