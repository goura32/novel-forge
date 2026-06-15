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
    result = template
    for key, value in variables.items():
        result = result.replace(f"{{{key}}}", str(value))
    # Check for unresolved placeholders ({{var}} format)
    import re
    unresolved = re.findall(r"\{\{(\w+)\}\}", result)
    if unresolved:
        raise KeyError(f"Missing template variables: {unresolved}")
    return result


class PromptManager:
    def __init__(self, loader: PromptLoader | None = None):
        self._loader = loader or PromptLoader()

    def render(self, name: str, variables: dict[str, str]) -> str:
        template = self._loader.load(name)
        return render_prompt(template, variables)
