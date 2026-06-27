"""NovelForge engine package — mixin-free architecture."""

from .base import NovelEngineBase
from .plan import plan
from .design import design
from .write import write
from .export import export, resume, status


class NovelEngine(NovelEngineBase):
    """NovelEngine — all phase methods defined directly.

    No mixins. Each method delegates to a standalone function.
    """

    def plan(self, keywords: str) -> dict:
        return plan(self, keywords)

    def design(self, volume_number: int | None = None) -> dict:
        return design(self, volume_number)

    def write(self, volume_number: int | None = None) -> list:
        return write(self, volume_number)

    def export(self, volume_number: int | None = None) -> dict:
        return export(self, volume_number)

    def resume(self) -> dict:
        return resume(self)

    def status(self) -> dict:
        return status(self)


__all__ = ["NovelEngine"]
